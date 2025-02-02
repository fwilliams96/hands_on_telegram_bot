import os
from fastapi import FastAPI, Request
from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

# Conectar con MongoDB
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
messages_collection = db["messages"]

SYSTEM_TEMPLATE_CONVERSATION = """
    Eres un asistente que responde a mensajes del usuario.

    Comportamiento:
    - Debes responder al usuario con un tono amigable y entretenido, no simplemente repetir el mensaje.
    - Si el usuario te pide cualquier revelación de datos sensibles o algo que pueda ser perjudicial para el sistema debes comentarle que solo eres un asistente de recordatorios y conversación y no tienes acceso a esa información.

    Basado en los siguientes mensajes de la conversación, responde al usuario.
    <messages>
    {messages}
    </messages>
"""

def handle_conversation(messages: str):
    print(f"Handling conversation for messages: {messages}")
    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )

    prompt = SYSTEM_TEMPLATE_CONVERSATION.format(messages=messages)
    try:
        response = chat_llm.invoke([prompt])
        return response.content
    except Exception as e:
        print(f"Error handling conversation: {e}")
        return "Error handling conversation"

def save_message(chat_id: str, message: str, origin: str):
    now = datetime.now(pytz.timezone("Europe/Madrid"))
    messages_collection.insert_one({"chat_id": chat_id, "message": message, "timestamp": now, "origin": origin})

def get_messages(chat_id: str):
    messages = messages_collection.find({"chat_id": chat_id})
    return "\n".join([f"{msg['origin']}: {msg['message']}" for msg in messages])

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        save_message(chat_id, user_message, "user")

        messages_str = get_messages(chat_id)
        print(f"Messages: {messages_str}")

        response = handle_conversation(messages_str)
        print(f"Response: {response}")

        save_message(chat_id, response, "assistant")

        return {"status": "success", "message": response}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

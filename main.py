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

    Basado en el siguiente mensaje del usuario, responde al usuario.
    <message>
    {message}
    </message>
"""

def handle_conversation(message: str):
    print(f"Handling conversation for message: {message}")
    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )

    prompt = SYSTEM_TEMPLATE_CONVERSATION.format(message=message)
    try:
        response = chat_llm.invoke([prompt])
        return response.content
    except Exception as e:
        print(f"Error handling conversation: {e}")
        return "Error handling conversation"

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        now = datetime.now(pytz.timezone("Europe/Madrid"))

        messages_collection.insert_one({"chat_id": chat_id, "message": user_message, "timestamp": now})

        response = handle_conversation(user_message)

        print(f"Response: {response}")

        return {"status": "success", "message": response}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

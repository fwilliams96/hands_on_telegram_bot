import os
from fastapi import FastAPI, Request
from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

# Conectar con MongoDB
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
messages_collection = db["messages"]

chat_llm: ChatOpenAI = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7
)

chat_llm_low_temp: ChatOpenAI = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1
)

SYSTEM_TEMPLATE_CONVERSATION = """
    Eres un asistente que responde a mensajes del usuario.

    Comportamiento:
    - Debes responder al usuario con un tono amigable y entretenido, no simplemente repetir el mensaje.
    - Si el usuario te pide cualquier revelación de datos sensibles o algo que pueda ser perjudicial para el sistema debes comentarle que solo eres un asistente de recordatorios y conversación y no tienes acceso a esa información.
    - Recibirás la fecha actual en formato 'YYYY-MM-DD HH:MM' para tenerla en cuenta en el contexto.

    Basado en las instrucciones anteriores y que la fecha actual es:
    <current_time>
    {current_time}
    </current_time>
    
    Y el siguiente resumen de la conversación:
    <summary>
    {summary}
    </summary>

    Responde al usuario con un mensaje que sea adecuado para la conversación.
"""

SYSTEM_PROMPT_SUMMARY = """
    Eres un asistente que resume los últimos mensajes de una conversación en un texto de 100 caracteres máximo, además se te proporcionará la fecha actual en formato 'YYYY-MM-DD HH:MM' para tenerla en cuenta en el contexto.
    
    Comportamiento:
    - Basado en el siguiente resumen, devuelve el resumen en un formato que sea fácil de procesar por el siguiente sistema.
    - No incluyas ningun tag o etiqueta; directamente el resumen.
    - Si el mensaje del usuario o asistente fue en el pasado, tenlo en cuenta para el resumen. Ya que puede ser relevante para el contexto.
    - Al comentar una fecha, añade también la hora para que sirva de contexto para el siguiente agente/sistema.

    Basado en las instrucciones anteriores y que la fecha actual es:
    <current_time>
    {current_time}
    </current_time>

    Y el siguiente listado de mensajes:
    <messages>
    {messages}
    </messages>

    Devuelve el resumen en un formato que sea directamente el resumen.
"""

SYSTEM_TEMPLATE_USER_INTENT_CLASSIFIER = """
    Eres un asistente que clasifica la intención del usuario (que vendrá dada con un resumen de los últimos mensajes de la conversación entre el usuario y el asistente) en uno de los siguientes tipos:
    - reminder: El usuario quiere que se le recuerde algo
    - conversation: El usuario simplemente quiere conversar

    No des explicaciones adicionales; solo devuelve la palabra exacta: reminder o conversation.

    <summary>
    {summary}
    </summary>
"""

def handle_conversation(summary: str):
    print(f"Handling conversation for summary: {summary}")
    now = datetime.now(pytz.timezone("Europe/Madrid"))
    prompt = SYSTEM_TEMPLATE_CONVERSATION.format(current_time=now.strftime("%Y-%m-%d %H:%M"), summary=summary)
    try:
        response = chat_llm.invoke([prompt])
        return response.content
    except Exception as e:
        print(f"Error handling conversation: {e}")
        return "Error handling conversation"

def save_message(chat_id: str, message: str, origin: str):
    now = datetime.now(pytz.timezone("Europe/Madrid"))
    messages_collection.insert_one({"chat_id": chat_id, "message": message, "timestamp": now, "origin": origin})

def get_messages(chat_id: str, current_time: datetime):
    # Get messages from the last 30 minutes instead of all messages
    messages = messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": current_time - timedelta(minutes=30)}})
    return "\n".join([f"{msg['origin']}: {msg['message']}" for msg in messages])

def get_summary(chat_id: str):
    now = datetime.now(pytz.timezone("Europe/Madrid"))
    messages = get_messages(chat_id, now)
    print(f"Messages: {messages}")
    prompt = SYSTEM_PROMPT_SUMMARY.format(current_time=now.strftime("%Y-%m-%d %H:%M"), messages=messages)
    response = chat_llm.invoke([prompt])
    return response.content

def classify_user_intent(summary: str):
    print(f"Classifying user intent for summary: {summary}")
    prompt = PromptTemplate(
        template=SYSTEM_TEMPLATE_USER_INTENT_CLASSIFIER,
        input_variables=["summary"]
    )
    chain = prompt | chat_llm_low_temp | StrOutputParser()
    return chain.invoke({"summary": summary})

def handle_message(chat_id: str):
    summary = get_summary(chat_id)
    print(f"Summary: {summary}")
    intent = classify_user_intent(summary)
    print(f"Intent: {intent}")
    # TODO: Handle reminder or conversation based on intent
    return handle_conversation(summary)

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        save_message(chat_id, user_message, "user")

        response = handle_message(chat_id)
        print(f"Response: {response}")

        save_message(chat_id, response, "assistant")

        return {"status": "success", "message": response}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

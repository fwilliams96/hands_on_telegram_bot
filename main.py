import os
from fastapi import FastAPI, Request
from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from reminder_extraction import ReminderExtraction

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

# Conectar con MongoDB
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
messages_collection = db["messages"]
reminders_collection = db["reminders"]

chat_llm: ChatOpenAI = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7
)

chat_llm_low_temp: ChatOpenAI = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1
)

TIMEZONE = pytz.timezone("Europe/Madrid")

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

SYSTEM_PROMPT_REMINDER_EXTRACTION = """
    Eres un asistente que extrae información de recordatorios en lenguaje natural, recibirás como entrada un resumen de los últimos mensajes de conversación entre el usuario y agente y además la fecha actual en formato 'YYYY-MM-DD HH:MM'.

    Tu respuesta debe ser un JSON con los siguientes campos:
    - message: El mensaje que se enviará como recordatorio
    - schedule_time: La fecha y hora en la que se programará el recordatorio en el formato 'YYYY-MM-DD HH:MM'

    En caso de que no puedas extraer o el mensaje o el tiempo, devuelve None para el campo que no puedas extraer.

    Aquí te dejo unos ejemplos:

    Ejemplo 1:
    Mensaje: recuerdame a las 16 que tengo que mirar si hay comida
    Respuesta: {{"message": "tengo que mirar si hay comida", "schedule_time": "2025-02-01 16:00"}}

    Ejemplo 2:
    Mensaje: recuerdame que tengo que mirar si hay comida
    Respuesta: {{"message": "tengo que mirar si hay comida", "schedule_time": None}}

    Ejemplo 3:
    Mensaje: recuerdame a las 16
    Respuesta: {{"message": None, "schedule_time": "2025-02-01 16:00"}}

    Basado en las instrucciones anteriores, extrae la fecha, hora y el mensaje de este recordatorio:

    <summary>
    {summary}
    </summary>

    Para ayudarte a generar el recordario correctamente, la fecha actual es:
    <current_time>
    {current_time}
    </current_time>
    La fecha generada tiene que ser siempre posterior a la fecha actual.
"""

def handle_conversation(summary: str):
    print(f"Handling conversation for summary: {summary}")
    now = datetime.now(TIMEZONE)
    prompt = SYSTEM_TEMPLATE_CONVERSATION.format(current_time=now.strftime("%Y-%m-%d %H:%M"), summary=summary)
    try:
        response = chat_llm.invoke([prompt])
        return response.content
    except Exception as e:
        print(f"Error handling conversation: {e}")
        return "Error handling conversation"

def save_message(chat_id: str, message: str, origin: str):
    now = datetime.now(TIMEZONE)
    messages_collection.insert_one({"chat_id": chat_id, "message": message, "timestamp": now, "origin": origin})

def get_messages(chat_id: str, current_time: datetime):
    # Get messages from the last 30 minutes instead of all messages
    messages = messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": current_time - timedelta(minutes=30)}})
    return "\n".join([f"{msg['origin']}: {msg['message']}" for msg in messages])

def get_summary(chat_id: str):
    now = datetime.now(TIMEZONE)
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
    if intent == "reminder":
        return handle_reminder(summary)
    else:
        return handle_conversation(summary)

def handle_reminder(summary: str):
    print(f"Handling reminder with summary: {summary}")
    current_time = datetime.now(TIMEZONE)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M")

    print(f"Current time: {current_time_str}")

    reminder_prompt = SYSTEM_PROMPT_REMINDER_EXTRACTION.format(summary=summary, current_time=current_time_str)
    #print(f"Reminder prompt: {reminder_prompt}")
    llm_structured_output = chat_llm.with_structured_output(ReminderExtraction)

    response: ReminderExtraction = llm_structured_output.invoke([reminder_prompt])
    print(f"Reminder extracted: {response}")
    if response.message is None and response.schedule_time is None:
        return "Mmm... ¿Qué mensaje quieres que te recuerde y en qué fecha y hora?"
    elif response.message is None:
        return "Mmm... ¿Qué mensaje quieres que te recuerde?"
    elif response.schedule_time is None:
        return "Mmm... ¿En qué fecha y hora quieres que te lo recuerde?"
    else:
        reminder_id = save_reminder(response)
        print(f"Reminder saved with ID: {reminder_id}")
        return f"¡Perfecto! Te he programado un recordatorio para el {response.schedule_time}"

def save_reminder(reminder: ReminderExtraction):
    now = datetime.now(TIMEZONE)
    reminder_id = str(reminders_collection.insert_one({"message": reminder.message, "schedule_time": reminder.schedule_time, "timestamp": now, "status": "pending"}).inserted_id)
    return reminder_id

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

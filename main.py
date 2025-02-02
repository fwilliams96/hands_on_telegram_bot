import asyncio
import os
from typing import Optional
from bson import ObjectId
from fastapi import BackgroundTasks, FastAPI, Request
from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from reminder_extraction import ReminderExtraction

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

# Configurar APScheduler
#scheduler = BackgroundScheduler()
scheduler = AsyncIOScheduler()
scheduler.configure(timezone="Europe/Madrid")
scheduler.start()

bot = Bot(token=TELEGRAM_BOT_TOKEN)

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

SYSTEM_PROMPT_REMINDER_MODELING = """
    Eres un asistente de Telegram que se encarga de enviar recordatorios a un usuario en Telegram.

    Comportamiento:
    - Se te proporcionará el mensaje de recordatorio escrito por el usuario tal cual.
    - Debes modelar el recordatorio al usuario con un tono cómico y entretenido, no simplemente repetir el mensaje.

    Aquí te dejo un ejemplo:

    Recordatorio: Tengo que ver si tengo comida o no
    Respuesta: ¡Oye! Me comentaste que te recordara que tenías que ver si tenías comida o no. ¡No te olvides de revisarlo!

    Basado en el ejemplo anterior, modela el siguiente recordatorio:

    <reminder>
    {reminder}
    </reminder>
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
    messages_collection.insert_one({"chat_id": chat_id, "message": message, "timestamp": now, "origin": origin, "processed": False})

def get_messages(chat_id: str, processed: Optional[bool] = None, origin: Optional[str] = None):
    now = datetime.now(TIMEZONE)
    # Get messages from the last 30 minutes instead of all messages
    if processed is None and origin is None:
        return list(messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": now - timedelta(minutes=30)}}))
    elif processed is None and origin is not None:
        return list(messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": now - timedelta(minutes=30)}, "origin": origin}))
    elif processed is not None and origin is None:
        return list(messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": now - timedelta(minutes=30)}}))
    elif processed is not None and origin is not None:
        return list(messages_collection.find({"chat_id": chat_id, "timestamp": {"$gte": now - timedelta(minutes=30)}, "processed": processed, "origin": origin}))

def get_summary(messages: list):
    print(f"Getting summary for messages: {messages}")
    now = datetime.now(TIMEZONE)
    # Generate copy of messages to be able to return it
    messages_str = "\n".join([f"{msg['origin']}: {msg['message']}" for msg in messages])
    print(f"Messages str: {messages_str}")
    prompt = SYSTEM_PROMPT_SUMMARY.format(current_time=now.strftime("%Y-%m-%d %H:%M"), messages=messages_str)
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

async def handle_message(chat_id: str, user_message: str):
    save_message(chat_id, user_message, "user")

    # Get summary and messages from the last 30 minutes that are not processed and from the user origin
    messages = get_messages(chat_id=chat_id, processed=False, origin="user")
    summary = get_summary(messages)
    print(f"Summary: {summary}")
    print(f"Messages: {messages}")
    intent = classify_user_intent(summary)
    print(f"Intent: {intent}")
    response = None
    if intent == "reminder":
        response = handle_reminder(summary, messages)
    else:
        # Get summary and messages from the last 30 minutes no matter if they are processed or not (important for the context) and from all origins
        messages = get_messages(chat_id=chat_id)
        summary = get_summary(messages)
        response = handle_conversation(summary)

    if response:
        await send_telegram_message(response)
        save_message(chat_id, response, "assistant")

def handle_reminder(summary: str, messages: list):
    print(f"Handling reminder with summary: {summary} and messages: {messages}")
    current_time = datetime.now(TIMEZONE)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M")

    print(f"Current time: {current_time_str}")

    reminder_prompt = SYSTEM_PROMPT_REMINDER_EXTRACTION.format(summary=summary, current_time=current_time_str)
    #print(f"Reminder prompt: {reminder_prompt}")
    llm_structured_output = chat_llm.with_structured_output(ReminderExtraction)

    reminder_extraction: ReminderExtraction = llm_structured_output.invoke([reminder_prompt])
    print(f"Reminder extracted: {reminder_extraction}")
    if reminder_extraction.message is None and reminder_extraction.schedule_time is None:
        return "Mmm... ¿Qué mensaje quieres que te recuerde y en qué fecha y hora?"
    elif reminder_extraction.message is None:
        return "Mmm... ¿Qué mensaje quieres que te recuerde?"
    elif reminder_extraction.schedule_time is None:
        return "Mmm... ¿En qué fecha y hora quieres que te lo recuerde?"
    else:
        reminder_id = save_reminder(reminder_extraction)
        print(f"Reminder saved with ID: {reminder_id}")
        enable_reminder(reminder_extraction,reminder_id)
        mark_messages_as_processed(messages)
        return f"¡Perfecto! Te he programado un recordatorio para el {reminder_extraction.schedule_time}"

def mark_messages_as_processed(messages: list):
    # Update all messages for the chat_id as processed
    print(f"Marking messages as processed: {messages}")
    for message in messages:
        messages_collection.update_one({"_id": message["_id"]}, {"$set": {"processed": True}})

def save_reminder(reminder: ReminderExtraction):
    now = datetime.now(TIMEZONE)
    reminder_id = str(reminders_collection.insert_one({"message": reminder.message, "schedule_time": reminder.schedule_time, "timestamp": now, "status": "pending"}).inserted_id)
    return reminder_id

def enable_reminder(reminder_extraction: ReminderExtraction, reminder_id: str):
    print(f"Enabling reminder with ID: {reminder_id}")
    reminder_time = datetime.strptime(reminder_extraction.schedule_time, "%Y-%m-%d %H:%M")
    # Schedule the reminder with APScheduler
    scheduler.add_job(
        trigger_reminder,
        'date',
        run_date=reminder_time,
        args=[reminder_id],
        id=reminder_id,
        replace_existing=True
    )

# Function that will be executed when the reminder is triggered
async def trigger_reminder(reminder_id: str):
    print(f"Triggering reminder {reminder_id}")
    try:
        reminder = reminders_collection.find_one({"_id": ObjectId(reminder_id)})
        print(f"Reminder found: {reminder}")
        if reminder:
            print(f"Sending reminder: {reminder['message']}")
            success = await send_reminder(reminder["message"])
            
            # Update the status based on the result
            status = "sent" if success else "failed"
            reminders_collection.update_one(
                {"_id": ObjectId(reminder_id)}, 
                {"$set": {
                    "status": status,
                    "last_attempt": datetime.now(),
                    "error": None if success else "Timeout error"
                }}
            )
    except Exception as e:
        print(f"Error in trigger_reminder: {e}")

async def send_reminder(original_reminder: str):
    print(f"Generating reminder message with OpenAI based on reminder: {original_reminder}")
    llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )

    reminder_prompt = SYSTEM_PROMPT_REMINDER_MODELING.format(reminder=original_reminder)
    reminder = None

    try:
        response = await llm.ainvoke([reminder_prompt])
        reminder = response.content
    except Exception as e:
        print(f"Error generating reminder with OpenAI: {e}")
        return False
    
    print(f"Reminder generated: {reminder}")

    status = await send_telegram_message(reminder)
    return status

async def send_telegram_message(message: str, max_retries: int = 3):
    print(f"Sending message to Telegram: {message}")
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID, 
                text=message,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30
            )
            print(f"Message sent to Telegram successfully: {message}")
            return True
        except Exception as e:
            print(f"Retry {attempt + 1}/{max_retries} - Error sending message to Telegram: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                print("All retries failed to send the message")
                return False

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        background_tasks.add_task(handle_message, chat_id, user_message)

        return {"status": "success", "message": "Message received successfully"}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

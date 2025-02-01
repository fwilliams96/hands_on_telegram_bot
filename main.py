from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId
from fastapi import BackgroundTasks, FastAPI, Request
from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
from telegram import Bot
import os
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from reminder_extraction import ReminderExtraction
from datetime import datetime, timedelta, timezone
import pytz

load_dotenv()

# Configuración
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Conectar con MongoDB
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
reminders_collection = db["reminders"]
messages_collection = db["messages"]

# Configurar APScheduler
#scheduler = BackgroundScheduler()
scheduler = AsyncIOScheduler()
scheduler.configure(timezone="Europe/Madrid")
scheduler.start()

SYSTEM_PROMPT_SUMMARY = """
    Eres un asistente que resume los últimos mensajes del usuario en un resumen de 100 caracteres máximo.
    Basado en el siguiente resumen, devuelve el resumen en un formato que sea fácil de procesar por el siguiente sistema.
    No incluyas ningun tag o etiqueta; directamente el resumen.
    <messages>
    {messages}
    </messages>
"""

SYSTEM_TEMPLATE_USER_INTENT_CLASSIFIER = """
    Eres un asistente que clasifica la intención del usuario (que vendrá dada con un resumen de los últimos mensajes del usuario) en uno de los siguientes tipos:
    - reminder: El usuario quiere que se le recuerde algo
    - conversation: El usuario simplemente quiere conversar

    No des explicaciones adicionales; solo devuelve la palabra exacta: reminder o conversation.

    <summary>
    {summary}
    </summary>
"""

SYSTEM_TEMPLATE_CONVERSATION = """
    Eres un asistente que responde a mensajes del usuario.

    Comportamiento:
    - Debes responder al usuario con un tono amigable y entretenido, no simplemente repetir el mensaje.
    - Si el usuario te pide cualquier revelación de datos sensibles o algo que pueda ser perjudicial para el sistema debes comentarle que solo eres un asistente de recordatorios y conversación y no tienes acceso a esa información.

    Basado en el siguiente resumen de los últimos mensajes del usuario, responde al usuario.
    <summary>
    {summary}
    </summary>
"""

SYSTEM_PROMPT_REMINDER_EXTRACTION = """
Eres un asistente que extrae información de recordatorios en lenguaje natural, recibirás como entrada un resumen de los últimos mensajes del usuario y además la fecha actual en formato 'YYYY-MM-DD HH:MM'.

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

Para ayudarte a generar el recordario correctamente, la hora actual es:
<current_time>
{current_time}
</current_time>
La fecha generada tiene que ser siempre posterior a la fecha actual.
"""

SYSTEM_PROMPT_REMINDER = """
Eres un asistente de Telegram que se encarga de enviar recordatorios a un usuario en Telegram.

Comportamiento:
- Se te proporcionará el mensaje de recordatorio escrito por el usuario tal cual.
- Debes modelar el recordatorio al usuario con un tono cómico y entretenido, no simplemente repetir el mensaje.

Aquí te dejo un ejemplo:

Recordatorio: Tengo que ver si tengo comida o no
Respuesta: ¡Oye! Me comentaste que te recordara que tenías que ver si tenías comida o no. ¡No te olvides de revisarlo!

Basado en el ejemplo anterior, modela el siguiente recordatorio:

<recordatorio>
{recordatorio}
</recordatorio>
"""

GENERAL_ERROR_MESSAGE = "Ups, parece que he tenido un fallo. ¿Que me decías?"

async def send_reminder(original_reminder: str):
    print(f"Generating reminder message with OpenAI based on reminder: {original_reminder}")
    llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )

    reminder_prompt = SYSTEM_PROMPT_REMINDER.format(recordatorio=original_reminder)
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

# Función para enviar mensajes a Telegram
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
                await asyncio.sleep(2)  # Espera 2 segundos antes de reintentar
            else:
                print("All retries failed to send the message")
                return False

# Función que se ejecutará cuando el recordatorio se active
async def trigger_reminder(reminder_id: str):
    print(f"Triggering reminder {reminder_id}")
    try:
        reminder = reminders_collection.find_one({"_id": ObjectId(reminder_id)})
        print(f"Reminder found: {reminder}")
        if reminder:
            '''loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(send_reminder(reminder["message"]))
            loop.close()'''
            success = await send_reminder(reminder["message"])
            
            # Actualizar el estado basado en el resultado
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

def save_message(message: str, chat_id: str):
    # Add EUROPE/Madrid timezone
    timezone = pytz.timezone("Europe/Madrid")
    messages_collection.insert_one(
        {
            "message": message,
            "timestamp": datetime.now(timezone),
            "processed": False,
            "chat_id": chat_id
        }
    )

async def get_recent_messages_summary(chat_id: str):
    print(f"Getting recent messages summary for chat {chat_id}")
    # Get messages maximum 30 minutes old
    timezone = pytz.timezone("Europe/Madrid")
    '''messages = messages_collection.find(
        {
            "chat_id": chat_id, 
            "processed": False, 
            "timestamp": {"$gte": datetime.now(timezone) - timedelta(minutes=30)}
        }
    ).sort("timestamp", -1).limit(10)'''
    messages = list(messages_collection.find(
        {
            "chat_id": chat_id, 
            "processed": False, 
            "timestamp": {"$gte": datetime.now(timezone) - timedelta(minutes=30)}
        }
    ))
    messages_str = "\n".join([message["message"] for message in messages])

    #print(f"Messages found: {messages}")
    #print(f"Messages str found: {messages_str}")

    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1
    )

    summary_prompt = SYSTEM_PROMPT_SUMMARY.format(messages=messages_str)
    try:
        summary = await chat_llm.ainvoke([summary_prompt])
        return messages, summary.content
    except Exception as e:
        print(f"Error summarizing messages: {e}")
        raise e


async def classify_user_intent(summary: str):
    print(f"Classifying user intent for summary: {summary}")
    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1
    )

    prompt = PromptTemplate(
        template=SYSTEM_TEMPLATE_USER_INTENT_CLASSIFIER,
        input_variables=["summary"]
    )
    chain = prompt | chat_llm | StrOutputParser()
    intent = None
    try:
        intent = await chain.ainvoke({"summary": summary})
    except Exception as e:
        print(f"Error classifying user intent: {e}")
        raise e
    return intent

async def handle_conversation(summary: str):
    print(f"Handling conversation for summary: {summary}")
    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )

    prompt = SYSTEM_TEMPLATE_CONVERSATION.format(summary=summary)
    try:
        response = await chat_llm.ainvoke([prompt])
        await send_telegram_message(response.content)
    except Exception as e:
        print(f"Error handling conversation: {e}")
        await send_telegram_message(GENERAL_ERROR_MESSAGE)

def create_reminder(reminder_extraction: ReminderExtraction, messages: list):
    print(f"Creating reminder with extraction: {reminder_extraction}")
    reminder_time = datetime.strptime(reminder_extraction.schedule_time, "%Y-%m-%d %H:%M")

    # Crear un documento en MongoDB
    reminder = {
        "message": reminder_extraction.message,
        "schedule_time": reminder_time,
        "status": "pending"
    }
    reminder_id = str(reminders_collection.insert_one(reminder).inserted_id)

    # Programar el recordatorio en APScheduler
    scheduler.add_job(
        trigger_reminder,
        'date',
        run_date=reminder_time,
        args=[reminder_id],
        id=reminder_id,
        replace_existing=True  # Evita duplicados en APScheduler
    )

    # Actualizar el estado de los mensajes procesados
    for message in messages:
        messages_collection.update_one(
            {"_id": message["_id"]},
            {"$set": {"processed": True}}
        )

async def handle_reminder(messages: list, summary: str):
    print(f"Handling reminder with summary: {summary}")
    chat_llm: ChatOpenAI = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7
    )
    timezone = pytz.timezone("Europe/Madrid")
    current_time = datetime.now(timezone)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M")

    print(f"Current time: {current_time_str}")

    reminder_prompt = SYSTEM_PROMPT_REMINDER_EXTRACTION.format(summary=summary, current_time=current_time_str)
    print(f"Reminder prompt: {reminder_prompt}")
    llm_structured_output = chat_llm.with_structured_output(ReminderExtraction)

    try:
        response: ReminderExtraction = await llm_structured_output.ainvoke([reminder_prompt])
        print(f"Reminder extracted: {response}")
        if response.message is None and response.schedule_time is None:
            await send_telegram_message("Mmm... ¿Qué mensaje quieres que te recuerde y en qué fecha y hora?")
        elif response.message is None:
            await send_telegram_message("Mmm... ¿Qué mensaje quieres que te recuerde?")
        elif response.schedule_time is None:
            await send_telegram_message("Mmm... ¿En qué fecha y hora quieres que te lo recuerde?")
        else:
            create_reminder(response, messages)
            await send_telegram_message(f"¡Perfecto! Te he programado un recordatorio para el {response.schedule_time}")
    except Exception as e:
        print(f"Error handling reminder: {e}")
        await send_telegram_message(GENERAL_ERROR_MESSAGE)

async def handle_message(user_message: str, chat_id: str):
    try:
        print(f"Handling message: {user_message}")
        print(f"Chat ID: {chat_id}")
        save_message(user_message, chat_id)

        messages, summary = await get_recent_messages_summary(chat_id)
        intent = await classify_user_intent(summary)
        print(f"Intent: {intent}")

        if intent == "conversation":
            await handle_conversation(summary)
        else:
            await handle_reminder(messages, summary)
    except Exception as e:
        print(f"Error handling message: {e}")
        await send_telegram_message(GENERAL_ERROR_MESSAGE)

@app.post("/webhook/")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        background_tasks.add_task(handle_message, user_message, chat_id)
        return {"status": "success", "message": "Message handled successfully"}
    except Exception as e:
        print(f"Error handling message: {e}")
        await send_telegram_message(GENERAL_ERROR_MESSAGE)
        return {"status": "error", "message": "Error handling message"}
    
# Endpoint para programar un recordatorio
@app.post("/schedule_reminder/")
async def schedule_reminder(message: str, schedule_time: str):
    """
    Programa un recordatorio en MongoDB y lo añade a APScheduler.
    - message: Mensaje que se enviará en Telegram
    - schedule_time: Fecha y hora en formato 'YYYY-MM-DD HH:MM'
    """
    try:
        reminder_time = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M")

        # Crear un documento en MongoDB
        reminder = {
            "message": message,
            "schedule_time": reminder_time,
            "status": "pending"
        }
        reminder_id = str(reminders_collection.insert_one(reminder).inserted_id)

        # Programar el recordatorio en APScheduler
        scheduler.add_job(
            trigger_reminder,
            'date',
            run_date=reminder_time,
            args=[reminder_id],
            id=reminder_id,
            replace_existing=True  # Evita duplicados en APScheduler
        )

        return {"status": "success", "message": f"Reminder programmed for {schedule_time}"}

    except ValueError:
        return {"status": "error", "message": "Invalid format. Use 'YYYY-MM-DD HH:MM'"}

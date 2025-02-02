import os
from fastapi import FastAPI, Request
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

        return {"status": "success", "message": "Message handled successfully"}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        print(f"Received message: {user_message}")
        print(f"Chat ID: {chat_id}")

        return {"status": "success", "message": "Message handled successfully"}
    except Exception as e:
        print(f"Error handling message: {e}")
        return {"status": "error", "message": "Error handling message"}

# Reminder Telegram Bot

## Introduction

This is a Telegram bot that chats with the user and creates reminders using APScheduler, it uses a MongoDB database to store the reminders and the conversation history and OpenAI to generate the responses to the user through the Langchain library.

## How to run in local

### Create the Telegram bot

First, create a Telegram bot using the BotFather. Open the Telegram app and search for the BotFather. Send the `/start` command and then `/newbot` to create a new bot.
You can find more information [here](https://core.telegram.org/bots/tutorial).
Make sure you save your bot token.

### Obtain the chat ID

Send a message to your new bot and then go to the url `https://api.telegram.org/bot<bot_token>/getUpdates` to get the chat ID from the response.
You can find more information [here](https://core.telegram.org/bots/api#getting-a-chat-id).

### Install Python

First, install Python 3.9 or higher. You can download it from [here](https://www.python.org/downloads/).

### Create a virtual environment

```bash
python3.9 -m venv env
source env/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```
Or

```bash
pip install fastapi uvicorn pymongo apscheduler python-telegram-bot python-dotenv langchain langchain-openai pytz
```

### Run

First, run the MongoDB container with the following command:
```bash
docker-compose -f docker-compose-mongo.yml up -d
```
And then run the bot with the following command:

```bash
uvicorn main:app --reload
```

### Expose the bot to the internet (create an account on ngrok and run the following command)

```bash
ngrok http 8000
```

And get your ngrok url, for example: `https://5539-84-17-62-141.ngrok-free.app`

### Set the webhook

```bash
curl -X POST "https://api.telegram.org/bot<bot_token>/setWebhook?url=<ngrok_url>/webhook"
```

### Test the bot

Send a message to your bot on Telegram and check the logs of the server to see the response, enjoy!

## Improvements

- Modify/delete reminders
- Add more options, like summarizing your last emails, or your last messages, etc.
- Allow the bot to retrieve all your reminders and show them to you in a structured way.
- Implement RAG to retrieve a specific reminder using natural language.
- Integrate the reminders with your Google Calendar.

## Possible issues

- If you have ISP issues while accessing to the Telegram API, you can use a VPN or your mobile data.










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

## Hands-on to learn how to build the bot step by step

1. Branch step_1: Setting up the environment and running main.py with a hello world

2. Branch step_2: Creating fastapi and basic endpoint /webhook (Telegram request-oriented structure) -> installing fastapi uvicorn python-dotenv

3. Branch step_3: Saving received message in mongodb -> installing pymongo

4. Branch step_4: Integrate genai to have conversation (last message) -> install langchain langchain-openai

5. Branch step_5: Modify previous genai agent to read all messages instead of just the last one and save assistant message

6. Branch step_6: Integrate another genai agent to summarize messages from the last 30 minutes and modify existing agent so that receives a summary instead of all messages

7. Branch step_7: Integrate another genai agent to detect if it is a conversation or a reminder

8. Branch step_8: Integrate genai agent to ask for all the necessary information for the reminder

9. Branch step_9: Save reminder in mongodb

10. Branch step_10: Run reminder with Apscheduler -> install apscheduler

11. Branch step_11: Change initial summary so only to include non-processed messages and sent by the user, and the summary for the conversation to be of the entire conversation.

12. Branch step_12: Integrate Telegram so that it sends the message to Telegram instead of just returning it in the API -> install python-telegram-bot

13. Branch step_13: Perform the entire process in a BackgroundTask and have the API return 200 as soon as it enters

14. Branch step_14: Configure a webhook to Telegram so that the bot can be tested from the Telegram App (ngrok) add handling of errors (try/except)
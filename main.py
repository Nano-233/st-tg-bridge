from fastapi import FastAPI, Request
import httpx
import os
import json

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ST_URL = os.getenv("ST_URL").rstrip("/")  # e.g. https://japanese.zeabur.app
CHARACTER_NAME = os.getenv("CHARACTER_NAME", "Haruka")  # your character name

async def send_to_sillytavern(message: str, user_id: str):
    payload = {
        "input": message,
        "character": CHARACTER_NAME,
        "user": "Nano"  # your user name
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{ST_URL}/api/chat", json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "Sorry, I didn't get that 💦")
    return "Error connecting to SillyTavern 😵"

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "message" in data:
        msg = data["message"]
        text = msg.get("text")
        chat_id = msg["chat"]["id"]
        
        if text and text.startswith("/"):
            # handle commands if you want
            pass
        elif text:
            reply = await send_to_sillytavern(text, str(chat_id))
            # send reply back to Telegram
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": reply}
                )
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "SillyTavern Telegram bridge is running"}

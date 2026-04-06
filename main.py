import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = (
    os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN", "")
).strip()
# ChatBridge: base ends with /v1 — we POST .../v1/chat/completions
ST_URL = os.environ.get("ST_URL", "").strip().rstrip("/")
CHATBRIDGE_API_KEY = os.environ.get("CHATBRIDGE_API_KEY", "your-user-api-key")
CHARACTER_NAME = os.environ.get("CHARACTER_NAME", "")
USER_NAME = os.environ.get("USER_NAME", "TelegramUser")
ST_MODEL = os.environ.get("ST_MODEL", "gpt-3.5-turbo")
# Zeabur injects ZEABUR_WEB_URL for the deployed service (Git → port "web")
WEBHOOK_URL = (
    os.environ.get("WEBHOOK_URL") or os.environ.get("ZEABUR_WEB_URL", "")
).rstrip("/")


def _st_openai_base() -> str:
    """Ensure ChatBridge path .../v1 when ST_URL is given as origin only."""
    if not ST_URL:
        return ""
    if ST_URL.endswith("/v1"):
        return ST_URL
    return f"{ST_URL}/v1"


def _legacy_api_chat_url() -> str | None:
    if not ST_URL:
        return None
    p = urlparse(ST_URL)
    return urlunparse((p.scheme, p.netloc, "/api/chat", "", "", ""))


async def send_to_sillytavern(user_message: str) -> str:
    async with httpx.AsyncClient(timeout=90.0) as client:
        # 1) SillyTavern Extension ChatBridge (OpenAI-compatible)
        st_openai = _st_openai_base()
        if st_openai:
            openai_endpoint = f"{st_openai}/chat/completions"
            try:
                resp = await client.post(
                    openai_endpoint,
                    json={
                        "model": ST_MODEL,
                        "messages": [{"role": "user", "content": user_message}],
                        "stream": False,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {CHATBRIDGE_API_KEY}",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices:
                        msg = choices[0].get("message") or {}
                        content = msg.get("content")
                        if content and len(str(content).strip()) > 0:
                            return str(content)
                elif resp.status_code not in (404, 405):
                    logger.warning(
                        "ChatBridge-style POST %s -> %s %s",
                        openai_endpoint,
                        resp.status_code,
                        resp.text[:200],
                    )
            except Exception:
                logger.exception("ChatBridge request failed for %s", openai_endpoint)

        # 2) Some setups expose /api/chat on the server origin (not /v1)
        payloads = [
            {
                "input": user_message,
                "character": CHARACTER_NAME,
                "user": USER_NAME,
            },
            {
                "prompt": user_message,
                "character": CHARACTER_NAME,
                "user": USER_NAME,
                "max_new_tokens": 300,
                "temperature": 0.85,
            },
        ]
        legacy = _legacy_api_chat_url()
        if legacy:
            for payload in payloads:
                try:
                    resp = await client.post(
                        legacy,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        reply = (
                            data.get("response")
                            or data.get("result")
                            or data.get("text")
                            or str(data)
                        )
                        return (
                            reply
                            if isinstance(reply, str) and len(reply) > 5
                            else "……ちょっと待ってね💦"
                        )
                except Exception:
                    logger.debug("Legacy /api/chat payload failed", exc_info=True)

    return "ごめん、今ちょっと接続が不安定みたい……もう一度言ってみて？"


telegram_app: Application | None = None


async def _on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    reply = await send_to_sillytavern(update.message.text)
    await update.message.reply_text(reply)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if not BOT_TOKEN:
        logger.error(
            "Set BOT_TOKEN or TELEGRAM_TOKEN; Telegram will not work without it."
        )
        yield
        return

    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text)
    )
    await telegram_app.initialize()
    await telegram_app.start()
    if WEBHOOK_URL:
        wh = f"{WEBHOOK_URL}/telegram/webhook"
        await telegram_app.bot.set_webhook(url=wh)
        logger.info("Telegram webhook set to %s", wh)
    else:
        logger.warning(
            "No WEBHOOK_URL or ZEABUR_WEB_URL: Telegram webhook not set. "
            "Set WEBHOOK_URL to this service's public https URL, or deploy on Zeabur "
            "so ZEABUR_WEB_URL is available."
        )
    yield
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
        telegram_app = None


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health() -> dict:
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> Response:
    if not telegram_app:
        return Response(status_code=503)
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)

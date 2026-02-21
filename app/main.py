"""
Application entry point.
FastAPI: POST /webhook — Telegram webhook
Flask-Admin: /admin via WSGIMiddleware
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.wsgi import WSGIMiddleware

import config as cfg
from bot.router import setup_routers
from db.session import async_engine
from scheduler.tasks import setup_scheduler
from web.app import create_flask_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot + dispatcher
# ---------------------------------------------------------------------------
bot = Bot(
    token=cfg.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    setup_routers(dp)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    # Self-signed SSL cert (mounted from VPS host)
    cert_path = Path("/etc/ssl/webhook_cert.pem")
    await bot.set_webhook(
        url=cfg.WEBHOOK_URL,
        secret_token=cfg.WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
        certificate=FSInputFile(str(cert_path)) if cert_path.exists() else None,
    )
    logger.info("Webhook set: %s", cfg.WEBHOOK_URL)

    yield

    # --- Shutdown ---
    scheduler.shutdown(wait=False)
    await bot.delete_webhook()
    await bot.session.close()
    await async_engine.dispose()
    logger.info("Application stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

# Flask-Admin at /admin
flask_app = create_flask_app()
app.mount("/admin", WSGIMiddleware(flask_app))


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
) -> dict:
    if x_telegram_bot_api_secret_token != cfg.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    body = await request.json()

    from aiogram.types import Update
    update = Update.model_validate(body)
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )

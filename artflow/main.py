# main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import redis.asyncio as aioredis

from api.comet_client import close_client, get_client
from bot.handlers import admin, balance, image_gen, marketplace, payment, start, video_gen
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from core.config import settings
from core.logger import setup_logging
from db.session import engine
from db.models import Base
from payments.cryptobot import verify_webhook_signature
from db import repository as repo
from db.seed import run_seed
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Global instances ──────────────────────────────────────────────────────────

bot: Bot | None = None
dp: Dispatcher | None = None
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, redis_client
    setup_logging()

    # Redis
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Bot + Dispatcher
    storage = RedisStorage(redis=redis_client)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middlewares (порядок важен)
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AuthMiddleware())
    dp.message.middleware(ThrottlingMiddleware(redis_client))

    # Routers
    dp.include_router(start.router)
    dp.include_router(image_gen.router)
    dp.include_router(video_gen.router)
    dp.include_router(balance.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(marketplace.router)
    dp.include_router(marketplace.mod_router)

    # DB tables (для prod используй alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_seed()

    # Webhook
    webhook_url = f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
    )
    logger.info("Webhook set: %s", webhook_url)

    # Warm up CometAPI client
    get_client()

    yield

    # Shutdown
    await bot.delete_webhook()
    await close_client()
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(title="ArtFlow AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Telegram Webhook ──────────────────────────────────────────────────────────

@app.post(settings.WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()
    update = Update.model_validate(body)
    await dp.feed_update(bot, update)  # type: ignore[arg-type]
    return {"ok": True}


# ── CryptoBot Webhook ─────────────────────────────────────────────────────────

@app.post("/webhook/cryptobot")
async def cryptobot_webhook(request: Request) -> dict:
    body_bytes = await request.body()
    check_hash = request.headers.get("crypto-pay-api-signature", "")

    if not verify_webhook_signature(settings.CRYPTOBOT_TOKEN, body_bytes, check_hash):
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    if data.get("update_type") != "invoice_paid":
        return {"ok": True}

    payload: str = data["payload"]["payload"]  # "plan_key:user_id"
    external_id = str(data["payload"]["invoice_id"])

    async with AsyncSessionLocal() as session:
        tx = await repo.confirm_transaction(session, external_id)
        if tx:
            new_balance = await repo.add_credits(session, tx.user_id, tx.credits)
            # Уведомляем пользователя
            user = await repo.get_user_by_id(session, tx.user_id)
            if user and bot:
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"✅ Оплата криптой подтверждена!\n"
                        f"Зачислено: <b>+{tx.credits} кредитов</b>\n"
                        f"Баланс: <b>{new_balance} кр</b>",
                    )
                except Exception as e:
                    logger.warning("Failed to notify user %s: %s", user.tg_id, e)

    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "artflow-ai"}

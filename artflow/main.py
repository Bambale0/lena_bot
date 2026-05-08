# main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update, URLInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

import redis.asyncio as aioredis

from api.comet_client import close_client, get_client
from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_success
from api.music_service import extract_music_urls, pop_task
from api.public_files import UPLOAD_ROOT, mirror_url
from bot.handlers import admin, balance, feed, image_gen, marketplace, midjourney, music_gen, payment, start, video_gen
from bot.keyboards.main_menu import back_to_menu_kb
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.utils.telegram_ui import is_benign_telegram_error
from core.config import settings
from core.logger import setup_logging
from db.models import GenerationType, TransactionStatus
from payments.cryptobot import verify_webhook_signature
from payments.tbank import verify_notification_token
from db import repository as repo
from db.seed import run_seed
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _accrue_referral_commissions(session, user: "User", amount_rub: float) -> None:
    """Начисляет реферальные комиссии с платежа по трём линиям."""
    pairs = [
        (user.referrer_id, settings.REFERRAL_COMMISSION_L1),
        (user.referrer_l2_id, settings.REFERRAL_COMMISSION_L2),
        (user.referrer_l3_id, settings.REFERRAL_COMMISSION_L3),
    ]
    for ref_id, pct in pairs:
        if not ref_id or pct <= 0:
            continue
        commission = round(amount_rub * pct, 2)
        await repo.add_referral_balance(session, ref_id, commission)
        referrer = await repo.get_user_by_id(session, ref_id)
        if referrer and bot:
            try:
                await bot.send_message(
                    referrer.tg_id,
                    f"💰 Реферальная комиссия: <b>+{commission:.2f}₽</b>\n"
                    f"Один из рефералов пополнил баланс на {amount_rub:.0f}₽.",
                )
            except Exception:
                pass
        logger.info("Referral commission %.2f₽ -> user_id=%s (%.0f%%)", commission, ref_id, pct * 100)


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
    dp.include_router(feed.router)
    dp.include_router(image_gen.router)
    dp.include_router(video_gen.router)
    dp.include_router(music_gen.router)
    dp.include_router(midjourney.router)
    dp.include_router(balance.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(marketplace.router)
    dp.include_router(marketplace.mod_router)

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
    logger.info("Shutdown complete")


app = FastAPI(title="APIX", lifespan=lifespan)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount(settings.STATIC_UPLOAD_URL_PATH, StaticFiles(directory=str(UPLOAD_ROOT)), name="static_upload")

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
    try:
        await dp.feed_update(bot, update)  # type: ignore[arg-type]
    except TelegramBadRequest as e:
        if is_benign_telegram_error(e):
            logger.debug("Ignoring benign Telegram callback error: %s", e)
            return {"ok": True}
        raise
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
            user = await repo.get_user_by_id(session, tx.user_id)
            if user:
                await _accrue_referral_commissions(session, user, tx.amount_rub)
                if bot:
                    try:
                        await bot.send_message(
                            user.tg_id,
                            f"✅ Оплата криптой подтверждена!\n"
                            f"Зачислено: <b>+{tx.credits} 💋</b>\n"
                            f"Баланс: <b>{new_balance} 💋</b>",
                            reply_markup=back_to_menu_kb(),
                        )
                    except Exception as e:
                        logger.warning("Failed to notify user %s: %s", user.tg_id, e)

    return {"ok": True}


@app.post("/webhook/tbank")
async def tbank_webhook(request: Request) -> PlainTextResponse:
    data = await request.json()

    if not verify_notification_token(data, settings.TBANK_PASSWORD):
        logger.warning(
            "Invalid T-Bank webhook token: payment_id=%s status=%s order_id=%s",
            data.get("PaymentId"),
            data.get("Status"),
            data.get("OrderId"),
        )
        raise HTTPException(status_code=403, detail="Invalid token")

    if not data.get("Success"):
        return PlainTextResponse("OK")

    status = str(data.get("Status", ""))
    external_id = str(data.get("PaymentId", ""))
    if not external_id:
        raise HTTPException(status_code=400, detail="PaymentId is required")

    async with AsyncSessionLocal() as session:
        if status == "CONFIRMED":
            tx = await repo.confirm_transaction(session, external_id)
            if tx:
                new_balance = await repo.add_credits(session, tx.user_id, tx.credits)
                user = await repo.get_user_by_id(session, tx.user_id)
                if user:
                    await _accrue_referral_commissions(session, user, tx.amount_rub)
                    if bot:
                        try:
                            await bot.send_message(
                                user.tg_id,
                                f"✅ Оплата через T-Банк подтверждена!\n"
                                f"Зачислено: <b>+{tx.credits} 💋</b>\n"
                                f"Баланс: <b>{new_balance} 💋</b>",
                                reply_markup=back_to_menu_kb(),
                            )
                        except Exception as e:
                            logger.warning("Failed to notify user %s: %s", user.tg_id, e)
        elif status in {"CANCELED", "CANCELLED", "REJECTED", "DEADLINE_EXPIRED", "AUTH_FAIL"}:
            await repo.set_transaction_status(session, external_id, TransactionStatus.failed)
        elif status in {"REFUNDED", "REVERSED", "PARTIAL_REVERSED"}:
            await repo.set_transaction_status(session, external_id, TransactionStatus.refunded)

    return PlainTextResponse("OK")



# ── KIE.AI Webhook ────────────────────────────────────────────────────────────

@app.post(settings.KIE_WEBHOOK_PATH)
async def kie_webhook(request: Request, secret: str | None = None) -> dict:
    if settings.KIE_WEBHOOK_SECRET and secret != settings.KIE_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid KIE webhook secret")

    payload = await request.json()
    task_id = extract_task_id(payload)
    if not task_id:
        logger.warning("KIE webhook without task_id: %s", payload)
        return {"ok": True}

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_task_id(session, task_id)
        if not gen:
            logger.warning("KIE webhook for unknown task_id=%s", task_id)
            return {"ok": True}

        # Idempotency: if already finished, acknowledge duplicate callback.
        if gen.status.value in {"done", "failed"}:
            return {"ok": True}

        user = await repo.get_user_by_id(session, gen.user_id)
        if not user:
            logger.warning("KIE webhook user not found for generation=%s", gen.id)
            return {"ok": True}

        if not is_success(payload):
            err = extract_error(payload)
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"❌ Генерация не удалась.\nКредиты возвращены.\n\n<code>{err[:500]}</code>",
                        reply_markup=back_to_menu_kb(),
                    )
                except Exception as e:
                    logger.warning("Failed to notify KIE failure user=%s: %s", user.tg_id, e)
            return {"ok": True}

        urls = extract_result_urls(payload)
        if not urls:
            err = "KIE callback success but no result urls"
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(user.tg_id, f"❌ {err}. Кредиты возвращены.", reply_markup=back_to_menu_kb())
                except Exception as e:
                    logger.warning("Failed to notify empty KIE result user=%s: %s", user.tg_id, e)
            return {"ok": True}

        try:
            result_url = await mirror_url(urls[0])
        except Exception as e:
            logger.warning("Failed to mirror KIE result task_id=%s url=%s: %s", task_id, urls[0], e)
            result_url = urls[0]

        await repo.finish_generation(session, gen.id, result_url)

        if gen.image_session_id:
            await repo.update_image_session_last_result(
                session,
                gen.image_session_id,
                result_url,
                gen.id,
            )

        if bot:
            try:
                from bot.keyboards.models import image_session_kb, after_generation_kb

                caption = f"✅ <b>Готово!</b>\n\n<i>{gen.prompt[:200]}</i>"
                if gen.gen_type == GenerationType.image:
                    caption += (
                        "\n\n🎨 <b>Серия активна.</b>\n"
                        "Теперь просто отправляй новый текст или фото — настройки сохранятся."
                    )
                    await bot.send_photo(
                        chat_id=user.tg_id,
                        photo=result_url,
                        caption=caption,
                        reply_markup=image_session_kb(gen.id),
                    )
                    await bot.send_document(
                        chat_id=user.tg_id,
                        document=URLInputFile(result_url, filename="image.jpg"),
                    )
                else:
                    await bot.send_video(
                        chat_id=user.tg_id,
                        video=result_url,
                        caption=caption,
                        reply_markup=after_generation_kb(gen.id, "video"),
                    )
            except Exception as e:
                logger.warning("Failed to send KIE result user=%s gen=%s: %s", user.tg_id, gen.id, e)

    return {"ok": True}


@app.post("/webhook/kie/music")
async def kie_music_webhook(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    task_id = extract_task_id(payload)
    if not task_id:
        logger.warning("KIE music webhook without task_id: %s", payload)
        return {"ok": True}

    tg_id = pop_task(task_id)
    if not tg_id or not bot:
        logger.warning("KIE music webhook: unknown task_id=%s", task_id)
        return {"ok": True}

    if not is_success(payload):
        err = extract_error(payload)
        logger.warning("KIE music failed task_id=%s: %s", task_id, err)
        try:
            await bot.send_message(tg_id, f"❌ Ошибка генерации музыки:\n{err}", reply_markup=back_to_menu_kb())
        except Exception as e:
            logger.warning("Failed to notify music failure tg_id=%s: %s", tg_id, e)
        return {"ok": True}

    audio_urls = extract_music_urls(payload)
    if not audio_urls:
        logger.warning("KIE music webhook: no audio URLs task_id=%s payload=%s", task_id, payload)
        try:
            await bot.send_message(tg_id, "❌ Музыка готова, но ссылка не найдена.", reply_markup=back_to_menu_kb())
        except Exception:
            pass
        return {"ok": True}

    try:
        for url in audio_urls:
            await bot.send_audio(
                chat_id=tg_id,
                audio=URLInputFile(url, filename="track.mp3"),
                caption="🎵 <b>Трек готов!</b>",
                reply_markup=back_to_menu_kb(),
            )
    except Exception as e:
        logger.warning("Failed to send music result tg_id=%s: %s", tg_id, e)

    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "apix"}

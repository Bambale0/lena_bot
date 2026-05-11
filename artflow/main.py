# main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, Update, URLInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import redis.asyncio as aioredis

from api.comet_client import close_client, get_client
from api.miniapp_routes import router as miniapp_router
from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_success
from api.music_service import extract_music_urls, pop_task
from api.public_files import UPLOAD_ROOT, mirror_url, save_public_file
from bot.handlers import admin, assistant, balance, feed, image_gen, marketplace, midjourney, music_gen, payment, start, video_gen, stars_payment
from bot.handlers import settings as settings_handler
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.feed import get_generation_result_keyboard
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.utils.telegram_ui import is_benign_telegram_error
from core.broadcast_scheduler import run_broadcast_scheduler
from core.config import settings
from core.logger import setup_logging
from db.models import GenerationType, TransactionStatus
from payments.cryptobot import verify_webhook_signature
from payments.tbank import verify_notification_token
from db import repository as repo
from db.seed import run_seed
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _sanitize_provider_error(raw: str | None, *, fallback: str = "Ошибка на стороне генератора") -> str:
    text = (raw or "").strip()
    if not text:
        return fallback

    replacements = {
        "KIE.AI": "генератор",
        "KIE AI": "генератор",
        "KIE": "генератор",
        "webhook": "сигнал о готовности",
        "callback": "ответ сервиса",
        "createTask": "запуск",
        "taskId": "id задачи",
        "resultUrls": "ссылки на результат",
        "result urls": "ссылки на результат",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    normalized = text.strip(" .\n")
    return normalized or fallback


async def _set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="starshelp", description="Telegram Stars"),
        BotCommand(command="assistant", description="AI-ассистент"),
        BotCommand(command="feed", description="Лента работ"),
        BotCommand(command="prompts", description="Библиотека промптов"),
    ]
    if settings.ADMIN_IDS:
        commands.append(BotCommand(command="admin", description="Админ-панель"))
    await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())


async def _accrue_referral_commissions(session, user: "User", amount_rub: float, bot_instance: Bot | None = None) -> None:
    """Начисляет реферальные комиссии с платежа по трём линиям."""
    active_bot = bot_instance or bot
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
        if referrer and active_bot:
            try:
                await active_bot.send_message(
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
broadcast_scheduler_task: asyncio.Task | None = None
broadcast_scheduler_stop: asyncio.Event | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp, redis_client, broadcast_scheduler_task, broadcast_scheduler_stop
    setup_logging()

    # Redis
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Bot + Dispatcher
    storage = RedisStorage(redis=redis_client)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await _set_bot_commands(bot)
    dp = Dispatcher(storage=storage)

    # Middlewares (порядок важен)
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AuthMiddleware())
    dp.message.middleware(ThrottlingMiddleware(redis_client))

    # Routers
    dp.include_router(start.router)
    dp.include_router(assistant.router)
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
    dp.include_router(settings_handler.router)
    dp.include_router(stars_payment.router)

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

    broadcast_scheduler_stop = asyncio.Event()
    broadcast_scheduler_task = asyncio.create_task(run_broadcast_scheduler(broadcast_scheduler_stop, bot))

    yield

    # Shutdown
    if broadcast_scheduler_stop is not None:
        broadcast_scheduler_stop.set()
    if broadcast_scheduler_task is not None:
        try:
            await broadcast_scheduler_task
        except Exception:
            logger.exception("Broadcast scheduler shutdown failed")
    await close_client()
    await redis_client.aclose()
    logger.info("Shutdown complete")



app = FastAPI(title="APIX", lifespan=lifespan)

@app.middleware("http")
async def miniapp_no_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/app" or path.startswith("/app/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount(settings.STATIC_UPLOAD_URL_PATH, StaticFiles(directory=str(UPLOAD_ROOT)), name="static_upload")
app.include_router(miniapp_router)

WEBAPP_DIST = Path("webapp/dist")
if WEBAPP_DIST.exists():
    @app.api_route("/app", methods=["GET", "HEAD"])
    async def miniapp_index() -> FileResponse:
        return FileResponse(WEBAPP_DIST / "index.html")

    @app.api_route("/app/{path:path}", methods=["GET", "HEAD"])
    async def miniapp_files(path: str) -> FileResponse:
        candidate = (WEBAPP_DIST / path).resolve()
        dist_root = WEBAPP_DIST.resolve()
        if dist_root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEBAPP_DIST / "index.html")
else:
    @app.get("/app", response_class=PlainTextResponse)
    async def miniapp_not_built() -> str:
        return "Mini app is not built. Run: cd webapp && npm install && npm run build"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://artflow.ru", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Telegram-Bot-Api-Secret-Token"],
)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Upload an image for use as a reference in generation."""
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
    url = save_public_file(data, file.content_type)
    return {"url": url}


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
                await _accrue_referral_commissions(session, user, tx.amount_rub, bot)
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
    try:
        data = await request.json()
    except Exception as exc:
        logger.warning("Invalid T-Bank webhook JSON: %s", exc)
        return PlainTextResponse("OK")

    if not verify_notification_token(data, settings.TBANK_PASSWORD):
        logger.warning(
            "Invalid T-Bank webhook token: payment_id=%s status=%s order_id=%s",
            data.get("PaymentId"),
            data.get("Status"),
            data.get("OrderId"),
        )
        return PlainTextResponse("OK")

    if not data.get("Success"):
        logger.info(
            "T-Bank webhook non-success acknowledged: payment_id=%s status=%s order_id=%s",
            data.get("PaymentId"),
            data.get("Status"),
            data.get("OrderId"),
        )
        return PlainTextResponse("OK")

    status = str(data.get("Status", "")).upper()
    external_id = str(data.get("PaymentId", "")).strip()
    if not external_id:
        logger.warning("T-Bank webhook without PaymentId: %s", data)
        return PlainTextResponse("OK")

    async with AsyncSessionLocal() as session:
        if status == "CONFIRMED":
            tx = await repo.confirm_transaction(session, external_id)
            if tx:
                new_balance = await repo.add_credits(session, tx.user_id, tx.credits)
                user = await repo.get_user_by_id(session, tx.user_id)
                if user:
                    await _accrue_referral_commissions(session, user, tx.amount_rub, bot)
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
        else:
            logger.info("Unhandled T-Bank status acknowledged: payment_id=%s status=%s", external_id, status)

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
            user_err = _sanitize_provider_error(err)
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"❌ Генерация не удалась.\nКредиты возвращены.\n\n<code>{user_err[:500]}</code>",
                        reply_markup=back_to_menu_kb(),
                    )
                except Exception as e:
                    logger.warning("Failed to notify KIE failure user=%s: %s", user.tg_id, e)
            return {"ok": True}

        urls = extract_result_urls(payload)
        if not urls:
            err = "Provider callback success but no result urls"
            user_err = "Результат готов, но ссылка на файл не пришла"
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(user.tg_id, f"❌ {user_err}. Кредиты возвращены.", reply_markup=back_to_menu_kb())
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
                    for idx, url in enumerate(urls):
                        is_first = idx == 0
                        img_caption = caption if is_first else None
                        try:
                            await bot.send_photo(
                                chat_id=user.tg_id,
                                photo=URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                                caption=img_caption,
                            )
                        except Exception:
                            await bot.send_document(
                                chat_id=user.tg_id,
                                document=URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                                caption=img_caption,
                            )

                    for idx, url in enumerate(urls):
                        doc_caption = "📎 <b>Исходник файлом</b>" if idx == 0 else None
                        try:
                            await bot.send_document(
                                chat_id=user.tg_id,
                                document=URLInputFile(url, filename=f"source_{gen.id}_{idx + 1}.png"),
                                caption=doc_caption,
                            )
                        except Exception:
                            logger.warning("Failed to send source document user=%s gen=%s idx=%s", user.tg_id, gen.id, idx)

                    await bot.send_message(
                        chat_id=user.tg_id,
                        text="Что делаем дальше?",
                        reply_markup=image_session_kb(gen.id),
                    )
                else:
                    await bot.send_video(
                        chat_id=user.tg_id,
                        video=URLInputFile(result_url, filename="video.mp4"),
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

    from api.music_service import pop_miniapp_task

    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}

    status = (
        data.get("status")
        or payload.get("status")
        or data.get("state")
        or payload.get("state")
        or ""
    )

    msg = (
        data.get("errorMessage")
        or payload.get("errorMessage")
        or data.get("msg")
        or payload.get("msg")
        or ""
    )

    extracted_error = extract_error(payload) or ""
    extracted_error_for_flags = "" if extracted_error == "KIE generation failed" else extracted_error
    normalized_msg = f"{msg} {extracted_error_for_flags}".strip().lower()

    # Suno/KIE can send an intermediate callback after lyrics/text are ready.
    # This is NOT a failed generation and task_id must NOT be popped here.
    if (
        status in {"PENDING", "TEXT_SUCCESS"}
        or "text generated successfully" in normalized_msg
        or "lyrics/text generation successful" in normalized_msg
    ):
        logger.info(
            "KIE music still processing task_id=%s status=%s msg=%s",
            task_id,
            status,
            normalized_msg,
        )
        return {"ok": True}

    audio_urls = extract_music_urls(payload)

    # If callback has no audio and does not look final-failed, keep waiting.
    # This prevents losing task_id on odd partial callbacks with empty status.
    failed_markers = (
        "failed",
        "sensitive",
        "error",
        "insufficient",
        "unauthorized",
        "invalid",
    )
    looks_failed = (
        status in {"CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED", "CALLBACK_EXCEPTION", "SENSITIVE_WORD_ERROR"}
        or any(x in normalized_msg for x in failed_markers)
    )
    explicit_success = str(status).upper() in {"SUCCESS", "COMPLETE", "COMPLETED", "DONE"}

    if not audio_urls and not looks_failed and not explicit_success and not is_success(payload):
        if "all generated successfully" in normalized_msg:
            logger.warning("KIE music final-looking callback without parsed audio task_id=%s payload=%s", task_id, payload)
        else:
            logger.info(
                "KIE music non-final callback task_id=%s status=%s msg=%s",
                task_id,
                status,
                normalized_msg,
            )
        return {"ok": True}

    db_gen = None
    db_user = None
    async with AsyncSessionLocal() as session:
        db_gen = await repo.get_generation_by_task_id(session, task_id)
        if db_gen:
            if db_gen.status.value in {"done", "failed"}:
                pop_task(task_id)
                pop_miniapp_task(task_id)
                return {"ok": True}
            db_user = await repo.get_user_by_id(session, db_gen.user_id)

    # Pop only on final success or final failure.
    tg_id = pop_task(task_id)
    miniapp_gen_id = pop_miniapp_task(task_id)
    if not tg_id and db_user:
        tg_id = db_user.tg_id

    generation_id = db_gen.id if db_gen else miniapp_gen_id

    if not tg_id and not generation_id:
        logger.warning("KIE music webhook: unknown task_id=%s status=%s", task_id, status)
        return {"ok": True}

    if looks_failed or (not audio_urls and not explicit_success and not is_success(payload)):
        err = extracted_error or msg or f"Music generation failed: {status}"
        user_err = _sanitize_provider_error(err, fallback="Ошибка при генерации музыки")
        logger.warning("KIE music failed task_id=%s status=%s: %s", task_id, status, err)
        if generation_id:
            async with AsyncSessionLocal() as session:
                gen = await repo.get_generation_by_id(session, generation_id)
                if gen:
                    await repo.fail_generation(session, gen.id, err)
                    await repo.add_credits(session, gen.user_id, gen.credits_spent)
        if tg_id and bot:
            try:
                await bot.send_message(
                    tg_id,
                    f"❌ Ошибка генерации музыки:\n{user_err}",
                    reply_markup=back_to_menu_kb(),
                )
            except Exception as e:
                logger.warning("Failed to notify music failure tg_id=%s: %s", tg_id, e)
        return {"ok": True}

    if not audio_urls:
        logger.warning("KIE music webhook: no audio URLs task_id=%s status=%s payload=%s", task_id, status, payload)
        if tg_id and bot:
            try:
                await bot.send_message(tg_id, "❌ Музыка готова, но ссылка не найдена.", reply_markup=back_to_menu_kb())
            except Exception:
                pass
        return {"ok": True}

    if generation_id:
        async with AsyncSessionLocal() as session:
            await repo.finish_generation(session, generation_id, audio_urls[0])

    if tg_id and bot:
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


LANDING_DIR = Path("landing")
if LANDING_DIR.exists():
    app.mount("/", StaticFiles(directory=str(LANDING_DIR), html=True), name="landing")
else:
    @app.get("/", response_class=PlainTextResponse)
    async def landing_not_built() -> str:
        return "Landing is not built."

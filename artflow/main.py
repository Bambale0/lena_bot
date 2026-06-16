# main.py
from __future__ import annotations

import asyncio
import html
import hmac
import json
import logging
import mimetypes
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    FSInputFile,
    MenuButtonCommands,
    Update,
    URLInputFile,
)
from aiogram.exceptions import TelegramEntityTooLarge
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import redis.asyncio as aioredis

from api import comet_fallback
from api.comet_client import close_client, get_client
from api.miniapp_auth import get_miniapp_user
from api.miniapp_routes import WEB_TASK_PREFIX, is_web_task_id, router as miniapp_router
from api.realtime import router as realtime_router
from api.web import router as web_router
from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_processing, is_success
from api.midjourney_service import MJButton, MJTaskResult
from api.music_service import (
    SUNO_VOICE_FAILED_STATUSES,
    SUNO_VOICE_STATUS_AWAITING_VERIFICATION,
    SUNO_VOICE_STATUS_FAILED,
    SUNO_VOICE_STATUS_READY,
    extract_music_urls,
    extract_suno_provider_voice_id,
    extract_suno_validate_phrase,
    extract_suno_voice_error,
    extract_suno_voice_status,
    extract_suno_voice_task_id,
    pop_task,
)
from api.public_files import UPLOAD_ROOT, mirror_url, save_public_file
from bot.handlers import admin, assistant, balance, feed, image_gen, marketplace, midjourney, music_gen, payment, start, video_gen, stars_payment
from bot.handlers import settings as settings_handler
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.feed import get_generation_result_keyboard
from bot.keyboards.midjourney import mj_action_buttons_kb
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.states import MidjourneyFSM
from bot.utils.telegram_ui import is_benign_telegram_error
from core.broadcast_scheduler import run_broadcast_scheduler
from core.config import settings
from core.logger import setup_logging
from db.models import Generation, GenerationType, ImageSession, TransactionStatus
from payments.cryptobot import verify_webhook_signature
from payments.lava import (
    cached_payment_url as lava_cached_payment_url,
    extract_payment_url as lava_extract_payment_url,
    get_invoice as lava_get_invoice,
    is_success_webhook as lava_is_success_webhook,
    webhook_contract_id as lava_webhook_contract_id,
)
from payments.tbank import verify_notification_token
from db import repository as repo
from db.seed import run_seed
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")

_MJ_IMAGE_MODELS = {"midjourney-imagine", "midjourney-blend", "midjourney-action"}
_MJ_DESCRIBE_MODEL = "midjourney-describe"
_MJ_VIDEO_MODEL = "midjourney-video"
_PROMPT_MENU_PREVIEW_MAX = 700
_TELEGRAM_UPDATE_DEDUPE_TTL = 3600
_recent_telegram_updates: dict[int, float] = {}


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


def _midjourney_webhook_secret() -> str:
    return (settings.MIDJOURNEY_WEBHOOK_SECRET or settings.WEBHOOK_SECRET).strip()


def _is_production_env() -> bool:
    return str(settings.ENV or "").strip().lower() in {"prod", "production"}


def _verify_kie_webhook_secret(secret: str | None, header_secret: str | None = None) -> None:
    configured = (settings.KIE_WEBHOOK_SECRET or "").strip()
    if not configured:
        if _is_production_env():
            logger.error("KIE webhook secret is required in production")
            raise HTTPException(status_code=503, detail="KIE webhook secret is not configured")
        return
    provided = [value.strip() for value in (secret, header_secret) if value]
    if not any(hmac.compare_digest(value, configured) for value in provided):
        raise HTTPException(status_code=403, detail="Invalid KIE webhook secret")


def _verify_midjourney_webhook_secret(secret: str | None) -> None:
    expected_secret = _midjourney_webhook_secret()
    if not expected_secret:
        if _is_production_env():
            logger.error("Midjourney webhook secret is required in production")
            raise HTTPException(status_code=503, detail="Midjourney webhook secret is not configured")
        return
    if not secret or not hmac.compare_digest(secret, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid Midjourney webhook secret")


def _midjourney_button_state(buttons: list[MJButton]) -> list[dict[str, str]]:
    return [
        {"custom_id": button.custom_id, "label": button.label, "emoji": button.emoji}
        for button in buttons
    ]


def _is_feed_prompt_derivative(gen: Generation) -> bool:
    return bool(getattr(gen, "source_feed_gen_id", None))


async def _prompt_actions_allowed_for_generation(session, gen: Generation) -> bool:
    source_feed_gen_id = getattr(gen, "source_feed_gen_id", None)
    if not source_feed_gen_id:
        return True
    source = await repo.get_generation_by_id(session, source_feed_gen_id)
    return bool(source and getattr(source, "user_id", None) == getattr(gen, "user_id", None))


def _kie_result_caption(gen: Generation) -> str:
    return "✅ <b>Готово!</b>"


def _is_repeat_generation(gen: Generation) -> bool:
    action_type = getattr(gen, "action_type", None)
    action_value = str(getattr(action_type, "value", action_type) or "")
    return action_value == "repeat" or action_value.endswith(".repeat")


def _web_task_lookup_id(task_id: str | None) -> str:
    value = str(task_id or "").strip()
    if not value or value.startswith(WEB_TASK_PREFIX):
        return value
    return f"{WEB_TASK_PREFIX}{value}"


def _should_notify_generation_in_bot(gen: Generation | None) -> bool:
    return bool(gen) and not is_web_task_id(getattr(gen, "task_id", None))


def _prompt_menu_preview_for_generation(gen: Generation, prompt: str | None) -> str | None:
    return None if _is_repeat_generation(gen) else prompt


def _prompt_menu_text(prompt: str | None) -> str:
    return "Что делаем дальше?"


def _looks_like_image_asset(url: str | None) -> bool:
    value = str(url or "").strip().lower().split("?", 1)[0].split("#", 1)[0]
    return value.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"))


def _extract_video_result_urls(payload: dict) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    candidates: list[str] = []
    if isinstance(data, dict):
        result_json_str = data.get("resultJson")
        if isinstance(result_json_str, str) and result_json_str.strip():
            try:
                parsed = json.loads(result_json_str)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                for key in ("resultUrls", "result_urls", "videoUrls", "video_urls", "urls"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        candidates.extend(str(item).strip() for item in value if str(item or "").strip())
                    elif isinstance(value, str) and value.strip():
                        candidates.append(value.strip())
                for key in ("resultUrl", "result_url", "videoUrl", "video_url", "url"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        candidates.append(value.strip())
        if not candidates:
            for key in ("resultUrls", "result_urls", "videoUrls", "video_urls", "urls"):
                value = data.get(key)
                if isinstance(value, list):
                    candidates.extend(str(item).strip() for item in value if str(item or "").strip())
                elif isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
            for key in ("resultUrl", "result_url", "videoUrl", "video_url", "url"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    if not candidates:
        candidates = extract_result_urls(payload)
    filtered = [url for url in dict.fromkeys(candidates) if url and not _looks_like_image_asset(url)]
    return filtered or list(dict.fromkeys(candidates))


def _claim_telegram_update_memory(update_id: int) -> bool:
    now = time.monotonic()
    if len(_recent_telegram_updates) > 10_000:
        expired = [key for key, expires_at in _recent_telegram_updates.items() if expires_at <= now]
        for key in expired:
            _recent_telegram_updates.pop(key, None)

    expires_at = _recent_telegram_updates.get(update_id)
    if expires_at and expires_at > now:
        return False
    _recent_telegram_updates[update_id] = now + _TELEGRAM_UPDATE_DEDUPE_TTL
    return True


async def _claim_telegram_update(update_id: int) -> bool:
    if redis_client is not None:
        try:
            key = f"telegram:update:{settings.BOT_USERNAME}:{update_id}"
            claimed = await redis_client.set(key, "1", ex=_TELEGRAM_UPDATE_DEDUPE_TTL, nx=True)
            return bool(claimed)
        except Exception as exc:
            logger.warning("Telegram update dedupe Redis fallback update_id=%s: %s", update_id, exc)
    return _claim_telegram_update_memory(update_id)


async def _get_midjourney_context(user_tg_id: int):
    if not bot or not dp:
        return None
    return dp.fsm.get_context(bot=bot, chat_id=user_tg_id, user_id=user_tg_id)


async def _delete_midjourney_status_message(user_tg_id: int, message_id: int | None) -> None:
    if not bot or not message_id:
        return
    try:
        await bot.delete_message(chat_id=user_tg_id, message_id=message_id)
    except TelegramBadRequest as exc:
        if is_benign_telegram_error(exc):
            return
        logger.debug("Failed to delete MJ status message chat=%s message=%s: %s", user_tg_id, message_id, exc)
    except Exception as exc:
        logger.debug("Failed to delete MJ status message chat=%s message=%s: %s", user_tg_id, message_id, exc)


async def _mark_midjourney_failed(
    session,
    gen: Generation,
    user_tg_id: int,
    error_text: str,
    *,
    state_ctx=None,
) -> None:
    if await repo.fail_generation(session, gen.id, error_text):
        await repo.add_credits(session, gen.user_id, gen.credits_spent)
    if state_ctx is not None:
        data = await state_ctx.get_data()
        await _delete_midjourney_status_message(user_tg_id, data.get("mj_status_message_id"))
        await state_ctx.clear()


async def _finish_midjourney_image_generation(
    gen: Generation,
    user_tg_id: int,
    task_result: MJTaskResult,
    *,
    state_ctx=None,
) -> None:
    if state_ctx is not None:
        data = await state_ctx.get_data()
        await _delete_midjourney_status_message(user_tg_id, data.get("mj_status_message_id"))
        await state_ctx.update_data(
            task_id=task_result.task_id,
            buttons=_midjourney_button_state(task_result.buttons),
            mj_status_message_id=None,
        )
        await state_ctx.set_state(MidjourneyFSM.viewing_result)

    caption = "✅ Blend готово!" if gen.model == "midjourney-blend" else f"✅ Готово!\n\n<i>{gen.prompt[:200]}</i>"
    reply_markup = mj_action_buttons_kb(task_result.buttons) if task_result.buttons else main_menu_kb()
    await bot.send_photo(  # type: ignore[union-attr]
        chat_id=user_tg_id,
        photo=URLInputFile(task_result.image_url, filename="image.jpg"),
        caption=caption,
        reply_markup=reply_markup,
    )
    await bot.send_document(  # type: ignore[union-attr]
        chat_id=user_tg_id,
        document=URLInputFile(task_result.image_url, filename="image.jpg"),
    )


async def _finish_midjourney_describe_generation(
    gen: Generation,
    user_tg_id: int,
    task_result: MJTaskResult,
    *,
    state_ctx=None,
) -> None:
    if state_ctx is not None:
        data = await state_ctx.get_data()
        await _delete_midjourney_status_message(user_tg_id, data.get("mj_status_message_id"))
        await state_ctx.clear()

    prompts_text = task_result.prompt or "Промпт не получен"
    await bot.send_message(  # type: ignore[union-attr]
        chat_id=user_tg_id,
        text=f"🔍 <b>Описание изображения:</b>\n\n{prompts_text}",
        reply_markup=main_menu_kb(),
    )


async def _finish_midjourney_video_generation(
    gen: Generation,
    user_tg_id: int,
    task_result: MJTaskResult,
    *,
    state_ctx=None,
) -> None:
    if state_ctx is not None:
        data = await state_ctx.get_data()
        await _delete_midjourney_status_message(user_tg_id, data.get("mj_status_message_id"))
        await state_ctx.clear()

    await bot.send_video(  # type: ignore[union-attr]
        chat_id=user_tg_id,
        video=URLInputFile(
            task_result.video_url or (task_result.video_urls[0] if task_result.video_urls else "") or task_result.image_url,
            filename="video.mp4",
        ),
        caption="✅ MJ Видео готово!",
        reply_markup=main_menu_kb(),
    )


async def _download_url_to_tempfile(url: str, suffix: str = ".bin") -> str | None:
    tmp_path = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=120) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp_path = tmp.name
                    async for chunk in resp.aiter_bytes(1024 * 256):
                        if chunk:
                            tmp.write(chunk)
        return tmp_path
    except Exception as e:
        logger.warning("Failed to download remote media %s: %s", url, e)
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        return None


async def _set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="assistant", description="AI-ассистент"),
        BotCommand(command="feed", description="Лента работ"),
        BotCommand(command="prompts", description="Библиотека промптов"),
    ]
    if settings.TELEGRAM_STARS_ENABLED:
        commands.insert(3, BotCommand(command="starshelp", description="Telegram Stars"))
    if settings.ADMIN_IDS:
        commands.append(BotCommand(command="admin", description="Админ-панель"))
    await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def _accrue_referral_commissions(session, user: "User", amount_rub: float, bot_instance: Bot | None = None) -> None:
    """Начисляет реферальные комиссии с платежа по трём линиям."""
    if settings.REFERRAL_FREEZE:
        logger.warning("Referral freeze active: skip commission accrual for user_id=%s amount=%.2f", getattr(user, "id", None), amount_rub)
        return
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


async def _reverse_referral_commissions(session, user: "User", amount_rub: float) -> None:
    """Откатывает реферальные комиссии по возврату/реверсу платежа."""
    pairs = [
        (user.referrer_id, settings.REFERRAL_COMMISSION_L1),
        (user.referrer_l2_id, settings.REFERRAL_COMMISSION_L2),
        (user.referrer_l3_id, settings.REFERRAL_COMMISSION_L3),
    ]
    for ref_id, pct in pairs:
        if not ref_id or pct <= 0:
            continue
        commission = round(amount_rub * pct, 2)
        await repo.add_referral_balance(session, ref_id, -commission)
        logger.info("Referral commission reversed %.2f₽ -> user_id=%s (%.0f%%)", commission, ref_id, pct * 100)


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



app = FastAPI(
    title="APIX",
    description="APIX AI API for Telegram auth, content generation, billing, prompt library, feed, and provider webhooks.",
    version="1.0.0",
    lifespan=lifespan,
)


_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class UploadStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return Response(
                content=_TRANSPARENT_PNG,
                media_type="image/png",
                headers={"Cache-Control": "no-store, max-age=0"},
            )


@app.middleware("http")
async def miniapp_no_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/app/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if "Pragma" in response.headers:
            del response.headers["Pragma"]
        if "Expires" in response.headers:
            del response.headers["Expires"]
        return response
    if path.startswith("/js/") or path.startswith("/css/"):
        response.headers["Cache-Control"] = "public, max-age=600"
        if "Pragma" in response.headers:
            del response.headers["Pragma"]
        if "Expires" in response.headers:
            del response.headers["Expires"]
        return response
    if path == "/app" or path.startswith("/app/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount(settings.STATIC_UPLOAD_URL_PATH, UploadStaticFiles(directory=str(UPLOAD_ROOT)), name="static_upload")
app.include_router(miniapp_router)
app.include_router(realtime_router)
app.include_router(web_router, prefix="/api/web")

PROMPT_RIOT_DIR = Path("web/static/prompt-riot")
WEBAPP_DIST = Path("webapp/dist")
if PROMPT_RIOT_DIR.exists():
    app.mount(
        "/prompt-riot",
        StaticFiles(directory=str(PROMPT_RIOT_DIR), html=True),
        name="prompt_riot_app",
    )

if WEBAPP_DIST.exists():
    @app.api_route("/app", methods=["GET", "HEAD"], include_in_schema=False)
    async def miniapp_index() -> FileResponse:
        return FileResponse(WEBAPP_DIST / "index.html")

    @app.api_route("/app/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def miniapp_files(path: str) -> FileResponse:
        candidate = (WEBAPP_DIST / path).resolve()
        dist_root = WEBAPP_DIST.resolve()
        if dist_root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEBAPP_DIST / "index.html")
else:
    @app.get("/app", response_class=PlainTextResponse, include_in_schema=False)
    async def miniapp_not_built() -> str:
        return "Mini app is not built. Run: cd webapp && npm install && npm run build"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://apixbotai.com",
        "https://www.apixbotai.com",
        "https://apix.chillcreative.ru",
        "https://artflow.ru",
        "http://localhost:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Telegram-Bot-Api-Secret-Token",
        "X-Telegram-Init-Data",
        "X-Web-Auth-Token",
        "X-Dev-Tg-Id",
    ],
)


def _is_supported_reference_image(data: bytes, content_type: str | None) -> bool:
    content = (content_type or "").lower()
    if content and not content.startswith("image/"):
        return False
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
    )


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _user=Depends(get_miniapp_user),
) -> dict:
    """Upload an image for use as a reference in generation."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
    if not _is_supported_reference_image(data, file.content_type):
        raise HTTPException(status_code=422, detail="Only JPEG, PNG and WebP images are supported")
    url = save_public_file(data, file.content_type)
    return {"url": url}


# ── Telegram Webhook ──────────────────────────────────────────────────────────

async def _process_telegram_update(update: Update) -> None:
    try:
        await dp.feed_update(bot, update)  # type: ignore[arg-type]
    except TelegramForbiddenError as e:
        logger.info("Ignoring Telegram webhook update for unavailable chat: %s", e)
    except TelegramBadRequest as e:
        if is_benign_telegram_error(e):
            logger.debug("Ignoring benign Telegram callback error: %s", e)
            return
        logger.exception("Telegram webhook bad request: %s", e)
    except Exception as e:
        logger.exception("Telegram webhook update processing failed: %s", e)


@app.post(settings.WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()
    update = Update.model_validate(body)
    if not await _claim_telegram_update(update.update_id):
        logger.info("Ignoring duplicate Telegram update_id=%s", update.update_id)
        return {"ok": True}
    asyncio.create_task(_process_telegram_update(update))
    return {"ok": True}


@app.post(settings.MIDJOURNEY_WEBHOOK_PATH)
async def midjourney_webhook(request: Request, secret: str | None = None) -> dict:
    _verify_midjourney_webhook_secret(secret)

    payload = await request.json()
    task_result = MJTaskResult.from_dict(payload)
    if not task_result.task_id:
        logger.warning("Midjourney webhook without task_id: %s", payload)
        return {"ok": True}

    if not task_result.is_done:
        logger.info(
            "Midjourney webhook ignoring non-terminal status task=%s status=%s",
            task_result.task_id,
            task_result.status,
        )
        return {"ok": True}

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_task_id(session, task_result.task_id)
        if not gen:
            gen = await repo.get_generation_by_task_id(session, _web_task_lookup_id(task_result.task_id))
        if not gen:
            logger.warning("Midjourney webhook for unknown task_id=%s", task_result.task_id)
            return {"ok": True}
        if gen.status.value in {"done", "failed"}:
            return {"ok": True}

        user = await repo.get_user_by_id(session, gen.user_id)
        if not user:
            logger.warning("Midjourney webhook user not found for generation=%s", gen.id)
            return {"ok": True}

        state_ctx = await _get_midjourney_context(user.tg_id)

        if not task_result.is_success:
            err = task_result.fail_reason or payload.get("description") or "Midjourney task failed"
            await _mark_midjourney_failed(session, gen, user.tg_id, err, state_ctx=state_ctx)
            if bot and _should_notify_generation_in_bot(gen):
                await bot.send_message(
                    user.tg_id,
                    f"❌ Ошибка Midjourney: <code>{_sanitize_provider_error(err)[:500]}</code>\n💋 возвращены.",
                    reply_markup=main_menu_kb(),
                )
            return {"ok": True}

        if gen.model in _MJ_IMAGE_MODELS:
            if not task_result.image_url:
                await _mark_midjourney_failed(
                    session, gen, user.tg_id, "Midjourney callback success but no imageUrl", state_ctx=state_ctx
                )
                if bot and _should_notify_generation_in_bot(gen):
                    await bot.send_message(
                        user.tg_id,
                        "❌ Midjourney вернул успех, но без изображения. 💋 возвращены.",
                        reply_markup=main_menu_kb(),
                    )
                return {"ok": True}

            await repo.finish_generation(session, gen.id, task_result.image_url)
            if bot and _should_notify_generation_in_bot(gen):
                await _finish_midjourney_image_generation(gen, user.tg_id, task_result, state_ctx=state_ctx)
            return {"ok": True}

        if gen.model == _MJ_DESCRIBE_MODEL:
            await repo.finish_generation(session, gen.id, task_result.task_id)
            if bot and _should_notify_generation_in_bot(gen):
                await _finish_midjourney_describe_generation(gen, user.tg_id, task_result, state_ctx=state_ctx)
            return {"ok": True}

        if gen.model == _MJ_VIDEO_MODEL:
            resolved_video_url = (
                task_result.video_url
                or (task_result.video_urls[0] if task_result.video_urls else "")
                or task_result.image_url
            )
            if not resolved_video_url:
                await _mark_midjourney_failed(
                    session, gen, user.tg_id, "Midjourney callback success but no videoUrl", state_ctx=state_ctx
                )
                if bot and _should_notify_generation_in_bot(gen):
                    await bot.send_message(
                        user.tg_id,
                        "❌ Midjourney вернул успех, но без видео. 💋 возвращены.",
                        reply_markup=main_menu_kb(),
                    )
                return {"ok": True}

            await repo.finish_generation(session, gen.id, resolved_video_url)
            if bot and _should_notify_generation_in_bot(gen):
                await _finish_midjourney_video_generation(gen, user.tg_id, task_result, state_ctx=state_ctx)
            return {"ok": True}

        logger.info("Midjourney webhook ignored unsupported model=%s task=%s", gen.model, task_result.task_id)
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
        confirmed = await repo.confirm_transaction_and_add_credits(
            session,
            external_id,
            note="Payment confirmed via cryptobot",
        )
        if confirmed:
            tx, new_balance = confirmed
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
            confirmed = await repo.confirm_transaction_and_add_credits(
                session,
                external_id,
                note="Payment confirmed via tbank",
            )
            if confirmed:
                tx, new_balance = confirmed
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
            existing_tx = await repo.get_transaction_by_external_id(session, external_id)
            was_paid = bool(existing_tx and existing_tx.status == TransactionStatus.paid)
            tx = await repo.set_transaction_status(session, external_id, TransactionStatus.refunded)
            if tx and was_paid:
                await repo.add_credits(session, tx.user_id, -tx.credits, entry_type="payment_refund", source_type="transaction", source_id=str(tx.id), note=f"Refund/reversal via {tx.provider}")
                user = await repo.get_user_by_id(session, tx.user_id)
                if user:
                    await _reverse_referral_commissions(session, user, tx.amount_rub)
        else:
            logger.info("Unhandled T-Bank status acknowledged: payment_id=%s status=%s", external_id, status)

    return PlainTextResponse("OK")


@app.get("/pay/lava/{invoice_id}")
async def lava_pay_redirect(invoice_id: str) -> RedirectResponse:
    pay_url = lava_cached_payment_url(invoice_id)
    if not pay_url:
        try:
            data = await lava_get_invoice(invoice_id)
            pay_url = lava_extract_payment_url(data).strip()
        except Exception as exc:
            logger.error("Lava redirect lookup failed for %s: %s", invoice_id, exc)
            raise HTTPException(status_code=502, detail="Payment service error")
    if not pay_url:
        raise HTTPException(status_code=404, detail="Payment link not found")
    return RedirectResponse(pay_url, status_code=307)


# ── KIE.AI Webhook ────────────────────────────────────────────────────────────

@app.post(settings.LAVA_WEBHOOK_PATH)
async def lava_webhook(request: Request) -> PlainTextResponse:
    try:
        data = await request.json()
    except Exception as exc:
        logger.warning("Invalid Lava webhook JSON: %s", exc)
        return PlainTextResponse("OK")

    if not lava_is_success_webhook(data):
        return PlainTextResponse("OK")

    external_id = lava_webhook_contract_id(data)
    if not external_id:
        logger.warning("Lava webhook without invoice id: %s", data)
        return PlainTextResponse("OK")

    async with AsyncSessionLocal() as session:
        confirmed = await repo.confirm_transaction_and_add_credits(
            session,
            external_id,
            note="Payment confirmed via lava",
        )
        if confirmed:
            tx, new_balance = confirmed
            user = await repo.get_user_by_id(session, tx.user_id)
            if user:
                await _accrue_referral_commissions(session, user, tx.amount_rub, bot)
                if bot:
                    try:
                        await bot.send_message(
                            user.tg_id,
                            f"✅ Оплата через Lava подтверждена!\n"
                            f"Зачислено: <b>+{tx.credits} 💋</b>\n"
                            f"Баланс: <b>{new_balance} 💋</b>",
                            reply_markup=back_to_menu_kb(),
                        )
                    except Exception as e:
                        logger.warning("Failed to notify user %s: %s", user.tg_id, e)

    return PlainTextResponse("OK")


@app.post(settings.KIE_WEBHOOK_PATH)
async def kie_webhook(
    request: Request,
    secret: str | None = None,
    provider: str | None = None,
    comet_kind: str | None = None,
    x_kie_webhook_secret: str | None = Header(default=None, alias="X-KIE-Webhook-Secret"),
) -> dict:
    _verify_kie_webhook_secret(secret, x_kie_webhook_secret)

    payload = await request.json()
    task_id = extract_task_id(payload)
    if not task_id:
        logger.warning("KIE webhook without task_id: %s", payload)
        return {"ok": True}
    lookup_task_id = task_id
    if provider == "comet" and comet_kind:
        lookup_task_id = comet_fallback.prefixed_task_id(comet_kind, task_id)

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_task_id(session, lookup_task_id)
        if not gen and lookup_task_id != task_id:
            gen = await repo.get_generation_by_task_id(session, task_id)
        if not gen:
            gen = await repo.get_generation_by_task_id(session, _web_task_lookup_id(lookup_task_id))
        if not gen and lookup_task_id != task_id:
            gen = await repo.get_generation_by_task_id(session, _web_task_lookup_id(task_id))
        if not gen:
            logger.warning("KIE webhook for unknown task_id=%s lookup_task_id=%s", task_id, lookup_task_id)
            return {"ok": True}

        # Idempotency: if already finished, acknowledge duplicate callback.
        if gen.status.value in {"done", "failed"}:
            return {"ok": True}

        user = await repo.get_user_by_id(session, gen.user_id)
        if not user:
            logger.warning("KIE webhook user not found for generation=%s", gen.id)
            return {"ok": True}

        if not is_success(payload):
            if is_processing(payload):
                logger.info("KIE webhook ignoring non-terminal task_id=%s status update", task_id)
                return {"ok": True}
            err = extract_error(payload)
            user_err = _sanitize_provider_error(err)
            if await repo.fail_generation(session, gen.id, err):
                await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot and _should_notify_generation_in_bot(gen):
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"❌ Генерация не удалась.\nКредиты возвращены.\n\n<code>{user_err[:500]}</code>",
                        reply_markup=back_to_menu_kb(),
                    )
                except Exception as e:
                    logger.warning("Failed to notify KIE failure user=%s: %s", user.tg_id, e)
            return {"ok": True}

        urls = _extract_video_result_urls(payload) if gen.gen_type == GenerationType.video else extract_result_urls(payload)
        if gen.gen_type == GenerationType.image and gen.image_session_id:
            image_session = await session.get(ImageSession, gen.image_session_id)
            reference_url = (getattr(image_session, "reference_url", None) or "").strip() if image_session else ""
            if reference_url:
                filtered_urls = [url for url in urls if str(url or "").strip() != reference_url]
                if filtered_urls:
                    urls = filtered_urls

        if not urls:
            err = "Provider callback success but no result urls"
            user_err = "Результат готов, но ссылка на файл не пришла"
            if await repo.fail_generation(session, gen.id, err):
                await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot and _should_notify_generation_in_bot(gen):
                try:
                    await bot.send_message(user.tg_id, f"❌ {user_err}. Кредиты возвращены.", reply_markup=back_to_menu_kb())
                except Exception as e:
                    logger.warning("Failed to notify empty KIE result user=%s: %s", user.tg_id, e)
            return {"ok": True}

        if gen.gen_type == GenerationType.video:
            urls = [url for url in urls if not _looks_like_image_asset(url)] or urls

        result_urls: list[str] = []
        for url in urls:
            try:
                result_urls.append(await mirror_url(url))
            except Exception as e:
                logger.warning("Failed to mirror KIE result task_id=%s url=%s: %s", task_id, url, e)
                result_urls.append(url)
        result_url = result_urls[0]

        await repo.finish_generation(session, gen.id, result_url, result_urls=result_urls)

        if gen.image_session_id:
            await repo.update_image_session_last_result(
                session,
                gen.image_session_id,
                result_url,
                gen.id,
            )

        if bot and _should_notify_generation_in_bot(gen):
            try:
                from bot.keyboards.models import after_generation_kb, image_session_kb, public_prompt_text

                publish_actions_allowed = await _prompt_actions_allowed_for_generation(session, gen)
                prompt_actions_allowed = publish_actions_allowed and not _is_repeat_generation(gen)
                prompt_for_copy = public_prompt_text(gen.prompt) if prompt_actions_allowed else None
                prompt_menu_preview = _prompt_menu_preview_for_generation(gen, prompt_for_copy)
                caption = _kie_result_caption(gen)
                if gen.gen_type == GenerationType.image:
                    caption += (
                        "\n\n🎨 <b>Серия активна.</b>\n"
                        "Теперь просто отправляй новый текст или фото — настройки сохранятся."
                    )
                    for idx, url in enumerate(result_urls):
                        is_first = idx == 0
                        img_caption = caption if is_first else None
                        try:
                            await bot.send_photo(
                                chat_id=user.tg_id,
                                photo=URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                                caption=img_caption,
                            )
                        except Exception:
                            try:
                                await bot.send_document(
                                    chat_id=user.tg_id,
                                    document=URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                                    caption=img_caption,
                                )
                            except Exception:
                                logger.warning("Failed to send image result user=%s gen=%s idx=%s", user.tg_id, gen.id, idx)

                    for idx, url in enumerate(result_urls):
                        try:
                            await bot.send_document(
                                chat_id=user.tg_id,
                                document=URLInputFile(url, filename=f"source_{gen.id}_{idx + 1}.png"),
                                caption="📎 <b>Исходник файлом</b>" if idx == 0 else None,
                            )
                        except Exception:
                            logger.warning("Failed to send source document user=%s gen=%s idx=%s", user.tg_id, gen.id, idx)

                    await bot.send_message(
                        chat_id=user.tg_id,
                        text=_prompt_menu_text(prompt_menu_preview),
                        reply_markup=image_session_kb(
                            gen.id,
                            prompt=prompt_menu_preview,
                            allow_publish=publish_actions_allowed,
                            allow_copy_prompt=prompt_actions_allowed,
                        ),
                    )
                else:
                    video_reply_markup = after_generation_kb(
                        gen.id,
                        "video",
                        prompt=prompt_menu_preview,
                        allow_publish=publish_actions_allowed,
                        allow_copy_prompt=prompt_actions_allowed,
                    )
                    telegram_safe_video_bytes = 49 * 1024 * 1024
                    video_sent = False
                    video_too_large = False
                    tmp_video = None
                    try:
                        await bot.send_video(
                            chat_id=user.tg_id,
                            video=URLInputFile(result_url, filename="video.mp4"),
                            caption=caption,
                            reply_markup=video_reply_markup,
                        )
                        video_sent = True
                    except TelegramEntityTooLarge as video_url_err:
                        video_too_large = True
                        logger.warning(
                            "Video URL send too large user=%s gen=%s url=%s err=%s",
                            user.tg_id, gen.id, result_url, video_url_err,
                        )
                    except Exception as video_url_err:
                        logger.warning(
                            "Video URL send failed user=%s gen=%s url=%s err=%s",
                            user.tg_id, gen.id, result_url, video_url_err,
                        )
                        tmp_video = await _download_url_to_tempfile(result_url, suffix=".mp4")
                        if tmp_video:
                            try:
                                await bot.send_video(
                                    chat_id=user.tg_id,
                                    video=FSInputFile(tmp_video, filename=f"video_{gen.id}.mp4"),
                                    caption=caption,
                                    reply_markup=video_reply_markup,
                                )
                                video_sent = True
                            except TelegramEntityTooLarge as video_file_err:
                                video_too_large = True
                                logger.warning(
                                    "Video file send too large user=%s gen=%s url=%s err=%s",
                                    user.tg_id, gen.id, result_url, video_file_err,
                                )
                            except Exception as video_file_err:
                                logger.warning(
                                    "Video file send failed user=%s gen=%s url=%s err=%s",
                                    user.tg_id, gen.id, result_url, video_file_err,
                                )
                    if not video_sent:
                        if tmp_video is None:
                            tmp_video = await _download_url_to_tempfile(result_url, suffix=".mp4")
                        tmp_video_size = None
                        if tmp_video:
                            try:
                                tmp_video_size = Path(tmp_video).stat().st_size
                            except Exception:
                                tmp_video_size = None
                        if video_too_large and tmp_video_size and tmp_video_size > telegram_safe_video_bytes:
                            logger.warning(
                                "Video exceeds safe Telegram upload limit user=%s gen=%s url=%s size_bytes=%s",
                                user.tg_id, gen.id, result_url, tmp_video_size,
                            )
                        elif tmp_video:
                            try:
                                await bot.send_document(
                                    chat_id=user.tg_id,
                                    document=FSInputFile(tmp_video, filename=f"video_{gen.id}.mp4"),
                                    caption="📎 <b>Видео готово файлом</b>",
                                    reply_markup=video_reply_markup,
                                )
                                video_sent = True
                            except TelegramEntityTooLarge as video_doc_err:
                                video_too_large = True
                                logger.warning(
                                    "Video document send too large user=%s gen=%s url=%s err=%s",
                                    user.tg_id, gen.id, result_url, video_doc_err,
                                )
                            except Exception as video_doc_err:
                                logger.warning(
                                    "Video document fallback failed user=%s gen=%s url=%s err=%s",
                                    user.tg_id, gen.id, result_url, video_doc_err,
                                )
                        if not video_sent:
                            fallback_text = (
                                f"✅ <b>Видео готово</b>\n\n"
                                f"Если Telegram не принял ролик, вот прямая ссылка:\n{result_url}"
                            )
                            if video_too_large:
                                fallback_text = (
                                    f"✅ <b>Видео готово</b>\n\n"
                                    f"Ролик слишком большой для отправки ботом в Telegram.\n"
                                    f"Вот прямая ссылка на видео:\n{result_url}"
                                )
                            await bot.send_message(
                                chat_id=user.tg_id,
                                text=fallback_text,
                                reply_markup=video_reply_markup,
                            )
                            logger.info("Video link fallback sent user=%s gen=%s", user.tg_id, gen.id)
                    if tmp_video:
                        try:
                            Path(tmp_video).unlink(missing_ok=True)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to send KIE result user=%s gen=%s: %s", user.tg_id, gen.id, e)

    return {"ok": True}


def _suno_voice_status_contains(status: str, markers: set[str]) -> bool:
    normalized = status.strip().lower()
    return any(marker in normalized for marker in markers)


@app.post("/webhook/kie/suno-voice")
async def kie_suno_voice_webhook(
    request: Request,
    secret: str | None = None,
    stage: str | None = None,
    x_kie_webhook_secret: str | None = Header(default=None, alias="X-KIE-Webhook-Secret"),
) -> dict:
    _verify_kie_webhook_secret(secret, x_kie_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    task_id = extract_suno_voice_task_id(payload) or extract_task_id(payload)
    if not task_id:
        logger.warning("KIE Suno voice webhook without task_id stage=%s payload=%s", stage, payload)
        return {"ok": True}

    provider_status = extract_suno_voice_status(payload)
    provider_voice_id = extract_suno_provider_voice_id(payload)
    validate_phrase = extract_suno_validate_phrase(payload)
    error_msg = extract_suno_voice_error(payload)

    async with AsyncSessionLocal() as session:
        voice = await repo.get_suno_voice_by_validate_task_id(session, task_id)
        is_validation_task = voice is not None
        if not voice:
            voice = await repo.get_suno_voice_by_voice_task_id(session, task_id)
        if not voice:
            logger.warning("KIE Suno voice webhook unknown task_id=%s stage=%s", task_id, stage)
            return {"ok": True}

        if _suno_voice_status_contains(provider_status, SUNO_VOICE_FAILED_STATUSES):
            await repo.update_suno_voice(
                session,
                voice.id,
                status=SUNO_VOICE_STATUS_FAILED,
                error_msg=error_msg or "Suno voice processing failed",
            )
            return {"ok": True}

        if is_validation_task:
            if validate_phrase or "wait_validating" in provider_status.lower():
                await repo.update_suno_voice(
                    session,
                    voice.id,
                    status=SUNO_VOICE_STATUS_AWAITING_VERIFICATION,
                    validate_phrase=validate_phrase or getattr(voice, "validate_phrase", None),
                    error_msg=None,
                )
            return {"ok": True}

        if provider_voice_id and provider_status.lower() == "success":
            await repo.update_suno_voice(
                session,
                voice.id,
                status=SUNO_VOICE_STATUS_READY,
                voice_id=provider_voice_id,
                error_msg=None,
            )

    return {"ok": True}


@app.post("/webhook/kie/music")
async def kie_music_webhook(
    request: Request,
    secret: str | None = None,
    x_kie_webhook_secret: str | None = Header(default=None, alias="X-KIE-Webhook-Secret"),
) -> dict:
    _verify_kie_webhook_secret(secret, x_kie_webhook_secret)

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
    extracted_error_for_flags = "" if extracted_error in {"KIE generation failed", "Generation failed"} else extracted_error
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
        "don't reference specific artists",
        "do not reference specific artists",
        "contains artist name",
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
        if not db_gen:
            db_gen = await repo.get_generation_by_task_id(session, _web_task_lookup_id(task_id))
        if db_gen:
            if db_gen.status.value in {"done", "failed"}:
                pop_task(task_id)
                pop_miniapp_task(task_id)
                return {"ok": True}
            db_user = await repo.get_user_by_id(session, db_gen.user_id)

    # Pop only on final success or final failure.
    tg_id = pop_task(task_id)
    miniapp_gen_id = pop_miniapp_task(task_id)
    is_web_generation = is_web_task_id(getattr(db_gen, "task_id", None))
    if not tg_id and db_user and not is_web_generation:
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
                    if await repo.fail_generation(session, gen.id, err):
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
        if tg_id and int(tg_id) > 0 and bot:
            try:
                await bot.send_message(tg_id, "❌ Музыка готова, но ссылка не найдена.", reply_markup=back_to_menu_kb())
            except Exception:
                pass
        return {"ok": True}

    if generation_id:
        async with AsyncSessionLocal() as session:
            await repo.finish_generation(session, generation_id, audio_urls[0])

    if tg_id and int(tg_id) > 0 and bot:
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
            try:
                links = "\n".join(audio_urls)
                await bot.send_message(
                    tg_id,
                    f"🎵 <b>Трек готов</b>\n\nTelegram не принял аудио напрямую. Вот ссылка на результат:\n{links}",
                    reply_markup=back_to_menu_kb(),
                )
                logger.info("Music link fallback sent tg_id=%s task_id=%s", tg_id, task_id)
            except Exception as fallback_err:
                logger.warning("Failed to send music link fallback tg_id=%s: %s", tg_id, fallback_err)

    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "apix"}


LANDING_DIR = Path("landing")
LANDING_PAGE_ALIASES = {
    "/account": "account.html",
    "/login": "account.html",
    "/studio": "studio.html",
    "/gallery": "gallery.html",
    "/models": "models.html",
    "/contact": "contact.html",
    "/features": "features.html",
    "/guide": "guide.html",
}
if LANDING_DIR.exists():
    for route_path, file_name in LANDING_PAGE_ALIASES.items():
        async def _landing_alias(file_name=file_name):
            return FileResponse(LANDING_DIR / file_name)
        app.add_api_route(route_path, _landing_alias, methods=["GET", "HEAD"], include_in_schema=False)
    app.mount("/", StaticFiles(directory=str(LANDING_DIR), html=True), name="landing")
else:
    @app.get("/", response_class=PlainTextResponse)
    async def landing_not_built() -> str:
        return "Landing is not built."

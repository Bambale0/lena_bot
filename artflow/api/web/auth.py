from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import smtplib

import httpx
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import create_web_auth_token, verify_telegram_login_data
from api.web.deps import error_response, ok
from api.web.schemas import UserMe
from core.config import settings
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class ContactAuthRequest(BaseModel):
    contact: str = Field(..., min_length=5, max_length=256)


class ContactAuthVerifyRequest(BaseModel):
    contact: str = Field(..., min_length=5, max_length=256)
    code: str = Field(..., min_length=4, max_length=12)
    full_name: str | None = Field(default=None, max_length=256)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TG_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _bot_username() -> str:
    return str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")


def telegram_start_link(start_param: str) -> str:
    username = _bot_username()
    if not username or not start_param:
        return ""
    return f"https://t.me/{username}?start={start_param}"


def telegram_bot_link() -> str:
    username = _bot_username()
    return f"https://t.me/{username}" if username else ""


def _normalize_contact(contact: str) -> tuple[str, str]:
    raw = contact.strip()
    if EMAIL_RE.match(raw):
        return "email", raw.lower()
    telegram = raw.removeprefix("https://t.me/").removeprefix("http://t.me/").strip().lstrip("@")
    if TG_USERNAME_RE.match(telegram):
        return "telegram", telegram
    phone = re.sub(r"[^\d+]", "", raw)
    if phone.startswith("8") and len(phone) == 11:
        phone = "+7" + phone[1:]
    if phone.startswith("7") and len(phone) == 11:
        phone = "+" + phone
    if phone.startswith("+") and 10 <= len(re.sub(r"\D", "", phone)) <= 15:
        return "phone", phone
    raise ValueError("Укажите @username Telegram, email или телефон в международном формате")


def _hash_auth_code(contact_type: str, contact: str, code: str) -> str:
    secret = f"{settings.BOT_TOKEN}:{settings.WEBHOOK_SECRET}:web-contact-auth".encode()
    payload = f"{contact_type}:{contact}:{code}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _contact_user_label(contact_type: str, contact: str, full_name: str | None) -> str:
    if full_name and full_name.strip():
        return full_name.strip()
    if contact_type == "email":
        return contact
    if contact_type == "telegram":
        return f"@{contact}"
    return f"Пользователь {contact[-4:]}"


def _auth_payload(user) -> dict:
    return {
        "token": create_web_auth_token(user.tg_id),
        "token_type": "web",
        "expires_in": 30 * 24 * 60 * 60,
        "user": UserMe.from_user(
            user,
            admin_ids=settings.ADMIN_IDS,
            referral_link=telegram_start_link(getattr(user, "referral_code", "") or ""),
        ).model_dump(),
    }


def _show_debug_auth_code() -> bool:
    return bool(getattr(settings, "APIX_WEB_DEV_AUTH", False))


def _telegram_auth_enabled() -> bool:
    return bool(_bot_username() and getattr(settings, "BOT_TOKEN", ""))


def _smtp_email_enabled() -> bool:
    return bool(
        getattr(settings, "WEB_AUTH_EMAIL_ENABLED", False)
        and getattr(settings, "SMTP_HOST", "")
        and getattr(settings, "SMTP_FROM_EMAIL", "")
    )


def _resend_email_enabled() -> bool:
    return bool(
        getattr(settings, "WEB_AUTH_EMAIL_ENABLED", False)
        and getattr(settings, "RESEND_API_KEY", "")
        and _email_from_address()
    )


def _email_auth_enabled() -> bool:
    return _resend_email_enabled() or _smtp_email_enabled()


def _email_from_address() -> str:
    return str(
        getattr(settings, "RESEND_FROM_EMAIL", "")
        or getattr(settings, "SMTP_FROM_EMAIL", "")
        or ""
    ).strip()


def _email_from_name() -> str:
    return str(
        getattr(settings, "RESEND_FROM_NAME", "")
        or getattr(settings, "SMTP_FROM_NAME", "APIX Studio")
        or "APIX Studio"
    ).strip()


def _contact_login_modes() -> list[str]:
    modes: list[str] = []
    if _telegram_auth_enabled():
        modes.append("telegram")
    if _email_auth_enabled() or _show_debug_auth_code():
        modes.append("email")
    return modes


def _contact_login_hint(modes: list[str]) -> str | None:
    if "telegram" in modes and "email" in modes:
        return "Укажи @username Telegram или email — пришлём код"
    if "telegram" in modes:
        return "Укажи @username Telegram — код придёт в бот"
    if "email" in modes:
        return "Укажи email — пришлём код для входа"
    return None


def _send_email_auth_code_sync(*, to_email: str, code: str) -> None:
    message = EmailMessage()
    sender_email = _email_from_address()
    sender_name = _email_from_name()
    message["Subject"] = "Код входа в APIX Studio"
    message["From"] = f'{sender_name} <{sender_email}>' if sender_email else sender_name
    message["To"] = to_email
    reply_to = str(getattr(settings, "SMTP_REPLY_TO", "") or "").strip()
    if reply_to:
        message["Reply-To"] = reply_to
    text = (
        f"Код входа в APIX Studio: {code}\n\n"
        "Он действует 10 минут. Если это были не вы — просто игнорируйте письмо."
    )
    html = (
        '<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">'
        '<h2 style="margin:0 0 16px">APIX Studio</h2>'
        '<p>Ваш код входа:</p>'
        f'<p style="font-size:28px;font-weight:700;letter-spacing:4px"><code>{code}</code></p>'
        '<p>Код действует 10 минут. Если это были не вы — просто игнорируйте письмо.</p>'
        '</div>'
    )
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    host = str(getattr(settings, "SMTP_HOST", "") or "")
    port = int(getattr(settings, "SMTP_PORT", 587) or 587)
    username = str(getattr(settings, "SMTP_USERNAME", "") or "")
    password = str(getattr(settings, "SMTP_PASSWORD", "") or "")
    use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))
    use_tls = bool(getattr(settings, "SMTP_USE_TLS", True))

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


async def _send_email_auth_code_resend(*, to_email: str, code: str) -> None:
    sender_email = _email_from_address()
    sender_name = _email_from_name()
    reply_to = str(getattr(settings, "SMTP_REPLY_TO", "") or "").strip()
    subject = "Код входа в APIX Studio"
    text = f"""Код входа в APIX Studio: {code}

Он действует 10 минут. Если это были не вы — просто игнорируйте письмо."""
    html = (
        '<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">'
        '<h2 style="margin:0 0 16px">APIX Studio</h2>'
        '<p>Ваш код входа:</p>'
        f'<p style="font-size:28px;font-weight:700;letter-spacing:4px"><code>{code}</code></p>'
        '<p>Код действует 10 минут. Если это были не вы — просто игнорируйте письмо.</p>'
        '</div>'
    )
    payload = {
        "from": f"{sender_name} <{sender_email}>" if sender_name else sender_email,
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
        )
    if response.status_code not in {200, 201, 202}:
        detail = response.text.strip()
        try:
            data = response.json()
            detail = data.get("message") or data.get("error") or detail
        except Exception:
            pass
        raise RuntimeError(detail or f"HTTP {response.status_code}")


async def _deliver_email_auth_code(*, email: str, code: str) -> None:
    try:
        if _resend_email_enabled():
            await _send_email_auth_code_resend(to_email=email, code=code)
        elif _smtp_email_enabled():
            await asyncio.to_thread(_send_email_auth_code_sync, to_email=email, code=code)
        else:
            raise RuntimeError("Email-провайдер не настроен")
    except Exception as exc:
        raise RuntimeError(f"Не удалось отправить код на email: {exc}") from exc


async def _deliver_telegram_auth_code(*, tg_id: int, username: str, code: str) -> None:
    text = (
        f"🔐 Код входа в APIX Studio: <code>{code}</code>\n\n"
        "Он действует 10 минут. Если это не вы — просто игнорируйте сообщение."
    )
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        await bot.send_message(chat_id=tg_id, text=text, parse_mode="HTML")
    except TelegramForbiddenError as exc:
        raise RuntimeError(f"Бот не может написать @{username}. Сначала открой бота и нажми Start") from exc
    except TelegramAPIError as exc:
        raise RuntimeError(f"Не удалось отправить код в Telegram: {exc}") from exc
    finally:
        await bot.session.close()


@router.get("/auth/config")
async def auth_config() -> dict:
    modes = _contact_login_modes()
    return ok({
        "bot_username": _bot_username(),
        "bot_link": telegram_bot_link(),
        "contact_login": bool(modes),
        "contact_login_modes": modes,
        "contact_login_hint": _contact_login_hint(modes),
    })


@router.post("/auth/telegram-login")
async def telegram_login(
    body: TelegramLoginRequest,
    session: AsyncSession = Depends(get_session),
    x_web_auth_token: str | None = Header(default=None, alias="X-Web-Auth-Token"),
) -> dict:
    tg_user = verify_telegram_login_data(body.model_dump())
    first_name = str(tg_user.get("first_name") or "").strip()
    last_name = str(tg_user.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
    username = str(tg_user.get("username") or "").strip() or None

    tg_id = int(tg_user["id"])
    current_user = None
    if x_web_auth_token:
        try:
            from api.miniapp_auth import verify_web_auth_token

            current_tg_id = verify_web_auth_token(x_web_auth_token)
            current_user = await repo.get_user_by_tg_id(session, current_tg_id)
        except Exception:
            current_user = None

    user = await repo.get_user_by_tg_id(session, tg_id)
    if current_user and int(getattr(current_user, "tg_id", 0)) < 0:
        if user and user.id != current_user.id:
            return error_response(409, "Этот Telegram уже привязан к другому аккаунту")
        user = await repo.bind_user_telegram(
            session,
            user_id=current_user.id,
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            photo_url=tg_user.get("photo_url"),
        )
    if not user:
        user = await repo.create_user(
            session,
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            welcome_credits=settings.WELCOME_BONUS_CREDITS,
        )

    return ok(_auth_payload(user))


@router.post("/auth/contact/request")
async def contact_auth_request(
    body: ContactAuthRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        contact_type, contact = _normalize_contact(body.contact)
    except ValueError as exc:
        return error_response(422, str(exc))

    if contact_type == "phone":
        return error_response(503, "Вход по телефону пока не настроен — используйте Telegram или email")
    if contact_type == "email" and not (_email_auth_enabled() or _show_debug_auth_code()):
        return error_response(503, "Вход по email пока не настроен — используйте Telegram")

    linked_user = None
    if contact_type == "telegram":
        linked_user = await repo.get_user_by_username(session, contact)
        if not linked_user:
            return error_response(404, "Пользователь с таким @username не найден. Сначала зайдите в бота APIX")
        if int(getattr(linked_user, "tg_id", 0)) <= 0:
            return error_response(409, "Для этого аккаунта Telegram ещё не привязан")

    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(timezone.utc)
    recent_code = await repo.get_recent_web_auth_code(
        session,
        contact_type=contact_type,
        contact=contact,
        now=now,
    )
    if recent_code and getattr(recent_code, "created_at", None):
        retry_after = 60 - int(max(0, (now - recent_code.created_at).total_seconds()))
        if retry_after > 0:
            return ok({
                "contact_type": contact_type,
                "contact": contact,
                "expires_in": 10 * 60,
                "retry_after": retry_after,
                "delivery": "debug" if _show_debug_auth_code() else "provider",
                "message": f"Код уже запрошен. Повторите через {retry_after} сек.",
            })
    await repo.consume_active_web_auth_codes(
        session,
        contact_type=contact_type,
        contact=contact,
        now=now,
    )
    await repo.create_web_auth_code(
        session,
        contact_type=contact_type,
        contact=contact,
        code_hash=_hash_auth_code(contact_type, contact, code),
        expires_at=now + timedelta(minutes=10),
    )
    if contact_type == "telegram" and linked_user is not None:
        try:
            await _deliver_telegram_auth_code(
                tg_id=int(linked_user.tg_id),
                username=str(getattr(linked_user, "username", contact) or contact),
                code=code,
            )
        except RuntimeError as exc:
            await repo.consume_active_web_auth_codes(session, contact_type=contact_type, contact=contact, now=now)
            return error_response(503, str(exc))
    elif contact_type == "email" and not _show_debug_auth_code():
        try:
            await _deliver_email_auth_code(email=contact, code=code)
        except RuntimeError as exc:
            await repo.consume_active_web_auth_codes(session, contact_type=contact_type, contact=contact, now=now)
            return error_response(503, str(exc))
    payload = {
        "contact_type": contact_type,
        "contact": contact,
        "expires_in": 10 * 60,
        "delivery": "debug" if _show_debug_auth_code() and contact_type in {"email", "phone"} else ("telegram" if contact_type == "telegram" else "provider"),
        "message": "Код отправлен. Введите его, чтобы открыть кабинет.",
    }
    if _show_debug_auth_code() and contact_type in {"email", "phone"}:
        payload["debug_code"] = code
    return ok(payload)


@router.post("/auth/contact/verify")
async def contact_auth_verify(
    body: ContactAuthVerifyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        contact_type, contact = _normalize_contact(body.contact)
    except ValueError as exc:
        return error_response(422, str(exc))

    now = datetime.now(timezone.utc)
    code_hash = _hash_auth_code(contact_type, contact, body.code.strip())
    auth_code = await repo.get_active_web_auth_code(
        session,
        contact_type=contact_type,
        contact=contact,
        code_hash=code_hash,
        now=now,
    )
    if not auth_code:
        await repo.increment_web_auth_attempts(session, contact_type=contact_type, contact=contact, now=now)
        return error_response(401, "Неверный или устаревший код")

    await repo.consume_web_auth_code(session, auth_code.id, now=now)
    if contact_type == "email":
        user = await repo.get_user_by_email(session, contact)
        if not user:
            user = await repo.create_contact_user(
                session,
                email=contact,
                full_name=_contact_user_label(contact_type, contact, body.full_name),
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
            )
    elif contact_type == "telegram":
        user = await repo.get_user_by_username(session, contact)
        if not user:
            return error_response(404, "Пользователь с таким @username не найден")
    else:
        user = await repo.get_user_by_phone(session, contact)
        if not user:
            user = await repo.create_contact_user(
                session,
                phone=contact,
                full_name=_contact_user_label(contact_type, contact, body.full_name),
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
            )
    return ok(_auth_payload(user))

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import create_web_auth_token, verify_telegram_login_data
from api.web.deps import WEB_AUTH_COOKIE_NAME, error_response, ok
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
    referral_code: str | None = Field(default=None, max_length=128)


class ContactAuthRequest(BaseModel):
    contact: str = Field(..., min_length=5, max_length=256)


class ContactAuthVerifyRequest(BaseModel):
    contact: str = Field(..., min_length=5, max_length=256)
    code: str = Field(..., min_length=4, max_length=12)
    full_name: str | None = Field(default=None, max_length=256)
    referral_code: str | None = Field(default=None, max_length=128)


class PasswordLoginRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)


class PasswordRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=256)
    referral_code: str | None = Field(default=None, max_length=128)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TG_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
REFERRAL_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,128}$")
PASSWORD_HASH_ITERATIONS = 390_000
PASSWORD_LOGIN_WINDOW_SECONDS = 15 * 60
PASSWORD_LOGIN_MAX_FAILURES = 8
_PASSWORD_LOGIN_FAILURES: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_raw, salt, digest = encoded.split("$", 3)
        iterations = int(iterations_raw)
    except (ValueError, TypeError):
        return False
    if algorithm != "pbkdf2_sha256" or iterations < 120_000:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, digest)


def _is_production() -> bool:
    return str(getattr(settings, "ENV", "") or "").lower() == "production"


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        WEB_AUTH_COOKIE_NAME,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        WEB_AUTH_COOKIE_NAME,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        path="/",
    )


def _password_attempt_key(login: str) -> str:
    return login.strip().lower()


def _password_retry_after(login: str) -> int:
    now = time.monotonic()
    key = _password_attempt_key(login)
    failures = [
        item for item in _PASSWORD_LOGIN_FAILURES.get(key, [])
        if now - item < PASSWORD_LOGIN_WINDOW_SECONDS
    ]
    if failures:
        _PASSWORD_LOGIN_FAILURES[key] = failures
    else:
        _PASSWORD_LOGIN_FAILURES.pop(key, None)
    if len(failures) < PASSWORD_LOGIN_MAX_FAILURES:
        return 0
    return max(1, int(PASSWORD_LOGIN_WINDOW_SECONDS - (now - failures[0])))


def _record_password_failure(login: str) -> None:
    key = _password_attempt_key(login)
    _PASSWORD_LOGIN_FAILURES.setdefault(key, []).append(time.monotonic())


def _clear_password_failures(login: str) -> None:
    _PASSWORD_LOGIN_FAILURES.pop(_password_attempt_key(login), None)


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


def web_referral_link(referral_code: str) -> str:
    code = _normalize_referral_code(referral_code)
    if not code:
        return ""
    base = str(getattr(settings, "WEB_PUBLIC_URL", "") or "").strip().rstrip("/")
    if not base:
        base = str(getattr(settings, "WEBHOOK_URL", "") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/account.html?{urlencode({'ref': code})}"


def _normalize_referral_code(referral_code: str | None) -> str | None:
    code = str(referral_code or "").strip()
    if not code or not REFERRAL_CODE_RE.match(code):
        return None
    return code


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


async def _resolve_referral_chain(
    session: AsyncSession,
    referral_code: str | None,
    *,
    current_user=None,
    current_tg_id: int | None = None,
):
    code = _normalize_referral_code(referral_code)
    if not code or settings.REFERRAL_FREEZE:
        return None, None, None

    referrer = await repo.get_user_by_referral_code(session, code)
    if not referrer:
        return None, None, None

    current_user_id = int(getattr(current_user, "id", 0) or 0) or None
    tg_id = current_tg_id
    if tg_id is None:
        try:
            tg_id = int(getattr(current_user, "tg_id", 0) or 0)
        except (TypeError, ValueError):
            tg_id = None
    if referrer.id == current_user_id or (tg_id and int(getattr(referrer, "tg_id", 0) or 0) == tg_id):
        return None, None, None

    chain_user = referrer
    seen_chain_ids: set[int] = set()
    for _ in range(50):
        chain_user_id = getattr(chain_user, "id", None)
        if chain_user_id is None:
            break
        if chain_user_id in seen_chain_ids:
            return None, None, None
        if chain_user_id == current_user_id or (tg_id and int(getattr(chain_user, "tg_id", 0) or 0) == tg_id):
            return None, None, None
        seen_chain_ids.add(chain_user_id)
        parent_id = getattr(chain_user, "referrer_id", None)
        if not parent_id:
            break
        parent = await repo.get_user_by_id(session, parent_id)
        if not parent:
            break
        chain_user = parent
    else:
        return None, None, None

    seen_ids: set[int] = {referrer.id}
    referrer_l2 = None
    referrer_l3 = None
    if getattr(referrer, "referrer_id", None) and referrer.referrer_id not in seen_ids:
        referrer_l2 = await repo.get_user_by_id(session, referrer.referrer_id)
        if referrer_l2 and (referrer_l2.id in seen_ids or (tg_id and int(getattr(referrer_l2, "tg_id", 0) or 0) == tg_id)):
            referrer_l2 = None
        elif referrer_l2:
            seen_ids.add(referrer_l2.id)
    if referrer_l2 and getattr(referrer_l2, "referrer_id", None) and referrer_l2.referrer_id not in seen_ids:
        referrer_l3 = await repo.get_user_by_id(session, referrer_l2.referrer_id)
        if referrer_l3 and (referrer_l3.id in seen_ids or (tg_id and int(getattr(referrer_l3, "tg_id", 0) or 0) == tg_id)):
            referrer_l3 = None
    return referrer, referrer_l2, referrer_l3


def _has_referrer(user) -> bool:
    return bool(
        getattr(user, "referrer_id", None)
        or getattr(user, "referrer_l2_id", None)
        or getattr(user, "referrer_l3_id", None)
    )


def _referral_bonus_source_id(user) -> str:
    try:
        tg_id = int(getattr(user, "tg_id", 0) or 0)
    except (TypeError, ValueError):
        tg_id = 0
    return str(tg_id if tg_id > 0 else getattr(user, "id", ""))


async def _award_referral_signup_bonus(session: AsyncSession, referrer, user) -> None:
    await repo.add_credits(
        session,
        referrer.id,
        settings.REFERRAL_L1_CREDITS,
        entry_type="referral_signup_bonus",
        source_type="user",
        source_id=_referral_bonus_source_id(user),
        note="L1 referral signup bonus",
    )


async def _bind_existing_user_referral(
    session: AsyncSession,
    user,
    referral_code: str | None,
):
    if not user or _has_referrer(user):
        return user
    referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(
        session,
        referral_code,
        current_user=user,
    )
    if not referrer:
        return user
    bound = await repo.bind_user_referrer_once(
        session,
        user.id,
        referrer=referrer,
        referrer_l2=referrer_l2,
        referrer_l3=referrer_l3,
    )
    if not bound:
        return user
    await _award_referral_signup_bonus(session, referrer, user)
    return await repo.get_user_by_id(session, user.id) or user


def _auth_payload(user, response: Response | None = None) -> dict:
    token = create_web_auth_token(user.tg_id)
    if response is not None:
        _set_auth_cookie(response, token)
    return {
        "token": token,
        "token_type": "web",
        "expires_in": 30 * 24 * 60 * 60,
        "user": UserMe.from_user(
            user,
            admin_ids=settings.ADMIN_IDS,
            referral_link=web_referral_link(getattr(user, "referral_code", "") or ""),
        ).model_dump(),
    }


async def _user_by_login(session: AsyncSession, login: str):
    try:
        contact_type, contact = _normalize_contact(login)
    except ValueError:
        return None
    if contact_type == "email":
        return await repo.get_user_by_email(session, contact)
    if contact_type == "phone":
        return await repo.get_user_by_phone(session, contact)
    return await repo.get_user_by_username(session, contact)


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
        "password_login": True,
    })


@router.post("/auth/telegram-login")
async def telegram_login(
    body: TelegramLoginRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_web_auth_token: str | None = Header(default=None, alias="X-Web-Auth-Token"),
) -> dict:
    tg_user = verify_telegram_login_data(body.model_dump(exclude={"referral_code"}))
    first_name = str(tg_user.get("first_name") or "").strip()
    last_name = str(tg_user.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
    username = str(tg_user.get("username") or "").strip() or None
    referral_code = _normalize_referral_code(body.referral_code)

    tg_id = int(tg_user["id"])
    current_user = None
    web_auth_token = x_web_auth_token or request.cookies.get(WEB_AUTH_COOKIE_NAME)
    if web_auth_token:
        try:
            from api.miniapp_auth import verify_web_auth_token

            current_tg_id = verify_web_auth_token(web_auth_token)
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
        referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(
            session,
            referral_code,
            current_tg_id=tg_id,
        )
        user = await repo.create_user(
            session,
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            welcome_credits=settings.WELCOME_BONUS_CREDITS,
            referrer=referrer,
            referrer_l2=referrer_l2,
            referrer_l3=referrer_l3,
        )
        if referrer:
            await _award_referral_signup_bonus(session, referrer, user)
    else:
        user = await _bind_existing_user_referral(session, user, referral_code)

    return ok(_auth_payload(user, response=response))


@router.post("/auth/password-login")
async def password_login(
    body: PasswordLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    retry_after = _password_retry_after(body.login)
    if retry_after > 0:
        return error_response(429, f"Слишком много попыток. Повторите через {retry_after} сек.")
    user = await _user_by_login(session, body.login)
    if not user or getattr(user, "is_banned", False):
        _record_password_failure(body.login)
        return error_response(401, "Неверный логин или пароль")
    if not verify_password(body.password, getattr(user, "password_hash", None)):
        _record_password_failure(body.login)
        return error_response(401, "Неверный логин или пароль")
    _clear_password_failures(body.login)
    return ok(_auth_payload(user, response=response))


@router.post("/auth/password-register")
async def password_register(
    body: PasswordRegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        contact_type, email = _normalize_contact(body.email)
    except ValueError as exc:
        return error_response(422, str(exc))
    if contact_type != "email":
        return error_response(422, "Регистрация с паролем доступна только по email")
    existing = await repo.get_user_by_email(session, email)
    if existing:
        return error_response(409, "Аккаунт с таким email уже существует")
    referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(session, body.referral_code)
    user = await repo.create_contact_user(
        session,
        email=email,
        full_name=_contact_user_label("email", email, body.full_name),
        welcome_credits=settings.WELCOME_BONUS_CREDITS,
        referrer=referrer,
        referrer_l2=referrer_l2,
        referrer_l3=referrer_l3,
    )
    if referrer:
        await _award_referral_signup_bonus(session, referrer, user)
    user = await repo.set_user_password_hash(session, user.id, hash_password(body.password)) or user
    return ok(_auth_payload(user, response=response))


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    _clear_auth_cookie(response)
    return ok()


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
    response: Response,
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
            referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(session, body.referral_code)
            user = await repo.create_contact_user(
                session,
                email=contact,
                full_name=_contact_user_label(contact_type, contact, body.full_name),
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
                referrer=referrer,
                referrer_l2=referrer_l2,
                referrer_l3=referrer_l3,
            )
            if referrer:
                await _award_referral_signup_bonus(session, referrer, user)
    elif contact_type == "telegram":
        user = await repo.get_user_by_username(session, contact)
        if not user:
            return error_response(404, "Пользователь с таким @username не найден")
    else:
        user = await repo.get_user_by_phone(session, contact)
        if not user:
            referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(session, body.referral_code)
            user = await repo.create_contact_user(
                session,
                phone=contact,
                full_name=_contact_user_label(contact_type, contact, body.full_name),
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
                referrer=referrer,
                referrer_l2=referrer_l2,
                referrer_l3=referrer_l3,
            )
            if referrer:
                await _award_referral_signup_bonus(session, referrer, user)
    user = await _bind_existing_user_referral(session, user, body.referral_code)
    return ok(_auth_payload(user, response=response))

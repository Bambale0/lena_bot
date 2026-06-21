from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.auth import (
    EMAIL_RE,
    TG_USERNAME_RE,
    _normalize_contact,
    hash_password,
    verify_password,
    web_referral_link,
)
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import UserMe
from core.config import settings
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=32)
    photo_url: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=8)


class PasswordUpdateRequest(BaseModel):
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


def _user_payload(user) -> dict:
    return UserMe.from_user(
        user,
        admin_ids=settings.ADMIN_IDS,
        referral_link=web_referral_link(getattr(user, "referral_code", "") or ""),
    ).model_dump()


@router.get("/me")
async def me(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    return ok(_user_payload(user))


@router.put("/me/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")

    updates: dict[str, object] = {}
    if body.full_name is not None:
        updates["full_name"] = body.full_name.strip() or None
    if body.username is not None:
        username = body.username.strip().lstrip("@")
        if username:
            if not TG_USERNAME_RE.match(username):
                return error_response(422, "Некорректный username")
            existing = await repo.get_user_by_username(session, username)
            if existing and int(existing.id) != int(user.id):
                return error_response(409, "Username уже занят")
            updates["username"] = username
        else:
            updates["username"] = None
    if body.email is not None:
        email = body.email.strip().lower()
        if email:
            if not EMAIL_RE.match(email):
                return error_response(422, "Некорректный email")
            existing = await repo.get_user_by_email(session, email)
            if existing and int(existing.id) != int(user.id):
                return error_response(409, "Email уже занят")
            updates["email"] = email
        else:
            updates["email"] = None
    if body.phone is not None:
        phone = body.phone.strip()
        if phone:
            try:
                contact_type, normalized_phone = _normalize_contact(phone)
            except ValueError as exc:
                return error_response(422, str(exc))
            if contact_type != "phone":
                return error_response(422, "Укажите телефон в международном формате")
            existing = await repo.get_user_by_phone(session, normalized_phone)
            if existing and int(existing.id) != int(user.id):
                return error_response(409, "Телефон уже занят")
            updates["phone"] = normalized_phone
        else:
            updates["phone"] = None
    if body.photo_url is not None:
        photo_url = body.photo_url.strip()
        if photo_url and not photo_url.startswith(("http://", "https://", "/static/")):
            return error_response(422, "Некорректная ссылка на фото")
        updates["photo_url"] = photo_url or None
    if body.language is not None:
        language = body.language.strip().lower()
        if language not in {"ru", "en"}:
            return error_response(422, "Unsupported language")
        updates["language"] = language

    updated = await repo.update_user_profile(session, user.id, **updates)
    return ok(_user_payload(updated or user))


@router.put("/me/password")
async def update_password(
    body: PasswordUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    if getattr(user, "password_hash", None):
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            return error_response(401, "Текущий пароль неверный")
    updated = await repo.set_user_password_hash(session, user.id, hash_password(body.new_password))
    return ok(_user_payload(updated or user))

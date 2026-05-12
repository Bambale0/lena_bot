# bot/middlewares/auth.py
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram import Bot
from aiogram.types import TelegramObject, Update, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.deep_links import parse_start_payload
from core.config import settings
from db import repository as repo

logger = logging.getLogger(__name__)


async def _notify_referral(bot: Bot | None, tg_id: int, text: str) -> None:
    if not bot:
        return
    try:
        await bot.send_message(tg_id, text)
    except Exception as e:
        logger.warning("Failed to send referral notification to %s: %s", tg_id, e)


def _extract_start_payload(update: Update | None) -> str | None:
    if not update or not update.message or not update.message.text:
        return None
    parts = update.message.text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    command = (parts[0] or "").strip().lower()
    if not command.startswith("/start"):
        return None
    payload = parts[1].strip()
    return payload or None


def _describe_entrypoint(update: Update | None) -> str:
    if not update:
        return "update=None"
    if update.message:
        text = (update.message.text or "").strip()
        if text:
            return f"message:{text[:200]}"
        if update.message.web_app_data:
            return "message:web_app_data"
        if update.message.photo:
            return "message:photo"
        return "message:<non-text>"
    if update.callback_query:
        data = (update.callback_query.data or "").strip()
        return f"callback:{data[:200]}" if data else "callback:<empty>"
    if update.inline_query:
        return "inline_query"
    return update.model_dump_json(exclude_none=True)[:200]


async def _resolve_referral_chain(
    session: AsyncSession,
    ref_code: str | None,
    *,
    tg_user_id: int,
) -> tuple[Any | None, Any | None, Any | None]:
    if not ref_code:
        return None, None, None
    referrer = await repo.get_user_by_referral_code(session, ref_code)
    if not referrer or referrer.tg_id == tg_user_id:
        return None, None, None

    referrer_l2 = None
    referrer_l3 = None
    if referrer.referrer_id:
        referrer_l2 = await repo.get_user_by_id(session, referrer.referrer_id)
    if referrer_l2 and referrer_l2.referrer_id:
        referrer_l3 = await repo.get_user_by_id(session, referrer_l2.referrer_id)
    return referrer, referrer_l2, referrer_l3


class AuthMiddleware(BaseMiddleware):
    """
    Авто-регистрация пользователя, проверка бана.
    Добавляет db_user в data для хендлеров.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        tg_user: TgUser | None = data.get("event_from_user")
        bot: Bot | None = data.get("bot")

        if not tg_user or tg_user.is_bot:
            return await handler(event, data)

        db_user = await repo.get_user_by_tg_id(session, tg_user.id)
        update: Update | None = event if isinstance(event, Update) else data.get("event_update")
        raw_payload = _extract_start_payload(update)
        start_payload = parse_start_payload(raw_payload)
        ref_code = start_payload.ref_code
        entrypoint = _describe_entrypoint(update)
        if ref_code:
            logger.info(
                "Referral start payload: tg_id=%s ref_code=%s existing_user=%s entrypoint=%s",
                tg_user.id,
                start_payload.raw or ref_code,
                bool(db_user),
                entrypoint,
            )

        if db_user is None:
            referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(
                session,
                ref_code,
                tg_user_id=tg_user.id,
            )
            logger.info(
                "Referral create resolve: tg_id=%s ref_code=%s referrer=%s l2=%s l3=%s",
                tg_user.id,
                start_payload.raw or ref_code,
                getattr(referrer, "id", None),
                getattr(referrer_l2, "id", None),
                getattr(referrer_l3, "id", None),
            )
            if not ref_code:
                logger.info("Referral create without payload: tg_id=%s entrypoint=%s", tg_user.id, entrypoint)

            db_user = await repo.create_user(
                session,
                tg_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
                referrer=referrer,
                referrer_l2=referrer_l2,
                referrer_l3=referrer_l3,
            )

            # Начисляем реферальные бонусы (только L1 — кредитами)
            if referrer:
                logger.info("Referral bind on create: tg_id=%s -> referrer_id=%s", tg_user.id, referrer.id)
                await repo.add_credits(session, referrer.id, settings.REFERRAL_L1_CREDITS)
                logger.info("Referral L1 bonus: %s -> %s", tg_user.id, referrer.tg_id)
                await _notify_referral(
                    bot,
                    referrer.tg_id,
                    "🎉 По твоей ссылке пришёл новый пользователь!\n"
                    f"+{settings.REFERRAL_L1_CREDITS} 💋 начислено.",
                )
        elif (
            ref_code
            and not db_user.is_banned
            and db_user.referrer_id is None
            and db_user.referrer_l2_id is None
            and db_user.referrer_l3_id is None
        ):
            referrer, referrer_l2, referrer_l3 = await _resolve_referral_chain(
                session,
                ref_code,
                tg_user_id=tg_user.id,
            )
            if referrer:
                logger.info("Referral late-bind attempt: tg_id=%s user_id=%s referrer_id=%s", tg_user.id, db_user.id, referrer.id)
                bound = await repo.bind_user_referrer_once(
                    session,
                    db_user.id,
                    referrer=referrer,
                    referrer_l2=referrer_l2,
                    referrer_l3=referrer_l3,
                )
                if bound:
                    logger.info("Referral late-bind success: tg_id=%s -> referrer_id=%s", tg_user.id, referrer.id)
                    await repo.add_credits(session, referrer.id, settings.REFERRAL_L1_CREDITS)
                    logger.info("Referral L1 late bind: %s -> %s", tg_user.id, referrer.tg_id)
                    await _notify_referral(
                        bot,
                        referrer.tg_id,
                        "🎉 По твоей ссылке пришёл новый пользователь!\n"
                        f"+{settings.REFERRAL_L1_CREDITS} 💋 начислено.",
                    )
                    db_user = await repo.get_user_by_tg_id(session, tg_user.id)
                else:
                    logger.info("Referral late-bind skipped: tg_id=%s user_id=%s already_bound_or_race=true", tg_user.id, db_user.id)
            else:
                logger.info("Referral late-bind without resolvable referrer: tg_id=%s ref_code=%s entrypoint=%s", tg_user.id, start_payload.raw or ref_code, entrypoint)

        elif db_user.is_banned:
            return  # Просто игнорируем забаненных

        data["db_user"] = db_user
        return await handler(event, data)

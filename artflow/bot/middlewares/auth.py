# bot/middlewares/auth.py
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.maintenance_mode import is_maintenance_mode
from bot.utils.deep_links import parse_start_payload
from core.config import settings
from core.referral_antifraud import ensure_referrer_allowed
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
    current_user_id: int | None = None,
) -> tuple[Any | None, Any | None, Any | None]:
    if not ref_code:
        return None, None, None
    referrer = await repo.get_user_by_referral_code(session, ref_code)
    if not referrer or referrer.tg_id == tg_user_id or referrer.id == current_user_id:
        return None, None, None
    if not await ensure_referrer_allowed(
        session,
        referrer=referrer,
        candidate_label=f"telegram:{tg_user_id}",
    ):
        return None, None, None

    chain_user = referrer
    seen_chain_ids: set[int] = set()
    for _ in range(50):
        chain_user_id = getattr(chain_user, "id", None)
        if chain_user_id is None:
            break
        if chain_user_id in seen_chain_ids:
            logger.warning(
                "Referral chain cycle detected: tg_user_id=%s ref_code=%s repeated_user_id=%s",
                tg_user_id,
                ref_code,
                chain_user_id,
            )
            return None, None, None
        if chain_user_id == current_user_id or getattr(chain_user, "tg_id", None) == tg_user_id:
            logger.warning(
                "Referral bind would create cycle: tg_user_id=%s current_user_id=%s ref_code=%s referrer_id=%s",
                tg_user_id,
                current_user_id,
                ref_code,
                referrer.id,
            )
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
        logger.warning(
            "Referral chain too deep: tg_user_id=%s current_user_id=%s ref_code=%s referrer_id=%s",
            tg_user_id,
            current_user_id,
            ref_code,
            referrer.id,
        )
        return None, None, None

    seen_ids: set[int] = {referrer.id}
    referrer_l2 = None
    referrer_l3 = None
    if referrer.referrer_id and referrer.referrer_id not in seen_ids:
        referrer_l2 = await repo.get_user_by_id(session, referrer.referrer_id)
        if referrer_l2 and (referrer_l2.id in seen_ids or referrer_l2.tg_id == tg_user_id):
            logger.warning("Referral chain cycle detected at L2: tg_user_id=%s ref_code=%s referrer_id=%s l2_id=%s", tg_user_id, ref_code, referrer.id, referrer_l2.id)
            referrer_l2 = None
        elif referrer_l2:
            seen_ids.add(referrer_l2.id)
    if referrer_l2 and referrer_l2.referrer_id and referrer_l2.referrer_id not in seen_ids:
        referrer_l3 = await repo.get_user_by_id(session, referrer_l2.referrer_id)
        if referrer_l3 and (referrer_l3.id in seen_ids or referrer_l3.tg_id == tg_user_id):
            logger.warning("Referral chain cycle detected at L3: tg_user_id=%s ref_code=%s referrer_id=%s l2_id=%s l3_id=%s", tg_user_id, ref_code, referrer.id, referrer_l2.id, referrer_l3.id)
            referrer_l3 = None
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

        if is_maintenance_mode() and tg_user.id not in settings.ADMIN_IDS:
            if bot:
                await bot.send_message(
                    tg_user.id,
                    "🛠 Бот временно в техрежиме. Попробуйте позже.",
                )
            return None

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

            referral_freeze = settings.REFERRAL_FREEZE
            if referral_freeze and referrer:
                logger.warning("Referral freeze active: skip bind on create tg_id=%s referrer_id=%s", tg_user.id, referrer.id)
            db_user = await repo.create_user(
                session,
                tg_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
                welcome_credits=settings.WELCOME_BONUS_CREDITS,
                referrer=None if referral_freeze else referrer,
                referrer_l2=None if referral_freeze else referrer_l2,
                referrer_l3=None if referral_freeze else referrer_l3,
            )

            if referrer and not referral_freeze:
                logger.info("Referral bind on create: tg_id=%s -> referrer_id=%s; reward deferred until first paid top-up", tg_user.id, referrer.id)
                await _notify_referral(
                    bot,
                    referrer.tg_id,
                    "🎉 По твоей ссылке пришёл новый пользователь!\n"
                    f"+{settings.REFERRAL_L1_CREDITS} 💋 начислим после его первого пополнения.",
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
                current_user_id=db_user.id,
            )
            if referrer:
                if settings.REFERRAL_FREEZE:
                    logger.warning("Referral freeze active: skip late-bind tg_id=%s user_id=%s referrer_id=%s", tg_user.id, db_user.id, referrer.id)
                    data["db_user"] = db_user
                    return await handler(event, data)
                logger.info("Referral late-bind attempt: tg_id=%s user_id=%s referrer_id=%s", tg_user.id, db_user.id, referrer.id)
                bound = await repo.bind_user_referrer_once(
                    session,
                    db_user.id,
                    referrer=referrer,
                    referrer_l2=referrer_l2,
                    referrer_l3=referrer_l3,
                )
                if bound:
                    logger.info("Referral late-bind success: tg_id=%s -> referrer_id=%s; reward deferred until first paid top-up", tg_user.id, referrer.id)
                    db_user = await repo.get_user_by_tg_id(session, tg_user.id)
                else:
                    logger.info("Referral late-bind skipped: tg_id=%s user_id=%s already_bound_or_race=true", tg_user.id, db_user.id)
            else:
                logger.info("Referral late-bind without resolvable referrer: tg_id=%s ref_code=%s entrypoint=%s", tg_user.id, start_payload.raw or ref_code, entrypoint)

            # Referral code not found — notify user
            if bot:
                try:
                    await _notify_referral(
                        bot,
                        tg_user.id,
                        "ℹ️ Реферальный бонус не начислен.\n"
                        "Код приглашения не найден или ссылка некорректна.\n\n"
                        "💡 Попросите у партнёра новую ссылку.",
                    )
                except Exception:
                    pass

        elif db_user.is_banned:
            return  # Просто игнорируем забаненных

        # User has ref_code but already has a referrer — notify them
        if ref_code and db_user and getattr(db_user, "referrer_id", None) and not db_user.is_banned:
            if bot:
                try:
                    await _notify_referral(
                        bot,
                        tg_user.id,
                        "ℹ️ Реферальный бонус не начислен.\n"
                        "Вы уже зарегистрированы в боте.\n"
                        "💡 Если вы ещё не нажимали «Запустить» — удалите чат с ботом и перейдите по ссылке заново.",
                    )
                except Exception:
                    pass

        data["db_user"] = db_user
        return await handler(event, data)

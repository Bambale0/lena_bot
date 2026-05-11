# bot/middlewares/auth.py
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram import Bot
from aiogram.types import TelegramObject, Update, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

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

        if db_user is None:
            # Обработка реферального кода из /start payload
            referrer = None
            referrer_l2 = None
            referrer_l3 = None
            update: Update | None = data.get("event_update")
            if update and update.message and update.message.text:
                parts = update.message.text.split()
                if len(parts) == 2 and parts[0] == "/start":
                    ref_code = parts[1]
                    referrer = await repo.get_user_by_referral_code(session, ref_code)
                    if referrer:
                        # L2: referrer's referrer
                        if referrer.referrer_id:
                            referrer_l2 = await repo.get_user_by_id(session, referrer.referrer_id)
                        if referrer_l2 and referrer_l2.referrer_id:
                            referrer_l3 = await repo.get_user_by_id(session, referrer_l2.referrer_id)

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
                await repo.add_credits(session, referrer.id, settings.REFERRAL_L1_CREDITS)
                logger.info("Referral L1 bonus: %s -> %s", tg_user.id, referrer.tg_id)
                await _notify_referral(
                    bot,
                    referrer.tg_id,
                    "🎉 По твоей ссылке пришёл новый пользователь!\n"
                    f"+{settings.REFERRAL_L1_CREDITS} cr начислено.",
                )

        elif db_user.is_banned:
            return  # Просто игнорируем забаненных

        data["db_user"] = db_user
        return await handler(event, data)

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from db import repository as repo

if TYPE_CHECKING:
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SEGMENT_LABELS: dict[str, str] = {
    "all": "Все пользователи",
    "paid": "Платившие",
    "new": "Новые за 7 дней",
    "active": "Активные за 14 дней",
}


async def get_recipient_ids(session: AsyncSession, segment: str) -> list[int]:
    return await repo.get_broadcast_recipient_ids(session, segment)


async def _copy_broadcast_message(*, bot: Bot, source_chat_id: int, source_message_id: int, target_chat_id: int) -> None:
    await bot.copy_message(
        chat_id=target_chat_id,
        from_chat_id=source_chat_id,
        message_id=source_message_id,
    )


async def deliver_broadcast(
    *,
    bot: Bot,
    tg_ids: list[int],
    source_chat_id: int,
    source_message_id: int,
    status_msg: Message | None = None,
) -> tuple[int, int, list[str]]:
    sent = 0
    failed = 0
    errors: list[str] = []

    for index, tg_id in enumerate(tg_ids, start=1):
        try:
            await _copy_broadcast_message(
                bot=bot,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                target_chat_id=tg_id,
            )
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            try:
                await _copy_broadcast_message(
                    bot=bot,
                    source_chat_id=source_chat_id,
                    source_message_id=source_message_id,
                    target_chat_id=tg_id,
                )
                sent += 1
            except Exception as retry_exc:  # noqa: BLE001
                failed += 1
                logger.warning("Broadcast retry failed tg_id=%s: %s", tg_id, retry_exc)
                if len(errors) < 10:
                    errors.append(f"{tg_id}: retry failed ({type(retry_exc).__name__})")
        except TelegramForbiddenError:
            failed += 1
            if len(errors) < 10:
                errors.append(f"{tg_id}: bot blocked or chat unavailable")
        except TelegramBadRequest as exc:
            failed += 1
            if len(errors) < 10:
                errors.append(f"{tg_id}: bad request ({exc.message})")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("Broadcast delivery failed tg_id=%s: %s", tg_id, exc)
            if len(errors) < 10:
                errors.append(f"{tg_id}: {type(exc).__name__}")

        if status_msg and (index % 20 == 0 or index == len(tg_ids)):
            try:
                await status_msg.edit_text(
                    f"📢 Рассылка идёт... {index}/{len(tg_ids)}\n"
                    f"Доставлено: {sent} · Ошибок: {failed}"
                )
            except Exception:  # noqa: BLE001
                pass

        await asyncio.sleep(0.05)

    return sent, failed, errors

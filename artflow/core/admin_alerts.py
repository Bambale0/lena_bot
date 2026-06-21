from __future__ import annotations

import asyncio
import html
import logging
import time
from typing import Iterable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import settings

logger = logging.getLogger(__name__)

_ALERT_LOCK = asyncio.Lock()
_ALERT_STATE: dict[str, float] = {}
_DEFAULT_COOLDOWN_SECONDS = 3600


async def send_admin_alert_once(
    *,
    alert_key: str,
    title: str,
    message: str,
    cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
    admin_ids: Iterable[int] | None = None,
) -> bool:
    admin_list = [int(x) for x in (admin_ids or settings.ADMIN_IDS or []) if str(x).strip()]
    if not admin_list:
        return False

    now = time.monotonic()
    async with _ALERT_LOCK:
        last_sent = _ALERT_STATE.get(alert_key)
        if last_sent is not None and (now - last_sent) < cooldown_seconds:
            return False

    text = f"⚠️ <b>{html.escape(title)}</b>\n\n{html.escape(message)}"
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        delivered = False
        for admin_id in admin_list:
            try:
                await bot.send_message(admin_id, text)
                delivered = True
            except Exception as exc:
                logger.warning("Failed to send admin alert to %s: %s", admin_id, exc)
        if delivered:
            async with _ALERT_LOCK:
                _ALERT_STATE[alert_key] = time.monotonic()
        return delivered
    finally:
        await bot.session.close()

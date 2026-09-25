from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)


def is_benign_telegram_error(error: TelegramBadRequest) -> bool:
    text = str(error).lower()
    benign_parts = (
        "message is not modified",
        "there is no text in the message to edit",
        "query is too old",
        "query id is invalid",
    )
    return any(part in text for part in benign_parts)


def split_text_chunks(text: str, *, max_chars: int = 3000) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return [""]
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: list[str] = []
    start = 0
    total = len(clean)
    while start < total:
        remaining = total - start
        if remaining <= max_chars:
            chunks.append(clean[start:])
            break

        window = clean[start : start + max_chars]
        candidates = (
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind(" "),
        )
        cut = max(candidates)
        if cut < max_chars // 2:
            cut = max_chars
        else:
            cut += 1
        chunks.append(clean[start : start + cut])
        start += cut

    return chunks


async def safe_edit_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        if "there is no text in the message to edit" not in str(e).lower():
            raise

    try:
        await message.edit_caption(caption=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        raise


async def safe_answer_callback(call: CallbackQuery, *args, **kwargs) -> None:
    try:
        await call.answer(*args, **kwargs)
    except TelegramBadRequest as e:
        if is_benign_telegram_error(e):
            logger.debug("Ignoring benign callback error: %s", e)
            return
        raise

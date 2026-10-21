"""Bounded multipart delivery of server-owned public media to Telegram."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram.types import FSInputFile, Message

from api import public_files

logger = logging.getLogger(__name__)
TELEGRAM_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def local_media_path(url: str, *, max_bytes: int = TELEGRAM_UPLOAD_MAX_BYTES) -> Path | None:
    path = public_files.local_upload_path_from_url(url)
    if path is None:
        return None
    try:
        path = path.resolve(strict=True)
        path.relative_to(public_files.UPLOAD_ROOT.resolve())
        if path.is_file() and 0 < path.stat().st_size <= max_bytes:
            return path
    except (OSError, ValueError):
        pass
    return None


async def send_video_to_message(
    message: Message,
    *,
    result_url: str,
    generation_id: int,
    caption: str,
    reply_markup=None,
) -> bool:
    path = local_media_path(result_url)
    # A missing/oversized local file must not cause another doomed public fetch.
    if path is None and public_files.local_upload_path_from_url(result_url) is not None:
        logger.info("Telegram media unavailable gen=%s mode=local", generation_id)
        return False
    media = FSInputFile(path) if path else result_url
    try:
        await message.answer_video(
            media, caption=caption, reply_markup=reply_markup, request_timeout=90
        )
        logger.info(
            "Telegram media delivered gen=%s mode=%s",
            generation_id,
            "multipart-video" if path else "url-video",
        )
        return True
    except Exception as exc:
        logger.info(
            "Telegram video retry gen=%s mode=%s error_type=%s",
            generation_id,
            "multipart" if path else "url",
            type(exc).__name__,
        )
    if path:
        try:
            await message.answer_document(
                FSInputFile(path), caption=caption, reply_markup=reply_markup, request_timeout=90
            )
            logger.info("Telegram media delivered gen=%s mode=multipart-document", generation_id)
            return True
        except Exception as exc:
            logger.warning(
                "Telegram media delivery failed gen=%s error_type=%s",
                generation_id,
                type(exc).__name__,
            )
    return False

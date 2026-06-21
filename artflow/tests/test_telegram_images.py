from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from PIL import Image

from bot.utils import telegram_images


def _png_bytes(size: tuple[int, int] = (32, 32), color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_send_image_to_message_falls_back_to_document_on_image_process_failed(monkeypatch) -> None:
    message = MagicMock()
    message.answer_photo = AsyncMock(side_effect=TelegramBadRequest(method="sendPhoto", message="Bad Request: IMAGE_PROCESS_FAILED"))
    message.answer_document = AsyncMock()

    monkeypatch.setattr(telegram_images, "download_image_bytes", AsyncMock(return_value=_png_bytes()))

    result = await telegram_images.send_image_to_message(
        message=message,
        result_url="https://example.test/result.png",
        generation_id=42,
        caption="Готово",
    )

    assert result.delivered is True
    assert result.mode == "document"
    message.answer_document.assert_awaited_once()
    assert "Оригинал без сжатия" in message.answer_document.await_args.kwargs["caption"]


@pytest.mark.asyncio
async def test_send_image_group_to_message_uses_media_group(monkeypatch) -> None:
    message = MagicMock()
    message.answer_media_group = AsyncMock()

    payloads = [_png_bytes(color=(255, 0, 0)), _png_bytes(color=(0, 255, 0))]
    monkeypatch.setattr(telegram_images, "download_image_bytes", AsyncMock(side_effect=payloads))

    result = await telegram_images.send_image_group_to_message(
        message=message,
        result_urls=["https://example.test/1.png", "https://example.test/2.png"],
        generation_prefix="88",
        caption="Серия",
    )

    assert result.delivered is True
    assert result.mode == "media_group"
    message.answer_media_group.assert_awaited_once()
    media = message.answer_media_group.await_args.args[0]
    assert len(media) == 2
    assert media[0].caption == "Серия"
    assert media[1].caption is None


@pytest.mark.asyncio
async def test_send_image_group_to_message_returns_not_delivered_when_download_fails(monkeypatch) -> None:
    message = MagicMock()
    message.answer_media_group = AsyncMock()

    monkeypatch.setattr(telegram_images, "download_image_bytes", AsyncMock(side_effect=[_png_bytes(), None]))

    result = await telegram_images.send_image_group_to_message(
        message=message,
        result_urls=["https://example.test/1.png", "https://example.test/2.png"],
        generation_prefix="99",
        caption="Серия",
    )

    assert result.delivered is False
    assert result.mode is None
    message.answer_media_group.assert_not_called()

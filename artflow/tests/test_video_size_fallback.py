from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo

from bot.handlers.video_gen import _send_video_with_fallback


@pytest.mark.asyncio
async def test_telegram_large_video_uses_link_without_reupload():
    url = "https://example.test/generated-video.mp4"
    error = TelegramBadRequest(
        method=SendVideo(chat_id=123, video=url),
        message="Bad Request: file is too big",
    )
    bot = SimpleNamespace(
        send_video=AsyncMock(side_effect=error),
        send_message=AsyncMock(),
    )
    await _send_video_with_fallback(
        bot, chat_id=123, video_url=url,
        caption="A" * 5000, reply_markup=None,
    )
    bot.send_video.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 123
    assert url in kwargs["text"]
    assert len(kwargs["text"]) < 4096


@pytest.mark.asyncio
async def test_telegram_url_fetch_failure_uses_short_link_message(monkeypatch):
    url = "https://example.test/generated-video.mp4"
    error = TelegramBadRequest(
        method=SendVideo(chat_id=123, video=url),
        message="Bad Request: failed to get HTTP URL content",
    )
    bot = SimpleNamespace(send_video=AsyncMock(side_effect=error), send_message=AsyncMock())

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def get(self, *_args, **_kwargs):
            raise ConnectionError("test provider unavailable")

    monkeypatch.setattr("bot.handlers.video_gen.aiohttp.ClientSession", FailingSession)
    await _send_video_with_fallback(bot, chat_id=123, video_url=url, caption="x" * 12000, reply_markup=None)
    assert bot.send_video.await_count == 1
    bot.send_message.assert_awaited_once()
    assert url in bot.send_message.await_args.kwargs["text"]
    assert len(bot.send_message.await_args.kwargs["text"]) < 4096

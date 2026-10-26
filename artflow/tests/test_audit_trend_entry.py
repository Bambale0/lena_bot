from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import marketplace, trends
from db.models import PromptStatus


@pytest.mark.asyncio
@pytest.mark.parametrize("tags", [["trend"], ["trend", "trend-video"]])
async def test_every_bot_trend_opens_shared_runner_before_any_generation(monkeypatch, tags):
    prompt = SimpleNamespace(id=123, tags=tags, is_public=True, status=PromptStatus.approved,
                             trend_user_fields=[], prompt_text="hidden-secret-prompt")
    monkeypatch.setattr(trends, "get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr(
        trends,
        "public_prompt_library_item_is_visible",
        AsyncMock(return_value=True),
    )
    launch = AsyncMock()
    monkeypatch.setattr(marketplace, "_launch_prompt_generation", launch)
    call = SimpleNamespace(data="trends:use:123", message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    await trends.use_trend(call, object(), AsyncMock(), SimpleNamespace(id=1), AsyncMock())
    launch.assert_not_awaited()
    reply = call.message.answer.await_args
    assert reply is not None
    assert "hidden-secret-prompt" not in str(reply)
    buttons = [b for row in reply.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons[0].web_app.url == f"{trends.settings.WEB_PUBLIC_URL.rstrip('/')}/app?trend=123"
    assert call.answer.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("public,status", [(False, PromptStatus.approved), (True, PromptStatus.pending)])
async def test_unpublished_trend_does_not_open_runner(monkeypatch, public, status):
    prompt = SimpleNamespace(id=123, tags=["trend"], is_public=public, status=status)
    monkeypatch.setattr(trends, "get_prompt_by_id", AsyncMock(return_value=prompt))
    call = SimpleNamespace(data="trends:use:123", message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    await trends.use_trend(call, object(), AsyncMock(), SimpleNamespace(id=1), AsyncMock())
    call.message.answer.assert_not_awaited()
    assert call.answer.await_args.kwargs["show_alert"] is True

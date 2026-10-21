from __future__ import annotations

import html
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import image_gen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    ["Короткий <промпт> & текст", "портрет & свет\n" * 700, "🎨" * 5000],
    ids=["short-html", "long-html", "astral-unicode"],
)
async def test_show_owned_prompt_preserves_complete_text_in_telegram_sized_messages(
    monkeypatch, prompt
):
    gen = SimpleNamespace(
        id=31, user_id=7, prompt=prompt.strip(), input_params=None, source_feed_gen_id=None
    )
    monkeypatch.setattr(image_gen.repo, "get_generation_by_id", AsyncMock(return_value=gen))

    async def accept_message(text, **kwargs):
        plain = html.unescape(re.sub(r"<[^>]+>", "", text))
        assert len(plain.encode("utf-16-le")) // 2 <= 4096

    message = SimpleNamespace(answer=AsyncMock(side_effect=accept_message))
    call = SimpleNamespace(data="gen:prompt:31", message=message, answer=AsyncMock())
    await image_gen.cb_gen_prompt(call, SimpleNamespace(), SimpleNamespace(id=7))
    parts = message.answer.await_args_list
    contents = [
        html.unescape(re.search(r"<code>(.*?)</code>", p.args[0], re.S).group(1)) for p in parts
    ]
    assert "".join(contents) == gen.prompt
    assert parts[-1].kwargs.get("reply_markup") is not None
    assert all(p.kwargs.get("reply_markup") is None for p in parts[:-1])


@pytest.mark.asyncio
@pytest.mark.parametrize("owner,params", [(8, None), (7, '{"hidden_prompt":true}')])
async def test_show_prompt_never_sends_foreign_or_hidden_recipe(monkeypatch, owner, params):
    gen = SimpleNamespace(
        id=31, user_id=owner, prompt="private recipe", input_params=params, source_feed_gen_id=None
    )
    monkeypatch.setattr(image_gen.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    call = SimpleNamespace(
        data="gen:prompt:31", message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock()
    )
    await image_gen.cb_gen_prompt(call, SimpleNamespace(), SimpleNamespace(id=7))
    call.message.answer.assert_not_awaited()

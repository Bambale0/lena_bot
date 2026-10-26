from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from bot.handlers import trends


def _category(index: int):
    return SimpleNamespace(key=f"cat_{index:02d}", title=f"Категория {index:02d}")


def _prompt(index: int):
    return SimpleNamespace(id=index, title=f"Тренд {index}")


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_category_keyboard_is_paged_and_callback_data_stays_within_telegram_limit():
    markup = trends._category_kb(
        [_category(index) for index in range(10)], page=0, is_admin=False
    )

    callbacks = _callbacks(markup)
    assert "trends:folder:cat_00:0" in callbacks
    assert "trends:folder:cat_07:0" in callbacks
    assert "trends:folder:cat_08:0" not in callbacks
    assert "trends:categories:1" in callbacks
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)
    assert not any(value.startswith("trends:add:") for value in callbacks)


def test_folder_keyboard_restores_category_page_and_keeps_admin_actions_private():
    public = trends._folder_kb(
        _prompt(7), index=0, total=2, category_key="cat_01", category_page=1, is_admin=False
    )
    admin = trends._folder_kb(
        _prompt(7), index=0, total=2, category_key="cat_01", category_page=1, is_admin=True
    )

    assert "trends:folder-nav:cat_01:1:1" in _callbacks(public)
    assert "trends:categories:1" in _callbacks(public)
    assert not any(value.startswith("trends:archive:") for value in _callbacks(public))
    assert "trends:archive:7" in _callbacks(admin)
    assert all(len(value.encode("utf-8")) <= 64 for value in _callbacks(admin))


@pytest.mark.asyncio
async def test_open_trends_shows_category_folders_first(monkeypatch):
    show = AsyncMock()
    monkeypatch.setattr(trends, "_show_categories", show)
    state = AsyncMock()
    message = SimpleNamespace()

    await trends.open_trends(message, SimpleNamespace(), state, None)

    state.clear.assert_awaited_once()
    show.assert_awaited_once_with(message, ANY, None, page=0)


@pytest.mark.asyncio
async def test_open_folder_and_back_keep_category_page(monkeypatch):
    show_folder = AsyncMock()
    show_categories = AsyncMock()
    answer = AsyncMock()
    monkeypatch.setattr(trends, "_show_folder", show_folder)
    monkeypatch.setattr(trends, "_show_categories", show_categories)
    monkeypatch.setattr(trends, "safe_answer_callback", answer)
    call = SimpleNamespace(
        data="trends:folder:cat_03:2", message=SimpleNamespace(), answer=AsyncMock()
    )

    await trends.open_trend_folder(call, SimpleNamespace(), None)
    show_folder.assert_awaited_once_with(
        call.message,
        ANY,
        None,
        category_key="cat_03",
        category_page=2,
        index=0,
    )

    call.data = "trends:categories:2"
    await trends.navigate_trend_categories(call, SimpleNamespace(), None)
    show_categories.assert_awaited_once_with(call.message, ANY, None, page=2)


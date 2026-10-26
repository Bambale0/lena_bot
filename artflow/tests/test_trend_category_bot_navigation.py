from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from bot.handlers import trends


def _category(index: int):
    return SimpleNamespace(key=f"cat_{index:02d}", title=f"Категория {index:02d}")


def _prompt(index: int):
    return SimpleNamespace(id=index, title=f"Тренд {index}", preview_url=None)


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
        _prompt(7), index=0, total=2, category_key="cat_01", category_page=1,
        folder_page=0, has_more=True, is_admin=False
    )
    admin = trends._folder_kb(
        _prompt(7), index=0, total=2, category_key="cat_01", category_page=1,
        folder_page=0, has_more=True, is_admin=True
    )

    assert "trends:fn:cat_01:1:0:1" in _callbacks(public)
    assert "trends:categories:1" in _callbacks(public)
    assert not any(value.startswith("trends:archive:") for value in _callbacks(public))
    assert "trends:archive:7:cat_01:1" in _callbacks(admin)
    assert all(len(value.encode("utf-8")) <= 64 for value in _callbacks(admin))


@pytest.mark.asyncio
async def test_open_trends_shows_category_folders_first(monkeypatch):
    show = AsyncMock()
    monkeypatch.setattr(trends, "_show_categories", show)
    state = AsyncMock()
    message = SimpleNamespace()

    await trends.open_trends(message, SimpleNamespace(), state, None)

    state.clear.assert_awaited_once()
    show.assert_awaited_once_with(message, ANY, None, page=0, edit=False)


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
        folder_page=0,
        index=0,
    )

    show_folder.reset_mock()
    call.data = "trends:fn:cat_03:2:4:17"
    await trends.navigate_trend_folder(call, SimpleNamespace(), None)
    show_folder.assert_awaited_once_with(
        call.message,
        ANY,
        None,
        category_key="cat_03",
        category_page=2,
        folder_page=4,
        index=17,
    )

    call.data = "trends:categories:2"
    await trends.navigate_trend_categories(call, SimpleNamespace(), None)
    show_categories.assert_awaited_once_with(call.message, ANY, None, page=2)


@pytest.mark.asyncio
async def test_direct_command_answers_with_a_new_bot_message(monkeypatch):
    page = SimpleNamespace(
        items=[SimpleNamespace(category=_category(1))],
        has_more=False,
        next_cursor=None,
    )
    monkeypatch.setattr(trends, "get_public_category_shelves", AsyncMock(return_value=page))
    edit = AsyncMock()
    monkeypatch.setattr(trends, "safe_edit_message", edit)
    holder = SimpleNamespace(answer=AsyncMock())

    await trends._show_categories(holder, SimpleNamespace(), None, page=0, edit=False)

    holder.answer.assert_awaited_once()
    assert "Тренды по категориям" in holder.answer.await_args.args[0]
    edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_folder_navigation_loads_only_the_requested_server_page(monkeypatch):
    category = _category(1)
    requested = SimpleNamespace(
        category=category,
        items=[_prompt(49)],
        has_more=False,
        next_cursor=None,
    )
    load = AsyncMock(return_value=requested)
    monkeypatch.setattr(trends, "get_public_category_trends", load)
    monkeypatch.setattr(trends, "_caption", lambda prompt, **_kwargs: prompt.title)
    monkeypatch.setattr(trends, "_folder_kb", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trends, "_media_source", lambda _url: None)
    edit = AsyncMock()
    monkeypatch.setattr(trends, "safe_edit_message", edit)
    holder = SimpleNamespace()

    await trends._show_folder(
        holder,
        SimpleNamespace(),
        None,
        category_key="cat_01",
        category_page=0,
        folder_page=1,
        index=0,
    )

    load.assert_awaited_once_with(
        ANY,
        key="cat_01",
        limit=trends.FOLDER_TREND_LIMIT,
        cursor=None,
        offset=trends.FOLDER_TREND_LIMIT,
    )
    assert "Тренд 49" in edit.await_args.args[1]


@pytest.mark.asyncio
async def test_folder_replaces_existing_photo_with_video(monkeypatch):
    category = _category(1)
    prompt = SimpleNamespace(id=1, title="Видео", preview_url="https://cdn.test/video.mp4")
    page = SimpleNamespace(category=category, items=[prompt], has_more=False, next_cursor=None)
    monkeypatch.setattr(trends, "get_public_category_trends", AsyncMock(return_value=page))
    monkeypatch.setattr(trends, "_caption", lambda *_args, **_kwargs: "Видео")
    monkeypatch.setattr(trends, "_folder_kb", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trends, "_media_source", lambda _url: "https://cdn.test/video.mp4")
    monkeypatch.setattr(trends, "trend_kind", lambda _prompt: "video")
    holder = SimpleNamespace(photo=[object()], video=None, edit_media=AsyncMock(), answer_video=AsyncMock())

    await trends._show_folder(
        holder,
        SimpleNamespace(),
        None,
        category_key="cat_01",
        category_page=0,
        folder_page=0,
        index=0,
    )

    holder.edit_media.assert_awaited_once()
    holder.answer_video.assert_not_awaited()

"""Тесты хендлеров feed."""
from __future__ import annotations

import random
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from PIL import Image

from bot.handlers import feed
from bot.states import PromptUseFSM
from db.models import GenerationType, ModelCost
from tests.factories import make_callback, make_message


# ── show_feed_empty ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_show_feed_empty() -> None:
    holder = MagicMock(spec=Message)
    holder.edit_text = AsyncMock()
    with patch("bot.handlers.feed.repo", AsyncMock(get_feed_generations=AsyncMock(return_value=[]))):
        await feed.show_feed_from_source(holder=holder, session=AsyncMock(), source="feed", index=0)
    holder.edit_text.assert_awaited_once()
    assert "Пока нет" in holder.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_show_top_day_empty() -> None:
    holder = MagicMock(spec=Message)
    holder.edit_text = AsyncMock()
    with patch("bot.handlers.feed.repo", AsyncMock(get_top_day_generations=AsyncMock(return_value=[]))):
        await feed.show_feed_from_source(holder=holder, session=AsyncMock(), source="top", index=0)
    holder.edit_text.assert_awaited_once()
    assert "Топ дня" in holder.edit_text.call_args[0][0]


# ── show_feed with card ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_show_feed_with_card() -> None:
    holder = MagicMock(spec=Message)
    holder.edit_text = AsyncMock()
    holder.photo = "existing_photo"
    gen = SimpleNamespace(id=42, model="sdxl", result_url="https://example.com/img.png", likes_count=5, shares_count=2, prompt="a cat")
    card = SimpleNamespace(generation=gen, username="testuser", full_name="Test", aspect_ratio="16:9", quality="base", count=1, reference_url=None, remix_count=0, score=1.0)
    with patch("bot.handlers.feed.repo", AsyncMock(get_feed_generations=AsyncMock(return_value=[card]))):
        with patch("bot.handlers.feed._show_feed_card", new_callable=AsyncMock):
            await feed.show_feed_from_source(holder=holder, session=AsyncMock(), source="feed", index=0)


# ── open_feed ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_feed_opens_feed() -> None:
    msg = make_message(text="/feed")
    mock_state = AsyncMock()
    with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
        await feed.open_feed(msg, AsyncMock(), mock_state)
    mock_state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_cb_feed_menu_opens_feed() -> None:
    call = make_callback(data="menu:feed")
    mock_state = AsyncMock()
    with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
        await feed.open_feed(call, AsyncMock(), mock_state)
    mock_state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_open_top_day() -> None:
    call = make_callback(data="feed:top")
    mock_state = AsyncMock()
    with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
        await feed.open_top_day(call, AsyncMock(), mock_state)
    mock_state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_cb_top_day_button() -> None:
    call = make_callback(data="menu:top_day")
    mock_state = AsyncMock()
    with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
        await feed.open_top_day(call, AsyncMock(), mock_state)
    mock_state.clear.assert_called_once()


# ── feed navigation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_feed_next() -> None:
    call = make_callback(data="feed:next:feed:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
        await feed.cb_feed_next(call, AsyncMock())
    call.answer.assert_awaited_once()


# ── feed:like ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_feed_like() -> None:
    call = make_callback(data="feed:like:42:feed:0")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.feed.repo.like_feed_generation", AsyncMock(return_value=None)):
        with patch("bot.handlers.feed.show_feed_from_source", new_callable=AsyncMock):
            await feed.cb_feed_like(call, AsyncMock())
    call.answer.assert_awaited_once_with("Лайк сохранён ❤️")


# ── feed:share ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_feed_share() -> None:
    call = make_callback(data="feed:share:42")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(return_value=SimpleNamespace(username="testbot"))
    mock_db_user = SimpleNamespace(id=42, username="testuser", referral_code="abc123")
    gen = SimpleNamespace(id=42, result_url="https://img.test/1.png")
    with patch("bot.handlers.feed.repo", AsyncMock(increment_feed_share=AsyncMock(return_value=gen))):
        await feed.cb_feed_share(call, AsyncMock(), mock_db_user, mock_bot)
    call.answer.assert_awaited_once_with("Ссылка готова")


@pytest.mark.asyncio
async def test_cb_feed_share_not_found() -> None:
    call = make_callback(data="feed:share:999")
    call.answer = AsyncMock()
    with patch("bot.handlers.feed.repo", AsyncMock(increment_feed_share=AsyncMock(return_value=None))):
        await feed.cb_feed_share(call, AsyncMock(), SimpleNamespace(id=42, referral_code="abc"), AsyncMock())
    call.answer.assert_awaited_once()
    assert "не найден" in call.answer.call_args[0][0].lower()


# ── feed:use ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_feed_use() -> None:
    """feed:use → вызывает prompt_use_model_kb с правильной моделью."""
    call = make_callback(data="feed:use:42")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    gen = SimpleNamespace(id=42, prompt="beautiful landscape", model="sdxl")
    # Используем настоящий ModelCost
    model_cost = ModelCost(
        model_key="sdxl", display_name="SDXL", credits=8,
        gen_type=GenerationType.image, is_active=True,
    )
    with patch("bot.handlers.feed.repo", AsyncMock(get_generation_by_id=AsyncMock(return_value=gen), get_all_model_costs=AsyncMock(return_value=[model_cost]))):
        with patch("bot.handlers.feed.prompt_use_model_kb", new_callable=AsyncMock, return_value=AsyncMock()):
            await feed.cb_feed_use(call, AsyncMock(), SimpleNamespace(id=42, credits=500, is_banned=False), mock_state)
    mock_state.set_state.assert_called_with(PromptUseFSM.model_select)


@pytest.mark.asyncio
async def test_cb_feed_use_no_prompt() -> None:
    call = make_callback(data="feed:use:42")
    call.answer = AsyncMock()
    gen = SimpleNamespace(id=42, prompt=None, model="sdxl")
    with patch("bot.handlers.feed.repo", AsyncMock(get_generation_by_id=AsyncMock(return_value=gen))):
        await feed.cb_feed_use(call, AsyncMock(), SimpleNamespace(id=42, credits=500, is_banned=False), AsyncMock())
    call.answer.assert_awaited_once()
    assert "не найдена" in call.answer.call_args[0][0].lower()


# ── feed:publish ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_feed_publish() -> None:
    call = make_callback(data="feed:publish:42")
    call.answer = AsyncMock()
    gen = SimpleNamespace(id=42, user_id=42, source_feed_gen_id=None, is_public_feed=False, is_prompt_library=False)
    with patch("bot.handlers.feed.repo", AsyncMock(get_generation_by_id=AsyncMock(return_value=gen), commit=AsyncMock())):
        await feed.cb_publish_generation(call, AsyncMock(), SimpleNamespace(id=42))
    assert gen.is_public_feed is True
    assert gen.is_prompt_library is True
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_feed_publish_not_found() -> None:
    call = make_callback(data="feed:publish:999")
    call.answer = AsyncMock()
    with patch("bot.handlers.feed.repo", AsyncMock(get_generation_by_id=AsyncMock(return_value=None))):
        await feed.cb_publish_generation(call, AsyncMock(), SimpleNamespace(id=42))
    call.answer.assert_awaited_once()
    assert "не найдена" in call.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cb_feed_publish_rejects_feed_derivative() -> None:
    call = make_callback(data="feed:publish:42")
    call.answer = AsyncMock()
    gen = SimpleNamespace(id=42, user_id=42, source_feed_gen_id=7, is_public_feed=False, is_prompt_library=False)
    with patch("bot.handlers.feed.repo", AsyncMock(get_generation_by_id=AsyncMock(return_value=gen), commit=AsyncMock())):
        await feed.cb_publish_generation(call, AsyncMock(), SimpleNamespace(id=42))
    assert gen.is_public_feed is False
    assert gen.is_prompt_library is False
    call.answer.assert_awaited_once()


# ── Utility functions ─────────────────────────────────────────────────────────

def test_model_label() -> None:
    assert "Sdxl" in feed._model_label("sdxl_v1-base")


def test_default_quality() -> None:
    assert feed._default_quality_for_model("some_model") == "basic"


def test_default_count() -> None:
    assert feed._default_count_for_model("some_model") == 1


def test_author_label_with_username() -> None:
    card = SimpleNamespace(generation=SimpleNamespace(), username="testuser", full_name=None)
    assert feed._author_label(card) == "@testuser"


def test_author_label_with_name() -> None:
    card = SimpleNamespace(generation=SimpleNamespace(), username=None, full_name="<b>Test</b>")
    assert "&lt;b&gt;" in feed._author_label(card)


def test_prepare_feed_photo_upload_keeps_small_file() -> None:
    data = b"small-image"

    upload = feed._prepare_feed_photo_upload(
        data=data,
        result_url="https://example.test/result.png",
        generation_id=42,
    )

    assert upload.data == data
    assert upload.filename == "gen_42.png"


def test_prepare_feed_photo_upload_compresses_large_png(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = random.Random(42)
    rgb = bytes(rng.randrange(256) for _ in range(512 * 512 * 3))
    image = Image.frombytes("RGB", (512, 512), rgb)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()
    monkeypatch.setattr(feed, "TELEGRAM_PHOTO_TARGET_BYTES", 80 * 1024)

    upload = feed._prepare_feed_photo_upload(
        data=data,
        result_url="https://example.test/result.png",
        generation_id=43,
    )

    assert upload.filename == "gen_43.jpg"
    assert len(upload.data) <= feed.TELEGRAM_PHOTO_TARGET_BYTES
    assert len(upload.data) < len(data)


def test_feed_caption() -> None:
    gen = SimpleNamespace(model="sdxl", likes_count=10, shares_count=5)
    card = SimpleNamespace(generation=gen, username="user", aspect_ratio="16:9")
    result = feed._feed_caption(card)
    assert "@user" in result
    assert "10" in result

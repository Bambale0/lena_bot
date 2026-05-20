from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import image_gen


@pytest.mark.asyncio
async def test_ensure_active_image_session_passes_multi_ref_ids() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "model_key": "nano-banana-pro",
        "mode": "image",
        "aspect_ratio": "1:1",
        "quality": "2K",
        "count": 1,
        "image_file_id": "ref_1",
        "ref_file_ids": ["ref_1", "ref_2"],
    })
    db_user = SimpleNamespace(id=42)

    create_image_session = AsyncMock(return_value=SimpleNamespace(id=7))
    repo_stub = SimpleNamespace(
        get_active_image_session=AsyncMock(return_value=None),
        create_image_session=create_image_session,
    )
    with patch("bot.handlers.image_gen.repo", new=repo_stub):
        await image_gen._ensure_active_image_session_from_state(
            session=AsyncMock(),
            state=state,
            db_user=db_user,
        )

    assert create_image_session.await_args.kwargs["reference_file_ids"] == ["ref_1", "ref_2"]


@pytest.mark.asyncio
async def test_session_reference_url_uses_stored_reference_file_ids() -> None:
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        reference_file_ids='["ref_1", "ref_2"]',
        reference_file_id="ref_1",
        reference_url=None,
        last_result_url=None,
    )

    with patch("bot.handlers.image_gen._telegram_file_url", AsyncMock(side_effect=[
        "https://example.test/ref_1.jpg",
        "https://example.test/ref_2.jpg",
    ])):
        result = await image_gen._session_reference_url(
            AsyncMock(),
            image_session,
            prefer_last_result=False,
            state=None,
        )

    assert result == [
        "https://example.test/ref_1.jpg",
        "https://example.test/ref_2.jpg",
    ]


@pytest.mark.asyncio
async def test_session_reference_url_ignores_state_refs_from_other_session() -> None:
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        reference_file_ids='["stored_ref"]',
        reference_file_id="stored_ref",
        reference_url=None,
        last_result_url=None,
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "image_session_id": 99,
        "ref_file_ids": ["stale_ref"],
    })

    with patch("bot.handlers.image_gen._telegram_file_url", AsyncMock(return_value="https://example.test/stored.jpg")) as file_url:
        result = await image_gen._session_reference_url(
            AsyncMock(),
            image_session,
            prefer_last_result=False,
            state=state,
        )

    assert result == "https://example.test/stored.jpg"
    file_url.assert_awaited_once()
    assert file_url.await_args.args[1] == "stored_ref"


@pytest.mark.asyncio
async def test_session_reference_url_prefers_last_result_for_remix() -> None:
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        reference_file_ids='["ref_1"]',
        reference_file_id="ref_1",
        reference_url="https://example.test/original.jpg",
        last_result_url="https://example.test/remix-base.jpg",
    )

    result = await image_gen._session_reference_url(
        AsyncMock(),
        image_session,
        prefer_last_result=True,
        state=None,
    )

    assert result == "https://example.test/remix-base.jpg"


@pytest.mark.asyncio
async def test_session_reference_url_falls_back_to_saved_reference_when_no_last_result() -> None:
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        reference_file_ids='["ref_1"]',
        reference_file_id="ref_1",
        reference_url=None,
        last_result_url=None,
    )

    with patch("bot.handlers.image_gen._telegram_file_url", AsyncMock(return_value="https://example.test/ref_1.jpg")):
        result = await image_gen._session_reference_url(
            AsyncMock(),
            image_session,
            prefer_last_result=True,
            state=None,
        )

    assert result == "https://example.test/ref_1.jpg"

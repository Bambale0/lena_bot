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
async def test_ensure_active_image_session_persists_carried_reference_url() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "model_key": "wan/2-7-image",
        "mode": "image",
        "image_mode": "image",
        "aspect_ratio": None,
        "quality": "2K",
        "count": 1,
        "remix_reference_url": "https://example.test/remix-base.jpg",
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

    assert create_image_session.await_args.kwargs["mode"] == "image"
    assert create_image_session.await_args.kwargs["reference_url"] == "https://example.test/remix-base.jpg"


@pytest.mark.asyncio
async def test_dynamic_continue_keeps_carried_reference_without_upload_prompt() -> None:
    call = SimpleNamespace(data="img_dyn:continue:wan/2-7-image", message=SimpleNamespace())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "model_key": "wan/2-7-image",
        "mode": "image",
        "image_mode": "image",
        "remix_reference_url": "https://example.test/remix-base.jpg",
    })

    with (
        patch("bot.handlers.image_gen.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.image_gen.safe_answer_callback", AsyncMock()),
    ):
        await image_gen.cb_image_dynamic_continue(call, state)

    state.set_state.assert_awaited_once_with(image_gen.ImageGenFSM.prompt_input)
    assert "Референс уже сохранён" in edit_message.await_args.args[1]
    assert state.update_data.await_args.kwargs["mode"] == "image"


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


def test_requires_reference_image_only_for_image_only_models() -> None:
    assert image_gen._requires_reference_image("wan/2-7-image-pro") is False
    assert image_gen._requires_reference_image("nano-banana-pro") is False
    assert image_gen._requires_reference_image("qwen/image-edit") is True


def test_style_edit_prompt_scopes_hair_color_to_hair_only() -> None:
    prompt = image_gen._style_edit_prompt("hair_color", "пастельно розовый")

    assert "пастельно розовый" in prompt
    assert "Change ONLY the main person's hair color" in prompt
    assert "cars" in prompt
    assert "Do not recolor anything except the hair" in prompt


@pytest.mark.asyncio
async def test_handle_session_prompt_wraps_hair_color_style_edit() -> None:
    message = SimpleNamespace(text="пастельно розовый", answer=AsyncMock())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "remix_mode": True,
        "style_edit_kind": "hair_color",
        "remix_reference_url": "https://example.test/base.jpg",
        "remix_parent_generation_id": 99,
        "mode": "image",
        "image_mode": "image",
    })
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        mode="image",
        last_generation_id=99,
    )
    launch = AsyncMock(return_value=True)

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, 99))),
        patch("bot.handlers.image_gen._launch_session_generation", launch),
    ):
        await image_gen.handle_session_prompt(
            message,
            state,
            AsyncMock(),
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    sent_prompt = launch.await_args.kwargs["prompt"]
    assert "пастельно розовый" in sent_prompt
    assert "Do not recolor anything except the hair" in sent_prompt
    assert any(call.kwargs == {"style_edit_kind": None} for call in state.update_data.await_args_list)


@pytest.mark.asyncio
async def test_launch_session_generation_allows_dual_mode_model_without_reference() -> None:
    source_message = AsyncMock()
    status_msg = AsyncMock()
    source_message.answer = AsyncMock(return_value=status_msg)
    state = AsyncMock()
    session = AsyncMock()
    db_user = SimpleNamespace(id=42)
    image_session = SimpleNamespace(
        id=7,
        model="wan/2-7-image-pro",
        mode="text",
        aspect_ratio="1:1",
        quality="2K",
        count=1,
        reference_file_id=None,
        reference_file_ids=None,
    )
    generation = SimpleNamespace(id=99)
    repo_stub = SimpleNamespace(
        resolve_image_model_cost=AsyncMock(return_value=SimpleNamespace(credits=4)),
        count_user_active_generations=AsyncMock(return_value=0),
        spend_credits=AsyncMock(return_value=True),
        create_generation=AsyncMock(return_value=generation),
        update_image_session_last_prompt=AsyncMock(),
        update_generation_task=AsyncMock(),
    )
    generate_image = AsyncMock(return_value=SimpleNamespace(task_id="task_1"))

    with (
        patch("bot.handlers.image_gen.repo", new=repo_stub),
        patch("bot.handlers.image_gen.image_service.generate_image", generate_image),
    ):
        ok = await image_gen._launch_session_generation(
            source_message=source_message,
            state=state,
            session=session,
            db_user=db_user,
            image_session=image_session,
            prompt="portrait",
            action_type=image_gen.ImageGenerationAction.initial,
            reference_url=None,
            parent_generation_id=None,
            launching_text="launching",
            queued_text="queued",
        )

    assert ok is True
    generate_image.assert_awaited_once()
    assert generate_image.await_args.kwargs["image_url"] is None
    repo_stub.update_generation_task.assert_awaited_once_with(session, generation.id, "task_1")

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.image_errors import image_generation_user_error, telegram_image_error_text
from bot.handlers import image_gen
from db.models import GenerationType


def test_banana_safety_error_is_user_friendly() -> None:
    error = (
        "CometAPI Gemini image fallback returned no image URLs for nano-banana-pro: "
        "{'candidates': [{'finishReason': 'IMAGE_SAFETY'}]}"
    )

    assert "safety/moderation" in image_generation_user_error(error)
    assert "💋 возвращены" in telegram_image_error_text(error)


def test_banana_no_image_error_is_user_friendly() -> None:
    error = (
        "CometAPI Gemini image fallback returned no image URLs for nano-banana-2: "
        "{'candidates': [{'finishReason': 'NO_IMAGE'}]}"
    )

    assert "не смогла собрать изображение" in image_generation_user_error(error)


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
async def test_ensure_active_image_session_replaces_stale_active_session_and_resets_bad_count() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "model_key": "nano-banana-2",
        "mode": "text",
        "aspect_ratio": "16:9",
        "quality": "2K",
        "count": 3,
    })
    db_user = SimpleNamespace(id=42)
    existing = SimpleNamespace(id=11, model="seedream/4.5-text-to-image")

    create_image_session = AsyncMock(return_value=SimpleNamespace(id=12))
    repo_stub = SimpleNamespace(
        get_active_image_session=AsyncMock(return_value=existing),
        create_image_session=create_image_session,
    )
    with patch("bot.handlers.image_gen.repo", new=repo_stub):
        await image_gen._ensure_active_image_session_from_state(
            session=AsyncMock(),
            state=state,
            db_user=db_user,
        )

    assert create_image_session.await_args.kwargs["model"] == "nano-banana-2"
    assert create_image_session.await_args.kwargs["count"] == 1
    state.update_data.assert_awaited_with(image_session_id=12, count=1, image_count=1)


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
async def test_prompt_reference_photo_with_caption_launches_prompt_handler() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="ref_1", file_size=100)],
        caption="сделай студийный свет",
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "model_key": "seedream/5-pro-text-to-image",
        "ref_file_ids": [],
    })

    with patch("bot.handlers.image_gen.handle_prompt", AsyncMock()) as handle_prompt:
        await image_gen.handle_prompt_reference_upload(
            message,
            state,
            AsyncMock(),
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    state.update_data.assert_awaited_with(
        image_file_id="ref_1",
        ref_file_ids=["ref_1"],
        mode="image",
        image_mode="image",
    )
    handle_prompt.assert_awaited_once()


@pytest.mark.asyncio
async def test_prompt_input_shows_review_before_launching_generation() -> None:
    message = SimpleNamespace(text="нарисуй красный рюкзак", caption=None, answer=AsyncMock())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"mode": "text", "image_mode": "text"})
    image_session = SimpleNamespace(
        id=7,
        model="seedream/5-pro-text-to-image",
        mode="text",
        aspect_ratio="1:1",
        quality="basic",
        count=1,
    )

    with (
        patch("bot.handlers.image_gen._ensure_active_image_session_from_state", AsyncMock(return_value=image_session)),
        patch("bot.handlers.image_gen._session_reference_url", AsyncMock(return_value=None)),
        patch("bot.handlers.image_gen._promote_reference_mode_if_needed", AsyncMock(return_value="text")),
        patch(
            "bot.handlers.image_gen.repo.resolve_image_model_cost",
            AsyncMock(return_value=SimpleNamespace(credits=2)),
        ),
        patch("bot.handlers.image_gen._launch_session_generation", AsyncMock()) as launch,
    ):
        await image_gen.handle_prompt(
            message,
            state,
            AsyncMock(),
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    launch.assert_not_awaited()
    state.set_state.assert_awaited_with(image_gen.ImageGenFSM.review)
    assert "Проверь задачу" in message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "img_review:ratio" in callbacks
    assert "img_review:quality" in callbacks
    assert "img_review:launch" in callbacks


@pytest.mark.asyncio
async def test_first_generation_ratio_can_change_from_review() -> None:
    call = SimpleNamespace(
        data="img_review:ratio:set:9:16",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    image_session = SimpleNamespace(
        id=7,
        model="seedream/5-pro-text-to-image",
        mode="text",
        aspect_ratio="1:1",
        quality="basic",
        count=1,
    )
    session = AsyncMock()

    with (
        patch(
            "bot.handlers.image_gen._ensure_active_image_session_from_state",
            AsyncMock(return_value=image_session),
        ),
        patch("bot.handlers.image_gen._show_image_review", AsyncMock()) as show_review,
    ):
        await image_gen.cb_image_review_ratio_set(
            call,
            state,
            session,
            SimpleNamespace(id=42),
        )

    assert image_session.aspect_ratio == "9:16"
    session.commit.assert_awaited_once()
    show_review.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_selection_opens_task_first_composer_for_any_model() -> None:
    call = SimpleNamespace(
        data="img_model:gpt-image-2-text-to-image",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.get_data = AsyncMock(return_value={})

    with (
        patch(
            "bot.handlers.image_wizard_v2.repo.resolve_image_model_cost",
            AsyncMock(return_value=SimpleNamespace(credits=2)),
        ),
        patch("bot.handlers.image_wizard_v2.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.image_wizard_v2.safe_answer_callback", AsyncMock()),
    ):
        await image_gen.cb_image_model(
            call,
            state,
            AsyncMock(),
            SimpleNamespace(id=42, tg_id=42, credits=500),
        )

    state.set_state.assert_awaited_with(image_gen.ImageGenFSM.prompt_input)
    text = edit_message.await_args.args[1]
    callbacks = [
        button.callback_data
        for row in edit_message.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "GPT Image 2" in text
    assert "Можно сразу отправлять" in text
    assert "Выбери параметры" not in text
    assert "img_v2:ratio" in callbacks
    assert "img_v2:quality" in callbacks
    assert "img_v2:refs" in callbacks


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
async def test_handle_session_prompt_does_not_reuse_stale_feed_source_for_new_prompt() -> None:
    message = SimpleNamespace(text="my own prompt", answer=AsyncMock())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "source_feed_gen_id": 77,
        "mode": "text",
        "image_mode": "text",
        "remix_mode": False,
    })
    image_session = SimpleNamespace(
        id=7,
        model="wan/2-7-image-pro",
        mode="text",
        last_generation_id=99,
    )
    launch = AsyncMock(return_value=True)

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, None))),
        patch("bot.handlers.image_gen._launch_session_generation", launch),
    ):
        await image_gen.handle_session_prompt(
            message,
            state,
            AsyncMock(),
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    assert launch.await_args.kwargs["source_feed_gen_id"] is None


@pytest.mark.asyncio
async def test_handle_session_prompt_does_not_reuse_stale_feed_source_for_own_remix() -> None:
    message = SimpleNamespace(text="make it brighter", answer=AsyncMock())
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "source_feed_gen_id": 77,
        "mode": "image",
        "image_mode": "image",
        "remix_mode": True,
        "remix_parent_generation_id": 99,
        "remix_reference_url": "https://example.test/own.jpg",
    })
    image_session = SimpleNamespace(
        id=7,
        model="wan/2-7-image-pro",
        mode="image",
        last_generation_id=99,
    )
    parent_gen = SimpleNamespace(id=99, user_id=42, source_feed_gen_id=None)
    launch = AsyncMock(return_value=True)
    repo_stub = SimpleNamespace(get_generation_by_id=AsyncMock(return_value=parent_gen))

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, 99))),
        patch("bot.handlers.image_gen._launch_session_generation", launch),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
    ):
        await image_gen.handle_session_prompt(
            message,
            state,
            AsyncMock(),
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    assert launch.await_args.kwargs["source_feed_gen_id"] is None


@pytest.mark.asyncio
async def test_session_remix_keeps_user_reference_ids_for_later_variants() -> None:
    call = SimpleNamespace(
        data="img_session:remix:99",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_session_id": 7})
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        mode="image",
        reference_file_id="face_ref_1",
        reference_file_ids='["face_ref_1", "face_ref_2"]',
        reference_url=None,
        last_result_url="https://example.test/previous.jpg",
        last_generation_id=99,
    )
    parent_gen = SimpleNamespace(
        id=99,
        user_id=42,
        result_url="https://example.test/current-result.jpg",
        source_feed_gen_id=None,
    )
    session_obj = AsyncMock()
    repo_stub = SimpleNamespace(get_generation_by_id=AsyncMock(return_value=parent_gen))

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, 99))),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
        patch("bot.handlers.image_gen.safe_edit_message", AsyncMock()),
    ):
        await image_gen.cb_image_session_remix(
            call,
            session_obj,
            state,
            SimpleNamespace(id=42),
        )

    assert image_session.reference_file_id == "face_ref_1"
    assert image_session.reference_file_ids == '["face_ref_1", "face_ref_2"]'
    assert image_session.reference_url is None
    session_obj.commit.assert_not_awaited()
    state.update_data.assert_awaited()
    updates = state.update_data.await_args.kwargs
    assert updates["remix_reference_url"] == "https://example.test/current-result.jpg"
    assert updates["ref_file_ids"] == []


@pytest.mark.asyncio
async def test_style_edit_keeps_user_reference_ids_for_later_variants() -> None:
    call = SimpleNamespace(
        data="img_style:hair_color:99",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_session_id": 7})
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        mode="image",
        reference_file_id="face_ref_1",
        reference_file_ids='["face_ref_1", "face_ref_2"]',
        reference_url=None,
        last_result_url="https://example.test/previous.jpg",
        last_generation_id=99,
    )
    parent_gen = SimpleNamespace(
        id=99,
        user_id=42,
        result_url="https://example.test/current-result.jpg",
        source_feed_gen_id=None,
    )
    session_obj = AsyncMock()
    repo_stub = SimpleNamespace(get_generation_by_id=AsyncMock(return_value=parent_gen))

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, 99))),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
        patch("bot.handlers.image_gen.safe_edit_message", AsyncMock()),
    ):
        await image_gen.cb_image_style_choice(
            call,
            session_obj,
            state,
            SimpleNamespace(id=42),
        )

    assert image_session.reference_file_id == "face_ref_1"
    assert image_session.reference_file_ids == '["face_ref_1", "face_ref_2"]'
    assert image_session.reference_url is None
    session_obj.commit.assert_not_awaited()
    state.update_data.assert_awaited()
    updates = state.update_data.await_args.kwargs
    assert updates["remix_reference_url"] == "https://example.test/current-result.jpg"
    assert updates["style_edit_kind"] == "hair_color"
    assert updates["ref_file_ids"] == []


@pytest.mark.asyncio
async def test_repeat_variant_uses_saved_user_references_not_last_result() -> None:
    call = SimpleNamespace(
        data="img_session:repeat:101",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_session_id": 7})
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        mode="image",
        reference_file_id="face_ref_1",
        reference_file_ids='["face_ref_1", "face_ref_2"]',
        reference_url=None,
        last_result_url="https://example.test/generated-wrong-face.jpg",
        last_generation_id=101,
        count=1,
        aspect_ratio="9:16",
        quality="2K",
    )
    last_gen = SimpleNamespace(
        id=101,
        prompt="same prompt",
        source_feed_gen_id=None,
    )
    repo_stub = SimpleNamespace(get_last_session_generation=AsyncMock(return_value=last_gen))
    launch = AsyncMock(return_value=True)

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, 101))),
        patch("bot.handlers.image_gen.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.image_gen._launch_session_generation", launch),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
    ):
        await image_gen.cb_image_session_repeat(
            call,
            AsyncMock(),
            state,
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    launch.assert_not_awaited()
    text = edit_message.await_args.args[1]
    assert "Повтор генерации" in text
    assert "Референсы: <b>2/" in text
    assert "Формат: <b>9:16</b>" in text
    assert "same prompt" in text
    state.update_data.assert_awaited()
    assert state.update_data.await_args.kwargs["pending_action_type"] == image_gen.ImageGenerationAction.repeat.value


@pytest.mark.asyncio
async def test_repeat_launch_uses_saved_user_references_not_last_result() -> None:
    call = SimpleNamespace(
        data="img_repeat:launch",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "image_session_id": 7,
        "pending_image_prompt": "same prompt",
        "pending_parent_generation_id": 101,
    })
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        mode="image",
        reference_file_id="face_ref_1",
        reference_file_ids='["face_ref_1", "face_ref_2"]',
        reference_url=None,
        last_result_url="https://example.test/generated-wrong-face.jpg",
        last_generation_id=101,
        count=1,
        aspect_ratio="9:16",
        quality="2K",
    )
    launch = AsyncMock(return_value=True)

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, None))),
        patch("bot.handlers.image_gen._telegram_file_url", AsyncMock(side_effect=[
            "https://example.test/face-1.jpg",
            "https://example.test/face-2.jpg",
        ])),
        patch("bot.handlers.image_gen._launch_session_generation", launch),
        patch("bot.handlers.image_gen.safe_answer_callback", AsyncMock()),
    ):
        await image_gen.cb_image_repeat_launch(
            call,
            AsyncMock(),
            state,
            SimpleNamespace(id=42),
            AsyncMock(),
        )

    assert launch.await_args.kwargs["prompt"] == "same prompt"
    assert launch.await_args.kwargs["reference_url"] == [
        "https://example.test/face-1.jpg",
        "https://example.test/face-2.jpg",
    ]
    assert launch.await_args.kwargs["reference_url"] != "https://example.test/generated-wrong-face.jpg"


@pytest.mark.asyncio
async def test_repeat_model_change_keeps_repeat_flow_and_updates_session() -> None:
    call = SimpleNamespace(
        data="img_model:seedream/5-pro-text-to-image",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=image_gen.ImageGenFSM.model_select.state)
    state.get_data = AsyncMock(return_value={
        "repeat_model_select": True,
        "pending_image_prompt": "same prompt",
        "pending_action_type": image_gen.ImageGenerationAction.repeat.value,
        "image_session_id": 7,
    })
    image_session = SimpleNamespace(
        id=7,
        model="seedream/4.5-text-to-image",
        mode="text",
        aspect_ratio="1:1",
        quality="basic",
        count=1,
        reference_file_id=None,
        reference_file_ids=None,
        reference_url=None,
        last_result_url=None,
        last_prompt="old prompt",
    )
    fake_session = AsyncMock()

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, None))),
        patch("bot.handlers.image_gen._sync_state_with_image_session", AsyncMock()),
        patch("bot.handlers.image_gen.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.image_gen.safe_answer_callback", AsyncMock()) as answer_callback,
    ):
        await image_gen.cb_image_model(
            call,
            state,
            fake_session,
            SimpleNamespace(id=42),
        )

    assert image_session.model == "seedream/5-pro-text-to-image"
    fake_session.commit.assert_awaited_once()
    assert any(
        kwargs.get("repeat_model_select") is False and kwargs.get("pending_action_type") == image_gen.ImageGenerationAction.repeat.value
        for _, kwargs in state.update_data.await_args_list
    )
    assert "Повтор генерации" in edit_message.await_args.args[1]
    assert "Seedream 5" in edit_message.await_args.args[1]
    assert edit_message.await_args.kwargs["reply_markup"].inline_keyboard[1][0].callback_data == "img_repeat:model:7"
    answer_callback.assert_awaited()


def test_repeat_defaults_to_portrait_when_model_supports_it() -> None:
    image_session = SimpleNamespace(
        model="seedream/5-pro-text-to-image",
        mode="image",
        aspect_ratio="1:1",
        quality="basic",
    )

    changed = image_gen._apply_default_repeat_ratio(image_session, {})

    assert changed is True
    assert image_session.aspect_ratio == "9:16"


def test_repeat_keeps_explicitly_selected_ratio() -> None:
    image_session = SimpleNamespace(
        model="seedream/5-pro-text-to-image",
        mode="image",
        aspect_ratio="1:1",
        quality="basic",
    )

    changed = image_gen._apply_default_repeat_ratio(
        image_session,
        {
            "pending_action_type": image_gen.ImageGenerationAction.repeat.value,
            "repeat_aspect_ratio_explicit": True,
        },
    )

    assert changed is False
    assert image_session.aspect_ratio == "1:1"


@pytest.mark.asyncio
async def test_handle_session_photo_switches_active_session_to_image_mode() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_size=10, file_id="ref_1")],
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-2",
        mode="text",
        last_generation_id=99,
    )
    session_obj = AsyncMock()
    repo_stub = SimpleNamespace(update_image_session_references=AsyncMock())

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, None))),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
    ):
        await image_gen.handle_session_photo(
            message,
            state,
            session_obj,
            SimpleNamespace(id=42),
        )

    repo_stub.update_image_session_references.assert_awaited_once_with(
        session_obj,
        7,
        ["ref_1"],
        mode="image",
    )
    assert image_session.mode == "image"
    state.update_data.assert_awaited_once_with(
        image_file_id="ref_1",
        ref_file_ids=["ref_1"],
        image_session_id=7,
        mode="image",
        image_mode="image",
    )


@pytest.mark.asyncio
async def test_handle_session_photo_uses_last_generation_source_not_stale_state() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_size=10, file_id="ref_1")],
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"source_feed_gen_id": 77})
    image_session = SimpleNamespace(
        id=7,
        model="wan/2-7-image-pro",
        mode="image",
        reference_file_id=None,
        reference_file_ids=None,
        reference_url=None,
        last_generation_id=99,
    )
    parent_gen = SimpleNamespace(id=99, user_id=42, source_feed_gen_id=None)
    session_obj = AsyncMock()
    repo_stub = SimpleNamespace(
        update_image_session_references=AsyncMock(),
        get_generation_by_id=AsyncMock(return_value=parent_gen),
    )

    with (
        patch("bot.handlers.image_gen._resolve_image_session", AsyncMock(return_value=(image_session, None))),
        patch("bot.handlers.image_gen.repo", new=repo_stub),
    ):
        await image_gen.handle_session_photo(
            message,
            state,
            session_obj,
            SimpleNamespace(id=42),
        )

    markup = message.answer.await_args.kwargs["reply_markup"]
    texts = {button.text for row in markup.inline_keyboard for button in row}
    assert "📤 В ленту" in texts
    assert "📚 В библиотеку" in texts
    assert any(call.kwargs == {"source_feed_gen_id": None} for call in state.update_data.await_args_list)

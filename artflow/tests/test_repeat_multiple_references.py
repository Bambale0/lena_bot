from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import feed, image_gen, repeat_references
from db.models import ImageGenerationAction


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})
        self.state = None
        self.cleared = False

    async def clear(self) -> None:
        self.data = {}
        self.state = None
        self.cleared = True

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict:
        return dict(self.data)


def _call() -> SimpleNamespace:
    return SimpleNamespace(
        data="img_session:repeat:77",
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )


def _callback_handlers(router) -> list:
    handlers = [handler.callback for handler in router.callback_query.handlers]
    for child in router.sub_routers:
        handlers.extend(_callback_handlers(child))
    return handlers


def test_repeat_handlers_are_prioritized_before_legacy_handlers() -> None:
    image_callbacks = _callback_handlers(image_gen.router)
    feed_callbacks = _callback_handlers(feed.router)

    assert image_callbacks.index(repeat_references._session_repeat_interceptor) < image_callbacks.index(
        image_gen.cb_image_session_repeat
    )
    assert image_callbacks.index(repeat_references._regen_repeat_interceptor) < image_callbacks.index(
        image_gen.cb_regen_image
    )
    assert feed_callbacks.index(repeat_references._feed_again_interceptor) < feed_callbacks.index(
        feed.cb_feed_again
    )


def test_repeat_max_refs_uses_remix_model_capability() -> None:
    source_model = "test/text-model"
    remix_model = "test/edit-model"
    with patch.dict(
        repeat_references.IMAGE_CAPS,
        {
            source_model: {"modes": ["text"]},
            remix_model: {"modes": ["image"], "max_refs": 6},
        },
        clear=False,
    ), patch.dict(
        repeat_references.image_gen.IMAGE_SPECS,
        {source_model: SimpleNamespace(remix_model=remix_model)},
        clear=False,
    ):
        assert repeat_references._repeat_max_refs(source_model) == 6


@pytest.mark.asyncio
async def test_begin_repeat_preserves_original_refs_and_waits_for_user() -> None:
    state = FakeState()
    call = _call()
    generation = SimpleNamespace(
        id=77,
        prompt="same hidden prompt",
        model="test/multi-ref",
        aspect_ratio="3:4",
    )
    source_session = SimpleNamespace(
        id=11,
        reference_file_id="old-file-1",
        reference_file_ids='["old-file-1", "old-file-2"]',
        reference_url=None,
        mode="image",
        aspect_ratio="3:4",
        quality="high",
        count=2,
    )

    with patch.dict(
        repeat_references.IMAGE_CAPS,
        {
            "test/multi-ref": {
                "modes": ["text", "image"],
                "max_refs": 5,
                "aspect_ratios": ["16:9", "1:1", "9:16"],
            }
        },
        clear=False,
    ), patch.object(
        repeat_references.image_gen,
        "_supports_img2img",
        return_value=True,
    ), patch.object(
        repeat_references.image_gen,
        "_requires_reference_image",
        return_value=False,
    ), patch.object(
        repeat_references,
        "_resolve_base_reference_urls",
        AsyncMock(return_value=["https://example.test/old-1.jpg", "https://example.test/old-2.jpg"]),
    ), patch.object(
        repeat_references.image_gen,
        "get_image_model_label",
        return_value="Test Model",
    ):
        handled = await repeat_references._begin_repeat_collection(
            call=call,
            state=state,
            bot=AsyncMock(),
            generation=generation,
            source_session=source_session,
            reuse_session=True,
            source_feed_gen_id=None,
        )

    assert handled is True
    assert state.data["repeat_prompt"] == "same hidden prompt"
    assert state.data["repeat_model_key"] == "test/multi-ref"
    assert state.data["repeat_base_reference_urls"] == [
        "https://example.test/old-1.jpg",
        "https://example.test/old-2.jpg",
    ]
    assert state.data["repeat_source_reference_file_ids"] == ["old-file-1", "old-file-2"]
    assert state.data["repeat_new_reference_file_ids"] == []
    assert state.data["repeat_max_refs"] == 5
    assert state.data["repeat_aspect_ratio"] == "9:16"
    assert state.data["repeat_ratio_options"] == ["9:16", "16:9", "1:1"]
    call.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeat_ratio_can_be_changed_before_launch() -> None:
    state = FakeState(
        {
            "repeat_base_reference_urls": ["https://example.test/original.jpg"],
            "repeat_new_reference_file_ids": [],
            "repeat_max_refs": 5,
            "repeat_model_key": "test/multi-ref",
            "repeat_reference_required": False,
            "repeat_aspect_ratio": "9:16",
            "repeat_ratio_options": ["9:16", "16:9", "1:1"],
        }
    )
    call = _call()
    call.data = "repeat_refs:ratio:1:1"

    with patch.object(repeat_references.image_gen, "get_image_model_label", return_value="Test Model"):
        await repeat_references._repeat_refs_ratio(call, state)

    assert state.data["repeat_aspect_ratio"] == "1:1"
    call.message.answer.assert_awaited_once()
    markup = call.message.answer.await_args.kwargs["reply_markup"]
    ratio_buttons = [button for row in markup.inline_keyboard for button in row if button.callback_data and button.callback_data.startswith("repeat_refs:ratio:")]
    assert [button.text for button in ratio_buttons] == ["9:16", "16:9", "✅ 1:1"]


@pytest.mark.asyncio
async def test_collect_repeat_photos_appends_until_provider_limit() -> None:
    state = FakeState(
        {
            "repeat_base_reference_urls": ["https://example.test/original.jpg"],
            "repeat_new_reference_file_ids": [],
            "repeat_max_refs": 3,
            "repeat_model_key": "test/multi-ref",
            "repeat_reference_required": False,
        }
    )
    message = SimpleNamespace(
        photo=[
            SimpleNamespace(file_id="small", file_size=1),
            SimpleNamespace(file_id="new-ref-1", file_size=100),
        ],
        answer=AsyncMock(),
    )

    with patch.object(repeat_references.image_gen, "get_image_model_label", return_value="Test Model"):
        await repeat_references._collect_repeat_reference(message, state)

    assert state.data["repeat_new_reference_file_ids"] == ["new-ref-1"]
    message.answer.assert_awaited_once()

    message.photo = [SimpleNamespace(file_id="new-ref-2", file_size=100)]
    with patch.object(repeat_references.image_gen, "get_image_model_label", return_value="Test Model"):
        await repeat_references._collect_repeat_reference(message, state)
    assert state.data["repeat_new_reference_file_ids"] == ["new-ref-1", "new-ref-2"]

    message.photo = [SimpleNamespace(file_id="overflow", file_size=100)]
    await repeat_references._collect_repeat_reference(message, state)
    assert state.data["repeat_new_reference_file_ids"] == ["new-ref-1", "new-ref-2"]


@pytest.mark.asyncio
async def test_run_repeat_combines_original_and_new_references() -> None:
    state = FakeState(
        {
            "repeat_generation_id": 77,
            "repeat_parent_generation_id": 77,
            "repeat_prompt": "same prompt",
            "repeat_model_key": "test/multi-ref",
            "repeat_max_refs": 5,
            "repeat_reference_required": False,
            "repeat_base_reference_urls": ["https://example.test/original.jpg"],
            "repeat_new_reference_file_ids": ["new-file-1", "new-file-2"],
            "repeat_source_reference_file_ids": ["old-file"],
            "repeat_source_reference_url": None,
            "repeat_source_feed_gen_id": 500,
            "repeat_reuse_session_id": None,
            "repeat_mode": "image",
            "repeat_aspect_ratio": "3:4",
            "repeat_quality": "high",
            "repeat_count": 2,
        }
    )
    generation = SimpleNamespace(id=77, user_id=42, prompt="same prompt", model="test/multi-ref")
    image_session = SimpleNamespace(id=123, mode="image")
    call = _call()
    db_user = SimpleNamespace(id=42)
    session = AsyncMock()

    launch = AsyncMock(return_value=True)
    with patch.object(
        repeat_references.repo,
        "get_generation_by_id",
        AsyncMock(return_value=generation),
    ), patch.object(
        repeat_references.repo,
        "create_image_session",
        AsyncMock(return_value=image_session),
    ) as create_session, patch.object(
        repeat_references.image_gen,
        "_telegram_file_url",
        AsyncMock(
            side_effect=[
                "https://example.test/new-1.jpg",
                "https://example.test/new-2.jpg",
            ]
        ),
    ), patch.object(
        repeat_references.image_gen,
        "_launch_session_generation",
        launch,
    ):
        await repeat_references._repeat_refs_run(
            call,
            session,
            state,
            db_user,
            AsyncMock(),
        )

    create_kwargs = create_session.await_args.kwargs
    assert create_kwargs["reference_file_ids"] == ["old-file", "new-file-1", "new-file-2"]
    assert create_kwargs["mode"] == "image"
    assert create_kwargs["aspect_ratio"] == "3:4"

    launch_kwargs = launch.await_args.kwargs
    assert launch_kwargs["prompt"] == "same prompt"
    assert launch_kwargs["action_type"] == ImageGenerationAction.repeat
    assert launch_kwargs["parent_generation_id"] == 77
    assert launch_kwargs["source_feed_gen_id"] == 500
    assert launch_kwargs["reference_url"] == [
        "https://example.test/original.jpg",
        "https://example.test/new-1.jpg",
        "https://example.test/new-2.jpg",
    ]

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import image_gen, marketplace, repeat_reference_marketplace
from db.models import ImageGenerationAction


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})
        self.state = None

    async def get_data(self) -> dict:
        return dict(self.data)

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def clear(self) -> None:
        self.data = {}
        self.state = None

    async def set_state(self, state) -> None:
        self.state = state


def test_marketplace_multi_ref_handler_precedes_legacy_single_photo_handler() -> None:
    callbacks = [handler.callback for handler in marketplace.router.message.handlers]
    assert callbacks.index(repeat_reference_marketplace._collect_prompt_reference) < callbacks.index(
        marketplace.fsm_prompt_use_reference
    )


@pytest.mark.asyncio
async def test_feed_repeat_collects_first_photo_without_starting_generation() -> None:
    state = FakeState(
        {
            "feed_use_prompt": "hidden feed prompt",
            "feed_use_gen_id": 77,
            "use_model_key": "test/multi-ref",
        }
    )
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="ref-1", file_size=100)],
        answer=AsyncMock(),
    )

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=5,
    ), patch.object(
        repeat_reference_marketplace.image_gen,
        "_supports_img2img",
        return_value=True,
    ), patch.object(
        marketplace,
        "fsm_prompt_use_reference",
        AsyncMock(),
    ) as legacy:
        await repeat_reference_marketplace._collect_prompt_reference(
            message,
            AsyncMock(),
            SimpleNamespace(id=42),
            state,
            AsyncMock(),
        )

    assert state.data["prompt_multi_ref_file_ids"] == ["ref-1"]
    assert state.data["prompt_multi_ref_max"] == 5
    legacy.assert_not_awaited()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_ref_model_uses_legacy_flow() -> None:
    state = FakeState({"use_model_key": "test/single-ref"})
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="ref-1", file_size=100)],
        answer=AsyncMock(),
    )
    legacy = AsyncMock()

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=1,
    ), patch.object(
        repeat_reference_marketplace.image_gen,
        "_supports_img2img",
        return_value=True,
    ), patch.object(marketplace, "fsm_prompt_use_reference", legacy):
        await repeat_reference_marketplace._collect_prompt_reference(
            message,
            AsyncMock(),
            SimpleNamespace(id=42),
            state,
            AsyncMock(),
        )

    legacy.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_feed_repeat_passes_all_reference_urls() -> None:
    state = FakeState(
        {
            "feed_use_prompt": "hidden feed prompt",
            "feed_use_gen_id": 77,
            "use_model_key": "test/multi-ref",
            "prompt_multi_ref_file_ids": ["ref-1", "ref-2", "ref-3"],
            "prompt_multi_ref_max": 5,
        }
    )
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    db_user = SimpleNamespace(id=42, credits=100)
    image_session = SimpleNamespace(id=123)
    launch = AsyncMock(return_value=True)

    with patch.object(
        repeat_reference_marketplace.repeat_references,
        "_repeat_max_refs",
        return_value=5,
    ), patch.object(
        repeat_reference_marketplace,
        "mirror_telegram_file",
        AsyncMock(
            side_effect=[
                "https://example.test/1.jpg",
                "https://example.test/2.jpg",
                "https://example.test/3.jpg",
            ]
        ),
    ), patch.object(
        repeat_reference_marketplace.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=2)),
    ), patch.object(
        repeat_reference_marketplace.repo,
        "create_image_session",
        AsyncMock(return_value=image_session),
    ) as create_session, patch.object(
        repeat_reference_marketplace.marketplace,
        "_default_quality_for_model",
        return_value="basic",
    ), patch.object(
        repeat_reference_marketplace.marketplace,
        "_default_count_for_model",
        return_value=1,
    ), patch.object(image_gen, "_launch_session_generation", launch):
        await repeat_reference_marketplace._run(
            call,
            AsyncMock(),
            db_user,
            state,
            AsyncMock(),
        )

    create_kwargs = create_session.await_args.kwargs
    assert create_kwargs["reference_file_ids"] == ["ref-1", "ref-2", "ref-3"]
    assert create_kwargs["mode"] == "image"

    launch_kwargs = launch.await_args.kwargs
    assert launch_kwargs["action_type"] == ImageGenerationAction.repeat
    assert launch_kwargs["parent_generation_id"] == 77
    assert launch_kwargs["source_feed_gen_id"] == 77
    assert launch_kwargs["reference_url"] == [
        "https://example.test/1.jpg",
        "https://example.test/2.jpg",
        "https://example.test/3.jpg",
    ]

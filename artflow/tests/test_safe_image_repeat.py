from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.repeat_runtime import current_repeat_launch_context
from bot.handlers import repeat_safe
from db import repeat_lookup


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})
        self.state = None

    async def clear(self) -> None:
        self.data = {}
        self.state = None

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict:
        return dict(self.data)


def _call(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=777),
        message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


def _image_source(**extra) -> SimpleNamespace:
    data = {
        "id": 42,
        "user_id": 5,
        "model": "nano-banana-pro",
        "gen_type": SimpleNamespace(value="image"),
        "prompt": "portrait prompt",
    }
    data.update(extra)
    return SimpleNamespace(**data)


def test_candidate_task_ids_support_public_provider_and_web_aliases() -> None:
    assert repeat_lookup.candidate_task_ids("img_c65c8ba58829") == [
        "img_c65c8ba58829",
        "c65c8ba58829",
        "web:img_c65c8ba58829",
        "web:c65c8ba58829",
    ]
    assert repeat_lookup.candidate_task_ids("8aad41f") == [
        "8aad41f",
        "img_8aad41f",
        "web:8aad41f",
        "web:img_8aad41f",
    ]


def test_reference_availability_keeps_external_and_reports_deleted_local() -> None:
    with patch.object(repeat_safe, "public_url_is_available", side_effect=lambda url: "missing" not in str(url)):
        available, missing = repeat_safe.available_reference_images(
            [
                "https://provider.example/live.jpg",
                "https://apix.example/uploads/missing.jpg",
            ]
        )
    assert available == ["https://provider.example/live.jpg"]
    assert missing == ["https://apix.example/uploads/missing.jpg"]


def test_pinterest_repeat_contract_preserves_roles_and_provider_order() -> None:
    contract = repeat_safe.pinterest_repeat_contract(
        {
            "flow": "pinterest",
            "scene_reference": "https://example.test/scene.jpg",
            "identity_reference": "https://example.test/me.jpg",
            "identity_evidence": ["https://example.test/me-2.jpg"],
            "reference_roles": ["scene", "identity", "identity_evidence"],
            "trend_id": 91,
        }
    )
    assert contract["reference_images"] == [
        "https://example.test/scene.jpg",
        "https://example.test/me.jpg",
        "https://example.test/me-2.jpg",
    ]
    assert contract["reference_roles"] == ["scene", "identity", "identity_evidence"]
    assert contract["provider_reference_images"] == [
        "https://example.test/me.jpg",
        "https://example.test/scene.jpg",
    ]
    assert contract["trend_id"] == 91


def test_repeat_router_registers_exact_confirm_cancel_before_open_compat() -> None:
    callbacks = [handler.callback for handler in repeat_safe.router.callback_query.handlers]
    assert callbacks.index(repeat_safe.confirm_repeat) < callbacks.index(repeat_safe.open_repeat)
    assert callbacks.index(repeat_safe.cancel_repeat) < callbacks.index(repeat_safe.open_repeat)


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_data", ["repeat_image_img_abc", "repeat_result_img_abc"])
async def test_old_and_new_repeat_callbacks_open_confirmation_without_launch(callback_data: str) -> None:
    state = FakeState()
    call = _call(callback_data)
    generation = _image_source(
        credits_spent=2.5,
        image_session_id=None,
        source_feed_gen_id=None,
        input_params='{"public_task_id":"img_abc","img_ratio":"9:16","img_quality":"2K","img_count":1,"reference_images":[]}',
    )
    user = SimpleNamespace(id=5, tg_id=777, credits=10)
    cost = SimpleNamespace(credits=2.5)

    with patch.object(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=generation)), patch.object(
        repeat_safe.repo, "resolve_image_model_cost", AsyncMock(return_value=cost)
    ), patch.object(repeat_safe, "_is_admin", return_value=False), patch.object(
        repeat_safe.image_gen, "_launch_session_generation", AsyncMock()
    ) as launch:
        await repeat_safe.open_repeat(call, AsyncMock(), state, user, AsyncMock())

    launch.assert_not_awaited()
    call.message.answer.assert_awaited_once()
    assert state.data["repeat_source_generation_id"] == 42
    assert state.data["repeat_prompt"] == "portrait prompt"
    assert state.data["repeat_cost"] == 2.5


@pytest.mark.asyncio
async def test_confirm_launches_once_and_carries_repeat_parent_metadata() -> None:
    state = FakeState(
        {
            "repeat_source_generation_id": 42,
            "repeat_raw_task_id": "img_abc",
            "repeat_model_key": "nano-banana-pro",
            "repeat_prompt": "portrait prompt",
            "repeat_aspect_ratio": "9:16",
            "repeat_quality": "basic",
            "repeat_count": 1,
            "repeat_reference_images": [],
            "repeat_source_feed_gen_id": 100,
            "repeat_confirm_key": "repeat-confirm-abc",
            "repeat_cost": 2.5,
            "repeat_is_admin": False,
        }
    )
    call = _call("repeat_run_confirm_img_abc")
    source = _image_source()
    user = SimpleNamespace(id=5, tg_id=777, credits=10)
    image_session = SimpleNamespace(id=501, model="nano-banana-pro", mode="text")
    captured = {}

    async def launch(**kwargs):
        captured["kwargs"] = kwargs
        captured["context"] = current_repeat_launch_context()
        return True

    with patch.object(repeat_safe.repo, "get_generation_by_id", AsyncMock(return_value=source)), patch.object(
        repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None)
    ), patch.object(repeat_safe.repo, "create_image_session", AsyncMock(return_value=image_session)), patch.object(
        repeat_safe.image_gen, "_launch_session_generation", AsyncMock(side_effect=launch)
    ) as launch_mock:
        await repeat_safe.confirm_repeat(call, AsyncMock(), state, user, AsyncMock())

    launch_mock.assert_awaited_once()
    kwargs = captured["kwargs"]
    context = captured["context"]
    assert kwargs["parent_generation_id"] == 42
    assert kwargs["source_feed_gen_id"] == 100
    assert kwargs["action_type"].value == "repeat"
    assert context is not None
    assert context.input_params_extra["repeat_source_task_id"] == "img_abc"
    assert context.input_params_extra["repeat_confirm_key"] == "repeat-confirm-abc"
    assert context.credits_override is None
    call.answer.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_is_idempotent_for_double_click() -> None:
    state = FakeState(
        {
            "repeat_source_generation_id": 42,
            "repeat_raw_task_id": "img_abc",
            "repeat_confirm_key": "repeat-confirm-abc",
        }
    )
    call = _call("repeat_run_confirm_img_abc")
    user = SimpleNamespace(id=5, tg_id=777, credits=10)
    existing = SimpleNamespace(id=99, task_id="provider-task", status=SimpleNamespace(value="processing"))

    with patch.object(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=existing)), patch.object(
        repeat_safe.image_gen, "_launch_session_generation", AsyncMock()
    ) as launch:
        await repeat_safe.confirm_repeat(call, AsyncMock(), state, user, AsyncMock())

    launch.assert_not_awaited()
    call.answer.assert_awaited()


@pytest.mark.asyncio
async def test_missing_required_references_block_confirm() -> None:
    state = FakeState(
        {
            "repeat_source_generation_id": 42,
            "repeat_raw_task_id": "img_abc",
            "repeat_model_key": "test/i2i-only",
            "repeat_prompt": "same prompt",
            "repeat_reference_images": [],
            "repeat_reference_required": True,
            "repeat_confirm_key": "repeat-confirm-missing",
        }
    )
    call = _call("repeat_run_confirm_img_abc")
    source = _image_source(model="test/i2i-only", prompt="same prompt")
    user = SimpleNamespace(id=5, tg_id=777, credits=10)

    with patch.object(repeat_safe.repo, "get_generation_by_id", AsyncMock(return_value=source)), patch.object(
        repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None)
    ), patch.object(repeat_safe.image_gen, "_launch_session_generation", AsyncMock()) as launch:
        await repeat_safe.confirm_repeat(call, AsyncMock(), state, user, AsyncMock())

    launch.assert_not_awaited()
    call.answer.assert_awaited()


@pytest.mark.asyncio
async def test_admin_repeat_uses_zero_credit_override_only_after_confirm() -> None:
    state = FakeState(
        {
            "repeat_source_generation_id": 42,
            "repeat_raw_task_id": "img_admin",
            "repeat_model_key": "nano-banana-pro",
            "repeat_prompt": "same prompt",
            "repeat_reference_images": [],
            "repeat_confirm_key": "repeat-admin",
            "repeat_is_admin": True,
            "repeat_cost": 0,
        }
    )
    call = _call("repeat_run_confirm_img_admin")
    source = _image_source()
    user = SimpleNamespace(id=5, tg_id=777, credits=0)
    image_session = SimpleNamespace(id=501)
    captured = {}

    async def launch(**kwargs):
        captured["context"] = current_repeat_launch_context()
        return True

    with patch.object(repeat_safe.repo, "get_generation_by_id", AsyncMock(return_value=source)), patch.object(
        repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None)
    ), patch.object(repeat_safe.repo, "create_image_session", AsyncMock(return_value=image_session)), patch.object(
        repeat_safe.image_gen, "_launch_session_generation", AsyncMock(side_effect=launch)
    ):
        await repeat_safe.confirm_repeat(call, AsyncMock(), state, user, AsyncMock())

    assert captured["context"].credits_override == 0.0

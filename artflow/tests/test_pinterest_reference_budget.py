from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from api import pinterest_service_routes as routes
from bot.handlers import pinterest_flow as flow
from bot.keyboards.models import IMAGE_CAPS


@pytest.mark.asyncio
async def test_metadata_budget_reserves_scene_and_identity_slots(monkeypatch):
    monkeypatch.setattr(routes, "_validate_runtime", AsyncMock())
    monkeypatch.setattr(routes, "_service_price_credits", AsyncMock(return_value=2))
    result = await routes.get_pinterest_service(SimpleNamespace(), SimpleNamespace())
    assert result["max_identity_angles"] == IMAGE_CAPS[routes.PINTEREST_MODEL]["max_refs"] - 2


@pytest.mark.asyncio
async def test_bot_rejects_extra_before_upload_at_current_model_limit(monkeypatch):
    data = {
        "scene_asset_id": "scene",
        "identity_asset_id": "identity",
        "extra_asset_ids": ["extra1", "extra2"],
    }
    state = SimpleNamespace(get_data=AsyncMock(return_value=data), update_data=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock())
    upload = AsyncMock(return_value="third-extra")
    monkeypatch.setattr(flow, "_best_photo_asset_id", upload)
    await flow.extra_photo(message, state, SimpleNamespace(), SimpleNamespace(id=7))
    upload.assert_not_awaited()
    state.update_data.assert_not_awaited()
    assert "2" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_direct_service_limit_is_checked_before_asset_work_or_generation(monkeypatch):
    monkeypatch.setattr(routes, "_validate_runtime", AsyncMock())
    monkeypatch.setattr(routes, "_service_price_credits", AsyncMock(return_value=2))
    monkeypatch.setattr(routes, "_find_idempotent_run", AsyncMock(return_value=None))
    verify = Mock(side_effect=AssertionError("must reject before asset access"))
    monkeypatch.setattr(routes, "verify_uploaded_asset", verify)
    with pytest.raises(HTTPException, match="4"):
        await routes.launch_pinterest_service(
            SimpleNamespace(),
            SimpleNamespace(id=7),
            idempotency_key="test-limit-12345",
            reference_asset_ids=["a", "b", "c", "d", "e"],
            height_cm=175,
            weight_kg=70,
        )
    verify.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity,extra", [(2, 0), (3, 1), (9, 2)])
async def test_service_budget_tracks_model_caps_but_never_exceeds_provider(
    monkeypatch, capacity, extra
):
    monkeypatch.setitem(
        IMAGE_CAPS,
        routes.PINTEREST_MODEL,
        {**IMAGE_CAPS[routes.PINTEREST_MODEL], "max_refs": capacity},
    )
    monkeypatch.setattr(routes, "_validate_runtime", AsyncMock())
    monkeypatch.setattr(routes, "_service_price_credits", AsyncMock(return_value=2))
    result = await routes.get_pinterest_service(SimpleNamespace(), SimpleNamespace())
    assert result["max_identity_angles"] == extra


@pytest.mark.asyncio
async def test_stale_overlimit_bot_draft_stays_editable_without_launch(monkeypatch):
    data = {
        "scene_asset_id": "scene",
        "identity_asset_id": "identity",
        "extra_asset_ids": ["a", "b", "c"],
        "height_cm": 170,
        "weight_kg": 70,
    }
    state = SimpleNamespace(
        get_data=AsyncMock(return_value=data), set_state=AsyncMock(), clear=AsyncMock()
    )
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    launch = AsyncMock()
    monkeypatch.setattr(flow, "_run_pinterest_service", launch)
    await flow.confirm_and_run(call, state, SimpleNamespace(), SimpleNamespace(id=7))
    launch.assert_not_awaited()
    state.clear.assert_not_awaited()
    assert state.set_state.await_args.args[0] == flow.PinterestFlow.waiting_extra_references

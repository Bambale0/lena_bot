from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes


@pytest.mark.asyncio
@pytest.mark.parametrize("auto", [False, True])
async def test_video_catalog_exposes_existing_input_routing_capability(monkeypatch, auto):
    key = next(model.value for model in miniapp_routes.VideoModel if model.value in miniapp_routes.VIDEO_CAPS)
    monkeypatch.setitem(miniapp_routes.VIDEO_CAPS, key, {
        "modes": ["text", "image"], "auto_route_by_inputs": auto,
        "max_refs": 2, "duration_options": [5], "resolutions": ["720p"],
    })
    monkeypatch.setattr(miniapp_routes.repo, "get_all_model_costs", AsyncMock(return_value=[
        SimpleNamespace(model_key=key, credits=1, display_name="Catalog fixture", is_active=True),
    ]))
    monkeypatch.setattr(miniapp_routes, "_video_model_rate_info", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(miniapp_routes, "_resolve_video_price_table", AsyncMock(return_value={}))
    models = await miniapp_routes.list_video_models(AsyncMock(), SimpleNamespace(id=7))
    payload = next(model.model_dump() for model in models if model.key == key)
    assert payload.get("auto_route_by_inputs") is auto

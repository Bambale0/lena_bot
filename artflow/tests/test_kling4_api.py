from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.kling4_contract import REFERENCE_MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["quote_video_generation", "create_video_generation"])
async def test_regular_user_cannot_quote_or_launch_even_by_direct_api(handler, monkeypatch):
    from api import miniapp_routes as routes
    from core.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    body = routes.VideoGenRequest(model=REFERENCE_MODEL, prompt="A scene")
    with pytest.raises(HTTPException) as error:
        await getattr(routes, handler)(
            body,
            session=SimpleNamespace(get=AsyncMock(return_value=None)),
            user=SimpleNamespace(tg_id=555),
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_catalog_filters_preview_for_regular_user(monkeypatch):
    from api import miniapp_routes as routes
    from core.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    monkeypatch.setattr(
        routes.repo,
        "get_all_model_costs",
        AsyncMock(return_value=[SimpleNamespace(model_key=REFERENCE_MODEL)]),
    )
    assert (
        await routes.list_video_models(
            session=SimpleNamespace(get=AsyncMock(return_value=None)),
            user=SimpleNamespace(tg_id=555),
        )
        == []
    )


@pytest.mark.asyncio
async def test_existing_intent_cannot_be_reused_with_changed_materials(monkeypatch):
    import json

    from api import kling4_checkout as checkout
    from api.kling4_contract import Kling4Input
    from api.miniapp_routes import VideoGenRequest
    from db.models import Generation, Kling4Intent

    monkeypatch.setattr(checkout, "require_kling4_access", AsyncMock())
    gen = SimpleNamespace(
        model=REFERENCE_MODEL,
        prompt="A scene",
        input_params=json.dumps({"kling4": Kling4Input().model_dump()}),
    )

    async def get(model, key):
        return (
            SimpleNamespace(user_id=1, generation_id=12)
            if model is Kling4Intent
            else gen
            if model is Generation
            else None
        )

    body = VideoGenRequest(
        model=REFERENCE_MODEL,
        prompt="A scene",
        duration=10,
        intent_id="12345678-1234-1234-1234-123456789abc",
    )
    with pytest.raises(HTTPException) as error:
        await checkout.create_kling4_generation(
            body,
            body.prompt,
            SimpleNamespace(get=get),
            SimpleNamespace(id=1),
            surface="web",
            callback_url="https://example.org/callback",
        )
    assert error.value.status_code == 409


@pytest.mark.parametrize("duration", [True, "5", 5.0])
def test_api_rejects_coercion_of_kling4_duration(duration):
    from api.miniapp_routes import VideoGenRequest

    with pytest.raises(ValueError):
        VideoGenRequest(model=REFERENCE_MODEL, prompt="A scene", duration=duration)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [1, 2])
async def test_saved_recipe_is_only_exported_to_its_owner(monkeypatch, owner):
    import json

    from api.kling4_contract import Kling4Input
    from api.web import generations as routes
    from core import kling4_access

    monkeypatch.setattr(kling4_access, "require_kling4_access", AsyncMock())
    options = Kling4Input(first_frame_url="https://media.example.org/kling4/1/first.png")
    generation = SimpleNamespace(
        user_id=owner,
        model="kling-4.0/keyframe-to-video",
        prompt="@first_frame Move",
        input_params=json.dumps({"kling4": options.model_dump()}),
        source_feed_gen_id=None,
    )
    monkeypatch.setattr(routes.repo, "get_generation_by_id", AsyncMock(return_value=generation))
    result = await routes.kling4_owned_recipe(1, session=None, user=SimpleNamespace(id=1))
    if owner == 1:
        assert result["data"]["kling4"]["first_frame_url"] == options.first_frame_url
    else:
        assert result.status_code == 404


@pytest.mark.asyncio
async def test_upload_rejects_changed_owner_before_reading_private_file(monkeypatch):
    from api.web import generations as routes
    from core import kling4_access

    monkeypatch.setattr(kling4_access, "require_kling4_access", AsyncMock())
    file = SimpleNamespace(read=AsyncMock())
    result = await routes.upload_kling4_asset(file=file, owner_id=1, session=None, user=SimpleNamespace(id=2))
    assert result.status_code == 409
    file.read.assert_not_awaited()

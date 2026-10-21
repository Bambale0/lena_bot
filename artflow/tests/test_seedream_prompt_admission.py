from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import image_service, miniapp_routes
from api.image_service import ImageModel
from bot.handlers import image_gen
from db.models import ImageGenerationAction


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [ImageModel.SEEDREAM_5_PRO_T2I, ImageModel.SEEDREAM_5_PRO_I2I])
async def test_seedream_oversize_rejected_before_upload_and_paid_submit(monkeypatch, model):
    upload = AsyncMock(return_value="https://example.test/ref.png")
    create = AsyncMock(return_value={"data": {"taskId": "unexpected-task"}})
    monkeypatch.setattr(image_service, "_prepare_reference_urls_for_model", upload)
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)
    with pytest.raises(ValueError, match="5000"):
        await image_service.generate_image(
            model, "я" * 5001, image_url="https://example.test/ref.png"
        )
    upload.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["miniapp", "web"])
async def test_long_stored_prompt_rejected_before_api_charge(monkeypatch, surface):
    from db import prompt_repository

    prompt = SimpleNamespace(id=31, prompt_text="a" * 6366)
    monkeypatch.setattr(prompt_repository, "get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr(miniapp_routes, "_is_prompt_public_approved", lambda p: True)
    monkeypatch.setattr(miniapp_routes, "is_trend_prompt", lambda p: False)
    charge = AsyncMock(side_effect=AssertionError("must reject before charging"))
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(
        miniapp_routes.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=1)),
    )
    body = miniapp_routes.ImageGenRequest(
        model=ImageModel.SEEDREAM_5_PRO_T2I.value, prompt="copy saved prompt", prompt_id=31
    )
    if surface == "web":
        from api.web.generations import generate_image

        response = await generate_image(body, SimpleNamespace(), SimpleNamespace(id=7))
        assert response.status_code == 422
        assert b"5000" in response.body
    else:
        with pytest.raises(HTTPException, match="5000"):
            await miniapp_routes.create_image_generation(
                body, SimpleNamespace(), SimpleNamespace(id=7)
            )
    charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_long_prompt_does_not_charge_or_clear_user_draft(monkeypatch):
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={}), update_data=AsyncMock(), clear=AsyncMock()
    )
    image_session = SimpleNamespace(
        id=1,
        model=ImageModel.SEEDREAM_5_PRO_T2I.value,
        count=1,
        quality="basic",
        aspect_ratio="1:1",
    )
    charge = AsyncMock(side_effect=AssertionError("must reject before charging"))
    monkeypatch.setattr(image_gen.repo, "charge_image_generation", charge)
    result = await image_gen._launch_session_generation(
        source_message=message,
        state=state,
        session=SimpleNamespace(commit=AsyncMock()),
        db_user=SimpleNamespace(id=7),
        image_session=image_session,
        prompt="a" * 6366,
        action_type=ImageGenerationAction.initial,
        reference_url=None,
        parent_generation_id=None,
        launching_text="start",
        queued_text="queued",
    )
    assert result is False
    assert "5000" in message.answer.await_args.args[0]
    charge.assert_not_awaited()
    state.clear.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [ImageModel.SEEDREAM_5_PRO_T2I, ImageModel.SEEDREAM_5_PRO_I2I])
async def test_seedream_boundary_sends_full_prompt_unchanged(monkeypatch, model):
    prompt = "я" * 5000
    create = AsyncMock(return_value={"data": {"taskId": "boundary-task"}})
    monkeypatch.setattr(image_service.kieai_client, "create_task", create)
    monkeypatch.setattr(
        image_service, "_prepare_reference_urls_for_model", AsyncMock(return_value=None)
    )
    result = await image_service.generate_image(model, prompt)
    assert result.task_id == "boundary-task"
    assert create.await_args.args[0]["input"]["prompt"] == prompt

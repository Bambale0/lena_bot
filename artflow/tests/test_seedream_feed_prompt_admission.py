from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import miniapp_routes
from db import repository as repo
from tests import test_nano_banana_pro_reference_transport as fixtures

local_launch = fixtures.local_launch


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_feed_recipe_oversize_rejected_before_charge(local_launch, monkeypatch, surface):
    launch = local_launch
    launch.source.user_id = launch.user.id
    launch.source.model = "seedream/5-pro-image-to-image"
    launch.source.prompt = "a" * 6366
    launch.source.input_params = {"hidden_prompt": False}
    generate = AsyncMock(side_effect=AssertionError("no provider submission permitted"))
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", generate)
    with pytest.raises(HTTPException, match="5000") as caught:
        await miniapp_routes.remix_feed_post(
            77,
            miniapp_routes.FeedRemixRequest(model="seedream/5-pro-image-to-image"),
            session=launch.session,
            user=launch.user,
            surface=surface,
        )
    assert caught.value.status_code == 422
    repo.charge_image_generation.assert_not_awaited()
    generate.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["quote_feed_remix", "remix_feed_post"])
async def test_rendered_identity_instructions_count_towards_seedream_budget(
    local_launch, monkeypatch, entrypoint
):
    launch = local_launch
    launch.source.model = "seedream/5-pro-image-to-image"
    launch.source.prompt = "a" * 4900
    launch.source.input_params = {"hidden_prompt": False}
    policy = AsyncMock(return_value="Identity preservation rule. " * 100)
    monkeypatch.setattr(miniapp_routes, "get_feed_recipe_identity_instruction", policy)
    with pytest.raises(HTTPException, match="5000") as caught:
        await getattr(miniapp_routes, entrypoint)(
            77,
            miniapp_routes.FeedRemixRequest(
                model="seedream/5-pro-image-to-image", image_url=fixtures.REFS[0]
            ),
            session=launch.session,
            user=launch.user,
        )
    assert caught.value.status_code == 422
    policy.assert_awaited_once()
    repo.charge_image_generation.assert_not_awaited()

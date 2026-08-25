from __future__ import annotations

from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from pydantic import ValidationError

from api.pinterest_contract import (
    PINTEREST_PROMPT_MARKER,
    build_pinterest_contract,
    install_pinterest_persistence_contract,
    install_pinterest_provider_contract,
    is_pinterest_prompt_source,
    pinterest_provider_context,
    pinterest_provider_prompt,
)
from api.pinterest_trend_backend import (
    MAX_PINTEREST_REFERENCES,
    PINTEREST_MODEL,
    PINTEREST_SERVICE_ALIAS_ID,
    PinterestTrendRunRequest,
)
from db import repository as repository_module


def test_pinterest_detection_does_not_capture_ordinary_image_trends() -> None:
    pinterest = SimpleNamespace(title="Повтори фото с Pinterest", tags=["trend", "pinterest-repeat"])
    ordinary = SimpleNamespace(title="Летний портрет", tags=["trend", "portrait"])
    assert is_pinterest_prompt_source(pinterest) is True
    assert is_pinterest_prompt_source(ordinary) is False


def test_product_and_provider_metadata_preserve_scene_first_order() -> None:
    contract = build_pinterest_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=[
            "https://example.test/person-side.jpg",
            "https://example.test/person-back.jpg",
        ],
        trend_id=42,
        height_cm=175,
        weight_kg=72,
        confirmed=True,
    )
    expected_images = [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/person-side.jpg",
        "https://example.test/person-back.jpg",
    ]
    expected_roles = [
        "scene",
        "identity",
        "identity_evidence",
        "identity_evidence",
    ]
    assert contract["reference_images"] == expected_images
    assert contract["reference_roles"] == expected_roles
    assert contract["provider_reference_images"] == expected_images
    assert contract["provider_reference_roles"] == expected_roles
    assert contract["prompt_hidden"] is True
    assert contract["prompt_actions_allowed"] is False
    assert contract["feed_prompt_visible"] is False
    assert contract["height_cm"] == 175
    assert contract["weight_kg"] == 72
    assert contract["confirmed"] is True


def test_provider_prompt_contains_identity_scene_and_partial_transfer_guards() -> None:
    prompt = pinterest_provider_prompt("Private scene recipe", height_cm=168, weight_kg=58)
    assert PINTEREST_PROMPT_MARKER in prompt
    assert "Image 1 is the only SCENE_REFERENCE" in prompt
    assert "Image 2 is the PRIMARY USER_IDENTITY_REFERENCE" in prompt
    assert "Images 3 and later" in prompt
    assert "USER_IDENTITY_EVIDENCE" in prompt
    assert "Do not preserve the person from Image 1" in prompt
    assert "PARTIAL TRANSFER GUARD" in prompt
    assert "Do not copy person from scene reference" in prompt
    assert "Do not replace identity" in prompt
    assert "height 168 cm" in prompt
    assert "weight 58 kg" in prompt
    assert "Private scene recipe" in prompt


@pytest.mark.asyncio
async def test_provider_sends_scene_identity_and_optional_identity_evidence() -> None:
    original = AsyncMock(return_value=SimpleNamespace(task_id="task-1"))
    service = SimpleNamespace(
        generate_image=original,
        ensure_provider_safe_png_url=lambda url: url,
        local_upload_path_from_url=lambda _url: None,
    )
    install_pinterest_provider_contract(service)
    contract = build_pinterest_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=["https://example.test/evidence.jpg"],
        trend_id=42,
        height_cm=170,
        weight_kg=60,
        confirmed=True,
    )

    with pinterest_provider_context(contract):
        await service.generate_image(
            "nano-banana-pro",
            "private prompt",
            image_url=["identity-wrong-first.jpg", "scene-wrong-second.jpg", "evidence.jpg"],
            aspect_ratio="3:4",
            quality="2K",
        )

    args = original.await_args.args
    kwargs = original.await_args.kwargs
    assert args[0] == "nano-banana-pro"
    assert PINTEREST_PROMPT_MARKER in args[1]
    assert "USER_IDENTITY_EVIDENCE" in args[1]
    assert kwargs["image_url"] == [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/evidence.jpg",
    ]


@pytest.mark.asyncio
async def test_private_recipe_is_redacted_before_generation_and_session_commits() -> None:
    create_generation = create_autospec(repository_module.create_generation)
    create_generation.return_value = SimpleNamespace(id=7)
    create_session = create_autospec(repository_module.create_image_session)
    create_session.return_value = SimpleNamespace(id=5)
    update_last_prompt = create_autospec(repository_module.update_image_session_last_prompt)
    update_last_prompt.return_value = None
    repository = SimpleNamespace(
        create_generation=create_generation,
        create_image_session=create_session,
        update_image_session_last_prompt=update_last_prompt,
    )
    install_pinterest_persistence_contract(repository)
    contract = build_pinterest_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        trend_id=42,
        height_cm=170,
        weight_kg=60,
        confirmed=True,
    )

    with pinterest_provider_context(contract):
        await repository.create_generation(
            "session",
            1,
            "nano-banana-pro",
            "image",
            "SECRET PRIVATE RECIPE",
            10,
            input_params={"hidden_prompt": True},
        )
        await repository.create_image_session(
            session="session",
            user_id=1,
            model="nano-banana-pro",
            mode="image",
            aspect_ratio="3:4",
            quality="2K",
            count=1,
            base_prompt="SECRET PRIVATE RECIPE",
            reference_url="https://example.test/scene.jpg",
            reference_urls=["https://example.test/person.jpg"],
        )
        await repository.update_image_session_last_prompt("session", 5, "SECRET PRIVATE RECIPE")

    generation_call = signature(repository_module.create_generation).bind_partial(
        *create_generation.await_args.args,
        **create_generation.await_args.kwargs,
    )
    session_call = signature(repository_module.create_image_session).bind_partial(
        *create_session.await_args.args,
        **create_session.await_args.kwargs,
    )
    last_prompt_call = signature(repository_module.update_image_session_last_prompt).bind_partial(
        *update_last_prompt.await_args.args,
        **update_last_prompt.await_args.kwargs,
    )
    assert generation_call.arguments["prompt"] != "SECRET PRIVATE RECIPE"
    assert generation_call.arguments["input_params"]["reference_contract"] == "pinterest_scene_identity"
    assert generation_call.arguments["input_params"]["prompt_hidden"] is True
    assert session_call.arguments["base_prompt"] != "SECRET PRIVATE RECIPE"
    assert last_prompt_call.arguments["last_prompt"] != "SECRET PRIVATE RECIPE"


def test_strict_request_requires_two_to_seven_assets_and_measurements() -> None:
    valid = PinterestTrendRunRequest(
        reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
        height_cm=175,
        weight_kg=72,
        confirmed=True,
        idempotency_key="pinterest-run-1234",
    )
    assert len(valid.reference_asset_ids) == 2
    assert PINTEREST_MODEL == "nano-banana-pro"
    assert PINTEREST_SERVICE_ALIAS_ID == 0

    with pytest.raises(ValidationError):
        PinterestTrendRunRequest(
            reference_asset_ids=["only-one-asset-0001"],
            height_cm=175,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestTrendRunRequest(
            reference_asset_ids=[f"signed-asset-{index:04d}" for index in range(MAX_PINTEREST_REFERENCES + 1)],
            height_cm=175,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestTrendRunRequest(
            reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
            height_cm=119,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestTrendRunRequest(
            reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
            height_cm=175,
            weight_kg=251,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )


def test_bootstrap_installs_pinterest_service_routes_and_preserves_generic_route() -> None:
    from api import trends_routes

    methods_by_path = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()) or set())
        for route in trends_routes.router.routes
    }
    assert "GET" in methods_by_path["/api/v1/services/pinterest"]
    assert "POST" in methods_by_path["/api/v1/trends/{trend_id}/run"]
    assert "POST" in methods_by_path["/api/v1/trends/{trend_id}/pinterest-run"]
    assert getattr(trends_routes, "PINTEREST_SERVICE_ALIAS_ID", None) == 0
    assert getattr(trends_routes, "_pinterest_trend_backend_installed", False) is True

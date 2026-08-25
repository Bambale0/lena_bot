from __future__ import annotations

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
    PinterestTrendRunRequest,
)
from db import repository as repository_module


def test_pinterest_detection_does_not_capture_ordinary_image_trends() -> None:
    pinterest = SimpleNamespace(title="Повтори фото с Pinterest", tags=["trend", "pinterest-repeat"])
    ordinary = SimpleNamespace(title="Летний портрет", tags=["trend", "portrait"])
    assert is_pinterest_prompt_source(pinterest) is True
    assert is_pinterest_prompt_source(ordinary) is False


def test_product_metadata_is_scene_first_but_provider_is_identity_first() -> None:
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
    assert contract["reference_images"] == [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/person-side.jpg",
        "https://example.test/person-back.jpg",
    ]
    assert contract["reference_roles"] == [
        "scene",
        "identity",
        "identity_evidence",
        "identity_evidence",
    ]
    assert contract["provider_reference_images"] == [
        "https://example.test/person.jpg",
        "https://example.test/scene.jpg",
    ]
    assert contract["provider_reference_roles"] == ["identity", "scene"]
    assert contract["prompt_hidden"] is True
    assert contract["prompt_actions_allowed"] is False
    assert contract["feed_prompt_visible"] is False
    assert contract["height_cm"] == 175
    assert contract["weight_kg"] == 72
    assert contract["confirmed"] is True


def test_provider_prompt_contains_identity_scene_and_partial_transfer_guards() -> None:
    prompt = pinterest_provider_prompt("Private scene recipe", height_cm=168, weight_kg=58)
    assert PINTEREST_PROMPT_MARKER in prompt
    assert "Image 1 is the only USER_IDENTITY_REFERENCE" in prompt
    assert "Image 2 is the only SCENE_REFERENCE" in prompt
    assert "Do not preserve the person from Image 2" in prompt
    assert "PARTIAL TRANSFER GUARD" in prompt
    assert "Do not copy person from scene reference" in prompt
    assert "Do not replace identity" in prompt
    assert "height 168 cm" in prompt
    assert "weight 58 kg" in prompt
    assert "Private scene recipe" in prompt


@pytest.mark.asyncio
async def test_provider_sends_only_identity_and_scene_semantic_anchors() -> None:
    original = AsyncMock(return_value=SimpleNamespace(task_id="task-1"))
    service = SimpleNamespace(generate_image=original)
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
            image_url=["scene-wrong-first.jpg", "identity-wrong-second.jpg", "evidence.jpg"],
            aspect_ratio="3:4",
            quality="2K",
        )

    args = original.await_args.args
    kwargs = original.await_args.kwargs
    assert args[0] == "nano-banana-pro"
    assert PINTEREST_PROMPT_MARKER in args[1]
    assert kwargs["image_url"] == [
        "https://example.test/person.jpg",
        "https://example.test/scene.jpg",
    ]
    assert "evidence.jpg" not in kwargs["image_url"]


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
            reference_url="https://example.test/person.jpg",
            reference_urls=["https://example.test/person.jpg", "https://example.test/scene.jpg"],
        )
        await repository.update_image_session_last_prompt("session", 5, "SECRET PRIVATE RECIPE")

    gen_args = create_generation.await_args.args
    gen_kwargs = create_generation.await_args.kwargs
    assert gen_args[4] != "SECRET PRIVATE RECIPE"
    assert gen_kwargs["input_params"]["reference_contract"] == "pinterest_scene_identity"
    assert gen_kwargs["input_params"]["prompt_hidden"] is True
    assert create_session.await_args.kwargs["base_prompt"] != "SECRET PRIVATE RECIPE"
    assert update_last_prompt.await_args.args[2] != "SECRET PRIVATE RECIPE"


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


def test_bootstrap_installs_strict_pinterest_route_and_preserves_generic_route() -> None:
    from api import trends_routes

    methods_by_path = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()) or set())
        for route in trends_routes.router.routes
    }
    assert "POST" in methods_by_path["/api/v1/trends/{trend_id}/run"]
    assert "POST" in methods_by_path["/api/v1/trends/{trend_id}/pinterest-run"]
    assert getattr(trends_routes, "_pinterest_trend_backend_installed", False) is True

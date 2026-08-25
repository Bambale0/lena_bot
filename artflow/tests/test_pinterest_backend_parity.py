from __future__ import annotations

from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from pydantic import ValidationError

from api.pinterest_service_contract import (
    PINTEREST_PROMPT_MARKER,
    PINTEREST_SERVICE_ID,
    active_pinterest_service_contract,
    build_pinterest_service_contract,
    install_pinterest_persistence_contract,
    install_pinterest_provider_contract,
    pinterest_provider_prompt,
    pinterest_service_provider_context,
)
from api.pinterest_service_routes import (
    MAX_PINTEREST_REFERENCES,
    PINTEREST_MODEL,
    PINTEREST_QUALITY,
    PINTEREST_RECIPE_VERSION,
    PinterestServiceRunRequest,
    get_pinterest_service,
    run_pinterest_service,
)
from db import repository as repository_module
from db.models import GenerationType


def test_service_contract_has_no_trend_identity() -> None:
    contract = build_pinterest_service_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=[
            "https://example.test/person-side.jpg",
            "https://example.test/person-back.jpg",
        ],
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
    expected_roles = ["scene", "identity", "identity_evidence", "identity_evidence"]
    assert contract["source"] == "service"
    assert contract["service_id"] == PINTEREST_SERVICE_ID
    assert "trend_id" not in contract
    assert contract["reference_images"] == expected_images
    assert contract["reference_roles"] == expected_roles
    assert contract["provider_reference_images"] == expected_images
    assert contract["provider_reference_roles"] == expected_roles
    assert contract["height_cm"] == 175
    assert contract["weight_kg"] == 72
    assert contract["confirmed"] is True
    assert contract["prompt_hidden"] is True
    assert contract["prompt_actions_allowed"] is False
    assert contract["feed_prompt_visible"] is False


def test_provider_prompt_contains_reference_and_measurement_guards() -> None:
    prompt = pinterest_provider_prompt("Private service recipe", height_cm=168, weight_kg=58)
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
    assert "Private service recipe" in prompt


@pytest.mark.asyncio
async def test_provider_canonicalizes_scene_user_and_identity_evidence() -> None:
    original = AsyncMock(return_value=SimpleNamespace(task_id="task-1"))
    service = SimpleNamespace(
        generate_image=original,
        ensure_provider_safe_png_url=lambda url: url,
        local_upload_path_from_url=lambda _url: None,
    )
    install_pinterest_provider_contract(service)
    contract = build_pinterest_service_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=["https://example.test/evidence.jpg"],
        height_cm=170,
        weight_kg=60,
        confirmed=True,
    )
    # Deliberately poison caller ordering: semantic role fields must win.
    contract["provider_reference_images"] = [
        "https://example.test/person.jpg",
        "https://example.test/scene.jpg",
    ]

    with pinterest_service_provider_context(contract):
        await service.generate_image(
            "nano-banana-pro",
            "private prompt",
            image_url=["wrong.jpg"],
            aspect_ratio="3:4",
            quality="2K",
        )

    args = original.await_args.args
    kwargs = original.await_args.kwargs
    assert args[0] == "nano-banana-pro"
    assert PINTEREST_PROMPT_MARKER in args[1]
    assert kwargs["image_url"] == [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/evidence.jpg",
    ]


@pytest.mark.asyncio
async def test_private_service_recipe_is_redacted_before_persistence() -> None:
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
    contract = build_pinterest_service_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        height_cm=170,
        weight_kg=60,
        confirmed=True,
    )

    with pinterest_service_provider_context(contract):
        await repository.create_generation(
            "session",
            1,
            "nano-banana-pro",
            "image",
            "SECRET PRIVATE SERVICE RECIPE",
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
            base_prompt="SECRET PRIVATE SERVICE RECIPE",
            reference_url="https://example.test/scene.jpg",
            reference_urls=["https://example.test/person.jpg"],
        )
        await repository.update_image_session_last_prompt("session", 5, "SECRET PRIVATE SERVICE RECIPE")

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
    assert generation_call.arguments["prompt"] != "SECRET PRIVATE SERVICE RECIPE"
    assert generation_call.arguments["input_params"]["source"] == "service"
    assert generation_call.arguments["input_params"]["service_id"] == "pinterest"
    assert "trend_id" not in generation_call.arguments["input_params"]
    assert session_call.arguments["base_prompt"] != "SECRET PRIVATE SERVICE RECIPE"
    assert last_prompt_call.arguments["last_prompt"] != "SECRET PRIVATE SERVICE RECIPE"


def test_service_request_requires_two_to_seven_assets_and_measurements() -> None:
    valid = PinterestServiceRunRequest(
        reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
        height_cm=175,
        weight_kg=72,
        confirmed=True,
        idempotency_key="pinterest-run-1234",
    )
    assert len(valid.reference_asset_ids) == 2
    assert PINTEREST_MODEL == "nano-banana-pro"
    assert PINTEREST_QUALITY == "2K"
    assert PINTEREST_SERVICE_ID == "pinterest"

    with pytest.raises(ValidationError):
        PinterestServiceRunRequest(
            reference_asset_ids=["only-one-asset-0001"],
            height_cm=175,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestServiceRunRequest(
            reference_asset_ids=[f"signed-asset-{index:04d}" for index in range(MAX_PINTEREST_REFERENCES + 1)],
            height_cm=175,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestServiceRunRequest(
            reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
            height_cm=119,
            weight_kg=72,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )

    with pytest.raises(ValidationError):
        PinterestServiceRunRequest(
            reference_asset_ids=["signed-scene-asset-0001", "signed-user-asset-0002"],
            height_cm=175,
            weight_kg=251,
            confirmed=True,
            idempotency_key="pinterest-run-1234",
        )


@pytest.mark.asyncio
async def test_service_descriptor_uses_runtime_billing_without_prompt_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import pinterest_service_routes as service_routes

    monkeypatch.setattr(
        service_routes.repo,
        "get_model_cost",
        AsyncMock(return_value=SimpleNamespace(is_active=True, gen_type=GenerationType.image)),
    )
    monkeypatch.setattr(
        service_routes.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(is_active=True, credits=2)),
    )

    payload = await get_pinterest_service(session=SimpleNamespace(), user=SimpleNamespace(id=1))

    assert payload["id"] == "pinterest"
    assert payload["available"] is True
    assert payload["price_credits"] == 2
    assert payload["quality"] == "2K"
    assert "trend_id" not in payload
    assert "prompt_id" not in payload


@pytest.mark.asyncio
async def test_service_run_has_no_prompt_or_trend_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import miniapp_routes
    from api import pinterest_service_routes as service_routes

    monkeypatch.setattr(service_routes, "_validate_runtime", AsyncMock(return_value=None))
    monkeypatch.setattr(service_routes, "_service_price_credits", AsyncMock(return_value=2.0))
    monkeypatch.setattr(service_routes, "_find_idempotent_run", AsyncMock(return_value=None))
    monkeypatch.setattr(service_routes, "_patch_service_snapshot", AsyncMock(return_value=None))

    assets = {
        "scene-asset-0000000001": {"url": "https://example.test/scene.jpg"},
        "user-asset-00000000002": {"url": "https://example.test/user.jpg"},
        "extra-asset-0000000003": {"url": "https://example.test/user-side.jpg"},
    }
    monkeypatch.setattr(
        service_routes,
        "verify_uploaded_asset",
        lambda asset_id, **_kwargs: dict(assets[asset_id]),
    )
    monkeypatch.setattr(service_routes, "_scene_matched_ratio", lambda _url: "3:4")

    captured: dict[str, object] = {}

    class FakeTask:
        id = 777

        def model_dump(self) -> dict[str, object]:
            return {
                "id": self.id,
                "model": "nano-banana-pro",
                "gen_type": "image",
                "status": "pending",
                "credits_spent": 2,
            }

    async def fake_create_image_generation(*, body, session, user, surface):
        captured["body"] = body
        captured["session"] = session
        captured["user"] = user
        captured["surface"] = surface
        captured["contract"] = active_pinterest_service_contract()
        return FakeTask()

    monkeypatch.setattr(miniapp_routes, "create_image_generation", fake_create_image_generation)

    class FakeSession:
        async def refresh(self, _obj) -> None:
            return None

    user = SimpleNamespace(id=9, credits=98)
    body = PinterestServiceRunRequest(
        reference_asset_ids=list(assets),
        height_cm=175,
        weight_kg=72,
        confirmed=True,
        idempotency_key="pinterest-service-run-1234",
    )
    result = await run_pinterest_service(body=body, session=FakeSession(), user=user)

    request_body = captured["body"]
    contract = captured["contract"]
    assert request_body.prompt_id is None
    assert request_body.model == "nano-banana-pro"
    assert request_body.quality == "2K"
    assert request_body.aspect_ratio == "3:4"
    assert request_body.reference_url == "https://example.test/scene.jpg"
    assert request_body.reference_urls == [
        "https://example.test/user.jpg",
        "https://example.test/user-side.jpg",
    ]
    assert contract["source"] == "service"
    assert contract["service_id"] == "pinterest"
    assert contract["service_recipe_version"] == PINTEREST_RECIPE_VERSION
    assert contract["service_price_credits"] == 2.0
    assert "trend_id" not in contract
    assert captured["surface"] == "web"
    assert result["price_credits"] == 2.0


def test_bootstrap_mounts_service_without_pinterest_trend_routes() -> None:
    from api import miniapp_routes, trends_routes

    miniapp_paths = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()) or set())
        for route in miniapp_routes.router.routes
    }
    trend_paths = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()) or set())
        for route in trends_routes.router.routes
    }
    assert "GET" in miniapp_paths["/api/v1/services/pinterest"]
    assert "POST" in miniapp_paths["/api/v1/services/pinterest/upload"]
    assert "POST" in miniapp_paths["/api/v1/services/pinterest/run"]
    assert "/api/v1/trends/{trend_id}/pinterest-run" not in trend_paths
    assert "POST" in trend_paths["/api/v1/trends/{trend_id}/run"]

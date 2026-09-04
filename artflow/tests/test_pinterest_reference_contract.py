from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.pinterest_service_contract import (
    build_pinterest_service_contract,
    install_pinterest_provider_contract,
    pinterest_provider_prompt,
    pinterest_service_provider_context,
)


def test_pinterest_service_contract_keeps_scene_first_order() -> None:
    contract = build_pinterest_service_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=["https://example.test/person-2.jpg"],
    )
    expected_images = [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/person-2.jpg",
    ]
    expected_roles = ["scene", "identity", "identity_evidence"]
    assert contract["source"] == "service"
    assert contract["service_id"] == "pinterest"
    assert "trend_id" not in contract
    assert contract["reference_images"] == expected_images
    assert contract["reference_roles"] == expected_roles
    assert contract["provider_reference_images"] == expected_images
    assert contract["provider_reference_roles"] == expected_roles


def test_pinterest_provider_prompt_is_explicit_about_reference_roles() -> None:
    prompt = pinterest_provider_prompt("Keep the beach lighting and red dress.")
    assert "Image 1 is the only SCENE_REFERENCE" in prompt
    assert "Image 2 is the PRIMARY USER_IDENTITY_REFERENCE" in prompt
    assert "Images 3 and later" in prompt
    assert "USER_IDENTITY_EVIDENCE" in prompt
    assert "Do not preserve the person from Image 1" in prompt
    assert "Do not return Image 1 unchanged" in prompt
    assert "Do not return Image 2 unchanged" in prompt
    assert "Keep the beach lighting and red dress." in prompt


@pytest.mark.asyncio
async def test_provider_wrapper_sends_scene_identity_then_extra_identity_evidence() -> None:
    original = AsyncMock(return_value=SimpleNamespace(task_id="task"))
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
    )

    with pinterest_service_provider_context(contract):
        await service.generate_image(
            "model",
            "hidden prompt",
            image_url=["wrong-order.jpg", "evidence.jpg"],
            aspect_ratio="9:16",
        )

    args = original.await_args.args
    kwargs = original.await_args.kwargs
    assert args[0] == "model"
    assert "SCENE_REFERENCE" in args[1]
    assert "USER_IDENTITY_REFERENCE" in args[1]
    assert "USER_IDENTITY_EVIDENCE" in args[1]
    assert kwargs["image_url"] == [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/evidence.jpg",
    ]


@pytest.mark.asyncio
async def test_provider_wrapper_normalizes_every_pinterest_reference() -> None:
    original = AsyncMock(return_value=SimpleNamespace(task_id="task"))
    normalized: list[str] = []

    def normalize(url: str) -> str:
        normalized.append(url)
        return url.replace(".heic", ".png").replace(".avif", ".png")

    service = SimpleNamespace(
        generate_image=original,
        ensure_provider_safe_png_url=normalize,
        local_upload_path_from_url=lambda _url: None,
    )
    install_pinterest_provider_contract(service)
    contract = build_pinterest_service_contract(
        scene_reference="https://example.test/scene.heic",
        identity_reference="https://example.test/person.avif",
        identity_evidence=["https://example.test/person-2.webp"],
    )

    with pinterest_service_provider_context(contract):
        await service.generate_image("model", "hidden prompt")

    assert normalized == [
        "https://example.test/scene.heic",
        "https://example.test/person.avif",
        "https://example.test/person-2.webp",
    ]
    assert original.await_args.kwargs["image_url"] == [
        "https://example.test/scene.png",
        "https://example.test/person.png",
        "https://example.test/person-2.webp",
    ]

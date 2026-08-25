from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.pinterest_contract import (
    build_pinterest_contract,
    install_pinterest_provider_contract,
    pinterest_provider_context,
    pinterest_provider_prompt,
)


def test_pinterest_contract_keeps_scene_first_product_and_provider_order() -> None:
    contract = build_pinterest_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=["https://example.test/person-2.jpg"],
        trend_id=55,
    )
    expected_images = [
        "https://example.test/scene.jpg",
        "https://example.test/person.jpg",
        "https://example.test/person-2.jpg",
    ]
    expected_roles = ["scene", "identity", "identity_evidence"]
    assert contract["reference_images"] == expected_images
    assert contract["reference_roles"] == expected_roles
    assert contract["provider_reference_images"] == expected_images
    assert contract["provider_reference_roles"] == expected_roles
    assert contract["trend_id"] == 55


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
    service = SimpleNamespace(generate_image=original)
    install_pinterest_provider_contract(service)
    contract = build_pinterest_contract(
        scene_reference="https://example.test/scene.jpg",
        identity_reference="https://example.test/person.jpg",
        identity_evidence=["https://example.test/evidence.jpg"],
        trend_id=55,
    )

    with pinterest_provider_context(contract):
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

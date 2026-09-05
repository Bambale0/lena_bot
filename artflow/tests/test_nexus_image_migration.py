from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import image_service, nexus_image_adapter
from api.image_service import ImageModel
from api.provider_contract_catalog import IMAGE_CONTRACTS
from bot.keyboards.models import IMAGE_CAPS, NANA_BANANO_MODEL_CHOICES, image_nana_banano_kb
from bot.ui.model_labels import model_display_name
from db.seed import DEFAULT_MODEL_COSTS


@pytest.mark.parametrize(
    ("apix_key", "nexus_model"),
    [
        ("nano-banana-pro", "nano-banana-pro"),
        ("nano-banana-2", "nano-banana-2"),
        ("seedream/5-pro-text-to-image", "seedream-5.0-pro"),
        ("seedream/5-pro-image-to-image", "seedream-5.0-pro"),
        ("gpt-image-2-text-to-image", "gpt-image-2"),
        ("gpt-image-2-image-to-image", "gpt-image-2"),
        ("nano-banana-pro-vip", "nano-banana-pro-vip"),
        ("gpt-image-2-vip", "gpt-image-2-vip"),
    ],
)
def test_apix_image_keys_map_to_expected_nexus_models(apix_key: str, nexus_model: str) -> None:
    assert nexus_image_adapter.nexus_model_name(apix_key) == nexus_model
    assert nexus_image_adapter.is_nexus_image_model(apix_key) is True


def test_nano_banana_pro_nexus_payload_preserves_refs_quality_ratio_and_webhook() -> None:
    payload = nexus_image_adapter.build_nexus_image_params(
        model_key="nano-banana-pro",
        prompt="keep the same person",
        image_urls=["https://example.test/person.jpg"],
        aspect_ratio="9:16",
        quality="4K",
        callback_url="https://apix.example/webhook/kie?secret=abc",
    )

    assert payload == {
        "model_name": "nano-banana-pro",
        "prompt": "keep the same person",
        "image_urls": ["https://example.test/person.jpg"],
        "aspect_ratio": "9:16",
        "image_size": "4K",
        "webhook_url": "https://apix.example/webhook/kie?secret=abc&provider=nexus",
    }


def test_seedream_5_pro_nexus_payload_maps_existing_quality_without_ux_change() -> None:
    payload = nexus_image_adapter.build_nexus_image_params(
        model_key="seedream/5-pro-image-to-image",
        prompt="make it cinematic",
        image_urls=["https://example.test/a.jpg", "https://example.test/b.jpg"],
        aspect_ratio="16:9",
        quality="high",
        output_format="png",
    )

    assert payload == {
        "model_name": "seedream-5.0-pro",
        "prompt": "make it cinematic",
        "image_urls": ["https://example.test/a.jpg", "https://example.test/b.jpg"],
        "aspect_ratio": "16:9",
        "resolution": "2K",
        "output_format": "png",
    }


@pytest.mark.parametrize("model_key", ["gpt-image-2-text-to-image", "gpt-image-2-vip"])
def test_gpt2_nexus_payload_omits_quality_field_not_present_in_live_schema(model_key: str) -> None:
    payload = nexus_image_adapter.build_nexus_image_params(
        model_key=model_key,
        prompt="portrait",
        image_urls=["https://example.test/ref.jpg"],
        aspect_ratio="4:3",
        quality="4K",
    )

    assert payload["model_name"] in {"gpt-image-2", "gpt-image-2-vip"}
    assert payload["image_urls"] == ["https://example.test/ref.jpg"]
    assert "quality" not in payload
    assert "resolution" not in payload
    assert "image_size" not in payload


def test_nexus_reference_limits_match_live_contract() -> None:
    cases = {
        "nano-banana-pro": 4,
        "nano-banana-2": 4,
        "seedream/5-pro-image-to-image": 10,
        "gpt-image-2-image-to-image": 4,
        "nano-banana-pro-vip": 14,
        "gpt-image-2-vip": 4,
    }
    for key, max_refs in cases.items():
        refs = [f"https://example.test/{idx}.jpg" for idx in range(max_refs)]
        nexus_image_adapter.build_nexus_image_params(
            model_key=key,
            prompt="use refs",
            image_urls=refs,
            aspect_ratio="1:1",
            quality="2K",
        )
        with pytest.raises(ValueError, match=f"at most {max_refs} reference images"):
            nexus_image_adapter.build_nexus_image_params(
                model_key=key,
                prompt="too many",
                image_urls=refs + ["https://example.test/overflow.jpg"],
                aspect_ratio="1:1",
                quality="2K",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
        ImageModel.NANO_BANANA_PRO,
        ImageModel.NANO_BANANA_2,
        ImageModel.SEEDREAM_5_PRO_T2I,
        ImageModel.SEEDREAM_5_PRO_I2I,
        ImageModel.GPT_IMAGE_2_T2I,
        ImageModel.GPT_IMAGE_2_I2I,
        ImageModel.NANO_BANANA_PRO_VIP,
        ImageModel.GPT_IMAGE_2_VIP,
    ],
)
async def test_generate_image_routes_migrated_models_only_to_nexus(monkeypatch, model: ImageModel) -> None:
    nexus_create = AsyncMock(return_value="nexus:task_123")
    kie_create = AsyncMock(side_effect=AssertionError("migrated model must not call KIE"))
    comet_create = AsyncMock(side_effect=AssertionError("migrated model must not call Comet"))
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", nexus_create)
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie_create)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", comet_create)

    refs = None
    if model in {
        ImageModel.SEEDREAM_5_PRO_I2I,
        ImageModel.GPT_IMAGE_2_I2I,
    }:
        refs = ["https://example.test/ref.jpg"]

    result = await image_service.generate_image(
        model,
        "test prompt",
        image_url=refs,
        aspect_ratio="1:1",
        quality="2K",
        callback_url="https://apix.example/webhook/kie?secret=abc",
    )

    assert result.is_async is True
    assert result.task_id == "nexus:task_123"
    nexus_create.assert_awaited_once()
    kie_create.assert_not_awaited()
    comet_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_image_poller_dispatches_nexus_prefix(monkeypatch) -> None:
    nexus_poll = AsyncMock(return_value=["https://cdn.example/result.png"])
    kie_poll = AsyncMock(side_effect=AssertionError("Nexus task must not be polled through KIE"))
    monkeypatch.setattr(nexus_image_adapter, "poll_nexus_image_result_urls", nexus_poll)
    monkeypatch.setattr(image_service, "poll_kieai_result_urls", kie_poll)

    urls = await image_service.poll_image_result_urls("nexus:abc")

    assert urls == ["https://cdn.example/result.png"]
    nexus_poll.assert_awaited_once_with("nexus:abc")
    kie_poll.assert_not_awaited()


def test_vip_labels_and_minimal_ux_additions_are_exact() -> None:
    assert model_display_name("nano-banana-pro-vip") == "🍌 Нана Банано Про ВИП"
    assert model_display_name("gpt-image-2-vip") == "🤖 ГПТ 2 ВИП"
    assert ImageModel.NANO_BANANA_PRO_VIP.value in NANA_BANANO_MODEL_CHOICES

    markup = image_nana_banano_kb(ImageModel.NANO_BANANA_PRO_VIP.value)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Нана Банано Про ВИП" in labels

    assert IMAGE_CAPS[ImageModel.NANO_BANANA_PRO]["max_refs"] == 4
    assert IMAGE_CAPS[ImageModel.NANO_BANANA_2]["max_refs"] == 4
    assert IMAGE_CAPS[ImageModel.NANO_BANANA_PRO_VIP]["max_refs"] == 14
    assert IMAGE_CAPS[ImageModel.GPT_IMAGE_2_T2I]["max_refs"] == 4
    assert IMAGE_CAPS[ImageModel.GPT_IMAGE_2_VIP]["max_refs"] == 4


def test_vip_bootstrap_prices_are_added_without_repricing_existing_models() -> None:
    rows = {row["model_key"]: row for row in DEFAULT_MODEL_COSTS}
    assert rows["nano-banana-pro"]["credits"] == 2
    assert rows["nano-banana-2"]["credits"] == 1.5
    assert rows["seedream/5-pro-text-to-image"]["credits"] == 5
    assert rows["gpt-image-2-text-to-image"]["credits"] == 4
    assert rows["nano-banana-pro-vip"]["display_name"] == "🍌 Нана Банано Про ВИП"
    assert rows["nano-banana-pro-vip"]["credits"] == 8
    assert rows["gpt-image-2-vip"]["display_name"] == "🤖 ГПТ 2 ВИП"
    assert rows["gpt-image-2-vip"]["credits"] == 5


def test_provider_inventory_marks_all_migrated_image_contracts_as_nexus() -> None:
    by_model = {contract.model: contract for contract in IMAGE_CONTRACTS}
    migrated = {
        "nano-banana-pro",
        "nano-banana-2",
        "seedream/5-pro-text-to-image",
        "seedream/5-pro-image-to-image",
        "gpt-image-2-text-to-image",
        "gpt-image-2-image-to-image",
        "nano-banana-pro-vip",
        "gpt-image-2-vip",
    }
    for key in migrated:
        contract = by_model[key]
        assert contract.provider == "nexus"
        assert "https://nexusapi.dev/openapi.json" in contract.official_docs

@pytest.mark.asyncio
async def test_miniapp_model_catalog_exposes_both_vip_models_with_exact_names(monkeypatch) -> None:
    from api import miniapp_routes

    costs = [
        SimpleNamespace(model_key="nano-banana-pro-vip", display_name="🍌 Нана Банано Про ВИП", credits=8),
        SimpleNamespace(model_key="gpt-image-2-vip", display_name="🤖 ГПТ 2 ВИП", credits=5),
    ]
    monkeypatch.setattr(miniapp_routes.repo, "get_all_model_costs", AsyncMock(return_value=costs))
    monkeypatch.setattr(miniapp_routes, "_resolve_image_quality_prices", AsyncMock(return_value={}))

    payload = await miniapp_routes.list_image_models(AsyncMock(), SimpleNamespace(id=1))
    by_key = {item.key: item for item in payload}

    assert by_key["nano-banana-pro-vip"].display_name == "🍌 Нана Банано Про ВИП"
    assert by_key["nano-banana-pro-vip"].max_refs == 14
    assert by_key["gpt-image-2-vip"].display_name == "🤖 ГПТ 2 ВИП"
    assert by_key["gpt-image-2-vip"].max_refs == 4

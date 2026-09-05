from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api import image_service, public_files
from api.image_service import ImageModel, _build_input
from bot.keyboards.models import HIDDEN_IMAGE_MODELS, IMAGE_CAPS

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


def test_gpt_image_2_text_model_routes_references_to_edit_endpoint() -> None:
    refs = [
        "https://example.test/person.jpg",
        "https://example.test/outfit.png",
    ]

    resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_T2I,
        prompt="Keep the person and use the outfit from reference two",
        image_url=refs,
        aspect_ratio="16:9",
        n=1,
        quality="2K",
    )

    assert resolved_model == ImageModel.GPT_IMAGE_2_I2I.value
    assert payload["input_urls"] == refs
    assert payload["prompt"] == "Keep the person and use the outfit from reference two"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["resolution"] == "2K"
    assert "nsfw_checker" not in payload


def test_gpt_image_2_without_references_keeps_text_endpoint() -> None:
    resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_T2I,
        prompt="A cinematic city at night",
        image_url=None,
        aspect_ratio="9:16",
        n=1,
        quality="2K",
    )

    assert resolved_model == ImageModel.GPT_IMAGE_2_T2I.value
    assert "input_urls" not in payload
    assert payload["aspect_ratio"] == "9:16"
    assert "nsfw_checker" not in payload


def test_gpt_image_2_supports_four_references() -> None:
    refs = [f"https://example.test/ref-{index}.jpg" for index in range(4)]

    resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_T2I,
        prompt="Use all references",
        image_url=refs,
        aspect_ratio="4:3",
        n=1,
        quality="2K",
    )

    assert resolved_model == ImageModel.GPT_IMAGE_2_I2I.value
    assert payload["input_urls"] == refs


def test_gpt_image_2_rejects_more_than_four_references() -> None:
    refs = [f"https://example.test/ref-{index}.jpg" for index in range(5)]

    with pytest.raises(ValueError, match="at most 4 reference images"):
        _build_input(
            ImageModel.GPT_IMAGE_2_T2I,
            prompt="Use all references",
            image_url=refs,
            aspect_ratio="4:3",
            n=1,
            quality="2K",
        )


def test_gpt_image_2_capabilities_are_unified_for_all_surfaces() -> None:
    text_caps = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_T2I]
    edit_caps = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_I2I]

    assert text_caps["modes"] == ["text", "image"]
    assert text_caps["aspect_ratio_modes"] == ["text", "image"]
    assert text_caps["max_refs"] == 4
    assert edit_caps["max_refs"] == 4
    assert text_caps["quality_options"] == [
        ("2K", "🔷 2K (стандарт)"),
        ("4K", "💎 4K (высокое)"),
        ("1K", "⚡ 1K (быстро)"),
    ]
    assert image_service.MODEL_ASPECT_RATIOS[ImageModel.GPT_IMAGE_2_T2I] == [
        "auto",
        "1:1",
        "3:2",
        "2:3",
        "4:3",
        "3:4",
        "16:9",
        "9:16",
        "2:1",
        "1:2",
        "21:9",
    ]
    assert image_service.normalize_quality_for_aspect_ratio(
        ImageModel.GPT_IMAGE_2_T2I,
        "1:1",
        "4K",
    ) == "4K"
    assert ImageModel.GPT_IMAGE_2_I2I in HIDDEN_IMAGE_MODELS


@pytest.mark.asyncio
async def test_gpt_image_2_routes_references_to_nexus_without_kie_upload(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(JPEG)
    second.write_bytes(JPEG + b"second")

    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "WEBHOOK_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "WEB_PUBLIC_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    calls: list[dict] = []

    async def fake_create_nexus_image_task(**kwargs):
        calls.append(kwargs)
        return "nexus:task_gpt_image_2"

    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", fake_create_nexus_image_task)
    monkeypatch.setattr(
        image_service.kieai_client,
        "upload_file_stream",
        AsyncMock(side_effect=AssertionError("GPT Image 2 refs must not be uploaded to KIE")),
    )
    monkeypatch.setattr(
        image_service.kieai_client,
        "create_task",
        AsyncMock(side_effect=AssertionError("GPT Image 2 must not create a KIE task")),
    )
    monkeypatch.setattr(
        image_service.comet_fallback,
        "generate_image",
        AsyncMock(side_effect=AssertionError("GPT Image 2 must not use Comet")),
    )

    refs = [
        "https://example.test/static/upload/first.jpg",
        "https://example.test/static/upload/second.jpg",
    ]
    result = await image_service.generate_image(
        ImageModel.GPT_IMAGE_2_T2I,
        "Combine both references",
        image_url=refs,
        aspect_ratio="16:9",
        quality="2K",
        callback_url="https://example.test/webhook/kie?secret=abc",
    )

    assert result.is_async is True
    assert result.task_id == "nexus:task_gpt_image_2"
    assert calls == [
        {
            "model_key": ImageModel.GPT_IMAGE_2_T2I.value,
            "prompt": "Combine both references",
            "image_urls": refs,
            "aspect_ratio": "16:9",
            "quality": "2K",
            "callback_url": "https://example.test/webhook/kie?secret=abc",
            "output_format": None,
        }
    ]


@pytest.mark.asyncio
async def test_gpt_image_2_nexus_failure_never_uses_old_providers(monkeypatch) -> None:
    async def fail_nexus(**_kwargs):
        raise RuntimeError("nexus unavailable")

    kie_create = AsyncMock()
    comet_create = AsyncMock()
    monkeypatch.setattr(image_service.nexus_image_adapter, "create_nexus_image_task", fail_nexus)
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie_create)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", comet_create)

    with pytest.raises(RuntimeError, match="nexus unavailable"):
        await image_service.generate_image(
            ImageModel.GPT_IMAGE_2_T2I,
            "Edit the portrait",
            image_url="https://cdn.example.test/reference.jpg",
            aspect_ratio="1:1",
            quality="2K",
        )

    kie_create.assert_not_awaited()
    comet_create.assert_not_awaited()

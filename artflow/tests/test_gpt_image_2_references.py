from __future__ import annotations

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


def test_gpt_image_2_supports_sixteen_references() -> None:
    refs = [f"https://example.test/ref-{index}.jpg" for index in range(16)]

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


def test_gpt_image_2_rejects_more_than_sixteen_references() -> None:
    refs = [f"https://example.test/ref-{index}.jpg" for index in range(17)]

    with pytest.raises(ValueError, match="at most 16 reference images"):
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
    assert text_caps["max_refs"] == 16
    assert edit_caps["max_refs"] == 16
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
async def test_gpt_image_2_uploads_local_references_before_create_task(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(JPEG)
    second.write_bytes(JPEG + b"second")

    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "WEBHOOK_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "WEB_PUBLIC_URL", "https://example.test")
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    uploaded: list[str] = []
    created: list[dict] = []

    async def fake_upload_file_stream(
        data: bytes,
        *,
        filename: str,
        content_type: str,
        upload_path: str = "images/apix-refs",
    ) -> str:
        assert data
        assert content_type == "image/jpeg"
        uploaded.append(filename)
        return f"https://kie-files.test/{filename}"

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        created.append(payload)
        return {"code": 200, "data": {"taskId": "task_gpt_image_2"}}

    async def forbidden_comet_fallback(**_kwargs):
        raise AssertionError("GPT Image 2 must not use generic Comet fallback")

    monkeypatch.setattr(image_service.kieai_client, "upload_file_stream", fake_upload_file_stream)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", forbidden_comet_fallback)

    result = await image_service.generate_image(
        ImageModel.GPT_IMAGE_2_T2I,
        "Combine both references",
        image_url=[
            "https://example.test/static/upload/first.jpg",
            "https://example.test/static/upload/second.jpg",
        ],
        aspect_ratio="16:9",
        quality="2K",
    )

    assert result.is_async is True
    assert result.task_id == "task_gpt_image_2"
    assert uploaded == ["first.jpg", "second.jpg"]
    assert created == [
        {
            "model": ImageModel.GPT_IMAGE_2_I2I.value,
            "input": {
                "prompt": "Combine both references",
                "aspect_ratio": "16:9",
                "resolution": "2K",
                "input_urls": [
                    "https://kie-files.test/first.jpg",
                    "https://kie-files.test/second.jpg",
                ],
            },
        }
    ]


@pytest.mark.asyncio
async def test_gpt_image_2_provider_failure_never_substitutes_seedream(monkeypatch) -> None:
    comet_called = False

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        assert payload["model"] == ImageModel.GPT_IMAGE_2_I2I.value
        return {"code": 500, "msg": "provider unavailable", "data": None}

    async def fake_comet_fallback(**_kwargs):
        nonlocal comet_called
        comet_called = True
        raise AssertionError("generic fallback must be disabled")

    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", fake_comet_fallback)

    with pytest.raises(RuntimeError, match="fallback disabled to prevent model substitution"):
        await image_service.generate_image(
            ImageModel.GPT_IMAGE_2_T2I,
            "Edit the portrait",
            image_url="https://cdn.example.test/reference.jpg",
            aspect_ratio="1:1",
            quality="2K",
        )

    assert comet_called is False

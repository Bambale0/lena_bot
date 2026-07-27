from __future__ import annotations

import pytest

from api import image_service, public_files
from api.image_service import ImageModel, _build_input

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


def test_qwen_text_to_image_emits_full_official_payload() -> None:
    model, payload = _build_input(
        ImageModel.QWEN_T2I,
        "A photorealistic astronaut",
        None,
        "16:9",
        1,
        "basic",
        negative_prompt="blurry, ugly",
        num_inference_steps=36,
        guidance_scale=3.5,
        acceleration="none",
        enable_safety_checker=False,
        output_format="png",
    )

    assert model == "qwen/text-to-image"
    assert payload == {
        "prompt": "A photorealistic astronaut",
        "image_size": "landscape_16_9",
        "num_inference_steps": 36,
        "guidance_scale": 3.5,
        "enable_safety_checker": False,
        "output_format": "png",
        "negative_prompt": "blurry, ugly",
        "acceleration": "none",
    }
    assert "nsfw_checker" not in payload


def test_qwen_image_to_image_emits_strength_and_no_fake_size() -> None:
    model, payload = _build_input(
        ImageModel.QWEN_I2I,
        "Restyle the portrait",
        "https://example.test/ref.png",
        None,
        1,
        "basic",
        strength=0.65,
        negative_prompt="artifact",
        num_inference_steps=30,
        guidance_scale=2.5,
        enable_safety_checker=True,
    )

    assert model == "qwen/image-to-image"
    assert payload["image_url"] == "https://example.test/ref.png"
    assert payload["strength"] == 0.65
    assert payload["negative_prompt"] == "artifact"
    assert "image_size" not in payload
    assert "nsfw_checker" not in payload


def test_qwen_image_edit_emits_sync_mode_and_official_checker() -> None:
    model, payload = _build_input(
        ImageModel.QWEN_EDIT,
        "Replace the sky",
        "https://example.test/ref.png",
        "4:3",
        1,
        "basic",
        sync_mode=True,
        acceleration="none",
        num_inference_steps=25,
        guidance_scale=4,
        enable_safety_checker=False,
        output_format="webp",
    )

    assert model == "qwen/image-edit"
    assert payload["image_url"] == "https://example.test/ref.png"
    assert payload["image_size"] == "landscape_4_3"
    assert payload["sync_mode"] is True
    assert payload["enable_safety_checker"] is False
    assert payload["output_format"] == "webp"


def test_qwen2_text_and_edit_emit_seed_and_output_format() -> None:
    text_model, text_payload = _build_input(
        ImageModel.QWEN2_T2I,
        "A clean product render",
        None,
        "3:2",
        1,
        "basic",
        seed=42,
        output_format="jpeg",
    )
    edit_model, edit_payload = _build_input(
        ImageModel.QWEN2_EDIT,
        "Change the label",
        "https://example.test/ref.png",
        "9:16",
        1,
        "basic",
        seed=7,
        output_format="png",
    )

    assert text_model == "qwen2/text-to-image"
    assert text_payload == {
        "prompt": "A clean product render",
        "image_size": "3:2",
        "seed": 42,
        "output_format": "jpeg",
    }
    assert edit_model == "qwen2/image-edit"
    assert edit_payload["image_url"] == "https://example.test/ref.png"
    assert edit_payload["image_size"] == "9:16"
    assert edit_payload["seed"] == 7


def test_grok_payloads_contain_only_documented_fields() -> None:
    _, text_payload = _build_input(
        ImageModel.GROK_T2I,
        "A cinematic portrait",
        None,
        "3:2",
        1,
        "basic",
    )
    _, edit_payload = _build_input(
        ImageModel.GROK_I2I,
        "Recreate the composition",
        "https://example.test/ref.webp",
        None,
        1,
        "basic",
    )

    assert text_payload == {
        "prompt": "A cinematic portrait",
        "aspect_ratio": "3:2",
    }
    assert edit_payload == {
        "prompt": "Recreate the composition",
        "image_urls": ["https://example.test/ref.webp"],
        "image_url": "https://example.test/ref.webp",
    }


def test_grok_accepts_multiple_reference_images() -> None:
    _, payload = _build_input(
        ImageModel.GROK_I2I,
        "Edit",
        ["https://example.test/a.png", "https://example.test/b.png"],
        None,
        1,
        "basic",
    )

    assert payload["image_urls"] == [
        "https://example.test/a.png",
        "https://example.test/b.png",
    ]
    assert payload["image_url"] == "https://example.test/a.png"


def test_wan_image_emits_all_official_controls() -> None:
    model, payload = _build_input(
        ImageModel.WAN_27_PRO,
        "Replace the marked object",
        ["https://example.test/ref.png"],
        None,
        4,
        "2K",
        seed=123,
        enable_sequential=False,
        thinking_mode=True,
        watermark=True,
        bbox_list=[[[10, 20, 100, 200]]],
    )

    assert model == "wan/2-7-image-pro"
    assert payload == {
        "prompt": "Replace the marked object",
        "n": 4,
        "enable_sequential": False,
        "resolution": "2K",
        "thinking_mode": True,
        "watermark": True,
        "seed": 123,
        "bbox_list": [[[10, 20, 100, 200]]],
        "input_urls": ["https://example.test/ref.png"],
    }
    assert "nsfw_checker" not in payload


def test_wan_rejects_4k_with_reference() -> None:
    with pytest.raises(ValueError, match="4K is unavailable"):
        _build_input(
            ImageModel.WAN_27_PRO,
            "Edit",
            "https://example.test/ref.png",
            None,
            1,
            "4K",
        )


@pytest.mark.asyncio
async def test_grok_local_reference_is_uploaded_to_kie(tmp_path, monkeypatch) -> None:
    ref = tmp_path / "grok-ref.jpg"
    ref.write_bytes(JPEG)
    uploaded: list[str] = []
    created: list[dict] = []

    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    async def fake_upload(
        data: bytes,
        *,
        filename: str,
        content_type: str,
        upload_path: str,
    ) -> str:
        uploaded.append(filename)
        return f"https://kie-files.test/{filename}"

    async def fake_create(payload: dict, callback_url: str | None = None) -> dict:
        created.append(payload)
        return {"code": 200, "data": {"taskId": "grok_task"}}

    monkeypatch.setattr(image_service.kieai_client, "upload_file_stream", fake_upload)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create)

    result = await image_service.generate_image(
        ImageModel.GROK_I2I,
        "Recreate this image",
        image_url="https://example.test/static/upload/grok-ref.jpg",
    )

    assert result.task_id == "grok_task"
    assert uploaded == ["grok-ref.jpg"]
    assert created[0]["input"]["image_urls"] == ["https://kie-files.test/grok-ref.jpg"]


@pytest.mark.asyncio
async def test_kie_image_failure_never_substitutes_seedream(monkeypatch) -> None:
    comet_called = False

    async def fail_kie(payload: dict, callback_url: str | None = None) -> dict:
        raise RuntimeError("provider unavailable")

    async def forbidden_comet(**_kwargs):
        nonlocal comet_called
        comet_called = True
        raise AssertionError("cross-model fallback must not run")

    monkeypatch.setattr(image_service.kieai_client, "create_task", fail_kie)
    monkeypatch.setattr(image_service.comet_fallback, "generate_image", forbidden_comet)

    with pytest.raises(RuntimeError, match="cross-model fallback is disabled"):
        await image_service.generate_image(
            ImageModel.QWEN_T2I,
            "A product photo",
            aspect_ratio="1:1",
        )

    assert comet_called is False

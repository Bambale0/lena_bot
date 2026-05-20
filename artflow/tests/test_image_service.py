from __future__ import annotations

import pytest

from api import public_files
from api import image_service
from api.image_service import ImageModel, _build_input, normalize_quality_for_aspect_ratio


JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"


def test_normalize_quality_for_aspect_ratio_downgrades_square_4k() -> None:
    assert normalize_quality_for_aspect_ratio(ImageModel.GPT_IMAGE_2_I2I, "1:1", "4K") == "2K"
    assert normalize_quality_for_aspect_ratio("nano-banana-pro", "1:1", "4K") == "2K"


def test_normalize_quality_for_aspect_ratio_keeps_supported_combo() -> None:
    assert normalize_quality_for_aspect_ratio(ImageModel.GPT_IMAGE_2_I2I, "16:9", "4K") == "4K"
    assert normalize_quality_for_aspect_ratio(ImageModel.SEEDREAM_45, "1:1", "high") == "high"


def test_build_input_uses_2k_for_square_4k_request() -> None:
    _resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_T2I,
        prompt="portrait",
        image_url=None,
        aspect_ratio="1:1",
        n=1,
        quality="4K",
    )

    assert payload["resolution"] == "2K"


def test_build_input_omits_gpt_image_2_auto_aspect_ratio() -> None:
    _resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_I2I,
        prompt="edit this image",
        image_url="https://example.test/ref.jpg",
        aspect_ratio="auto",
        n=1,
        quality="2K",
    )

    assert payload["resolution"] == "2K"
    assert "aspect_ratio" not in payload


@pytest.mark.asyncio
async def test_poll_kieai_result_urls_returns_all_urls(monkeypatch) -> None:
    async def fake_get_task_status(_task_id: str) -> dict:
        return {
            "data": {
                "state": "success",
                "resultJson": '{"resultUrls":["https://example.test/1.png","https://example.test/2.png"]}',
            }
        }

    monkeypatch.setattr(image_service.kieai_client, "get_task_status", fake_get_task_status)

    assert await image_service.poll_kieai_result_urls("task_1") == [
        "https://example.test/1.png",
        "https://example.test/2.png",
    ]
    assert await image_service.poll_kieai_status("task_1") == "https://example.test/1.png"


@pytest.mark.asyncio
async def test_generate_image_uploads_local_seedream_reference_before_create_task(tmp_path, monkeypatch) -> None:
    ref = tmp_path / "ref.jpg"
    ref.write_bytes(JPEG)
    uploaded_urls: list[str] = []
    created_payloads: list[dict] = []

    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    async def fake_upload_file_stream(data: bytes, *, filename: str, content_type: str, upload_path: str = "images/apix-refs") -> str:
        assert data == JPEG
        assert filename == "ref.jpg"
        assert content_type == "image/jpeg"
        assert upload_path == "images/apix-refs"
        uploaded_urls.append(filename)
        return "https://kie-files.test/ref.jpg"

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        created_payloads.append(payload)
        return {"code": 200, "data": {"taskId": "task_seedream"}}

    monkeypatch.setattr(image_service.kieai_client, "upload_file_stream", fake_upload_file_stream)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)

    result = await image_service.generate_image(
        ImageModel.SEEDREAM_45_EDIT,
        "edit this",
        image_url="https://example.test/static/upload/ref.jpg",
        aspect_ratio="1:1",
    )

    assert result.task_id == "task_seedream"
    assert uploaded_urls == ["ref.jpg"]
    assert created_payloads[0]["model"] == "seedream/4.5-edit"
    assert created_payloads[0]["input"]["image_urls"] == ["https://kie-files.test/ref.jpg"]


@pytest.mark.asyncio
async def test_generate_image_uploads_local_qwen_reference_before_create_task(tmp_path, monkeypatch) -> None:
    ref = tmp_path / "qwen-ref.jpg"
    ref.write_bytes(JPEG)
    created_payloads: list[dict] = []

    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(public_files.settings, "STATIC_UPLOAD_URL_PATH", "/static/upload")

    async def fake_upload_file_stream(data: bytes, *, filename: str, content_type: str, upload_path: str = "images/apix-refs") -> str:
        assert data == JPEG
        assert filename == "qwen-ref.jpg"
        assert content_type == "image/jpeg"
        return "https://kie-files.test/qwen-ref.jpg"

    async def fake_create_task(payload: dict, callback_url: str | None = None) -> dict:
        created_payloads.append(payload)
        return {"code": 200, "data": {"taskId": "task_qwen"}}

    monkeypatch.setattr(image_service.kieai_client, "upload_file_stream", fake_upload_file_stream)
    monkeypatch.setattr(image_service.kieai_client, "create_task", fake_create_task)

    result = await image_service.generate_image(
        ImageModel.QWEN_I2I,
        "restyle",
        image_url="https://example.test/static/upload/qwen-ref.jpg",
        aspect_ratio="1:1",
    )

    assert result.task_id == "task_qwen"
    assert created_payloads[0]["model"] == "qwen/image-to-image"
    assert created_payloads[0]["input"]["image_url"] == "https://kie-files.test/qwen-ref.jpg"

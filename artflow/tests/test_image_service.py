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


@pytest.mark.parametrize(
    "model",
    [ImageModel.QWEN_I2I, ImageModel.QWEN_EDIT, ImageModel.QWEN2_EDIT],
)
def test_build_input_qwen_reference_models_send_user_prompt_first(model: ImageModel) -> None:
    user_prompt = "сменить цвет волос на пастельно розовый"
    _resolved_model, payload = _build_input(
        model,
        prompt=user_prompt,
        image_url="https://example.test/ref.jpg",
        aspect_ratio="1:1",
        n=1,
        quality="basic",
    )

    assert payload["prompt"].startswith(user_prompt)
    assert "PROMPT-DIRECTED REFERENCE EDITING" in payload["prompt"]


def test_build_input_qwen_edit_does_not_truncate_user_prompt_behind_reference_lock() -> None:
    user_prompt = "сменить цвет волос на пастельно розовый"
    _resolved_model, payload = _build_input(
        ImageModel.QWEN_EDIT,
        prompt=user_prompt,
        image_url="https://example.test/ref.jpg",
        aspect_ratio="1:1",
        n=1,
        quality="basic",
    )

    assert len(payload["prompt"]) <= 2000
    assert user_prompt in payload["prompt"]


def test_build_input_wan_multiref_keeps_first_reference_as_identity_source() -> None:
    user_prompt = "надеть белье со второго референса"
    _resolved_model, payload = _build_input(
        ImageModel.WAN_27_PRO,
        prompt=user_prompt,
        image_url=[
            "https://example.test/face.jpg",
            "https://example.test/lingerie.jpg",
        ],
        aspect_ratio=None,
        n=1,
        quality="2K",
    )

    assert payload["input_urls"] == [
        "https://example.test/face.jpg",
        "https://example.test/lingerie.jpg",
    ]
    assert payload["prompt"].startswith("MULTI-REFERENCE IDENTITY AND DETAIL CONTROL")
    assert "Use the first reference image as the primary identity source" in payload["prompt"]
    assert "transfer only the garment design" in payload["prompt"]
    assert user_prompt in payload["prompt"]


def test_build_input_wan_reference_does_not_lock_old_background() -> None:
    user_prompt = "я в белом платье на пляже на закате, фон полностью пляж и море"
    _resolved_model, payload = _build_input(
        ImageModel.WAN_27_PRO,
        prompt=user_prompt,
        image_url="https://example.test/tarot-books-room.jpg",
        aspect_ratio=None,
        n=1,
        quality="2K",
    )

    assert payload["prompt"].startswith("REFERENCE IDENTITY PRESERVATION WITH TRANSFORMATION")
    assert "replace the reference background completely" in payload["prompt"]
    assert "do not carry over reference background artifacts" in payload["prompt"]
    assert user_prompt in payload["prompt"]


def test_build_input_nano_banana_reference_prioritizes_requested_beauty_edits() -> None:
    user_prompt = (
        "гламурный beauty portrait, ровная сияющая кожа с ретушью, макияж, "
        "длинные объемные волнистые волосы до пояса, голова наклонена вбок"
    )
    _resolved_model, payload = _build_input(
        ImageModel.NANO_BANANA_PRO,
        prompt=user_prompt,
        image_url="https://example.test/ref.jpg",
        aspect_ratio="9:16",
        n=1,
        quality="2K",
    )

    assert payload["prompt"].startswith("PROMPT-DIRECTED REFERENCE TRANSFORMATION")
    assert "not to freeze the whole source photo" in payload["prompt"]
    assert "glowing retouched skin" in payload["prompt"]
    assert "long voluminous hair" in payload["prompt"]
    assert "head tilted to the side" in payload["prompt"]
    assert "Do not make the face prettier" not in payload["prompt"]
    assert user_prompt in payload["prompt"]


def test_build_input_does_not_duplicate_prompt_directed_reference_prefix() -> None:
    prompt = (
        "PROMPT-DIRECTED REFERENCE TRANSFORMATION. HIGHEST PRIORITY.\n\n"
        "use the same person, but change the hairstyle"
    )
    _resolved_model, payload = _build_input(
        ImageModel.NANO_BANANA_PRO,
        prompt=prompt,
        image_url="https://example.test/ref.jpg",
        aspect_ratio="9:16",
        n=1,
        quality="2K",
    )

    assert payload["prompt"].count("PROMPT-DIRECTED REFERENCE TRANSFORMATION") == 1


def test_build_input_seedream_reference_uses_scene_replacement_rules() -> None:
    user_prompt = "cinematic portrait in a clean glass studio, no old interior"
    _resolved_model, payload = _build_input(
        ImageModel.SEEDREAM_45_EDIT,
        prompt=user_prompt,
        image_url="https://example.test/old-room.jpg",
        aspect_ratio="1:1",
        n=1,
        quality="high",
    )

    assert payload["image_urls"] == ["https://example.test/old-room.jpg"]
    assert "use the reference background only when the prompt explicitly asks" in payload["prompt"]
    assert "prioritize the requested scene and composition" in payload["prompt"]
    assert user_prompt in payload["prompt"]


def test_build_input_seedream_uses_current_prompt_limit() -> None:
    user_prompt = "x" * 2600
    _resolved_model, payload = _build_input(
        ImageModel.SEEDREAM_45_EDIT,
        prompt=user_prompt,
        image_url="https://example.test/ref.jpg",
        aspect_ratio="1:1",
        n=1,
        quality="basic",
    )

    assert len(payload["prompt"]) <= 3000
    assert len(payload["prompt"]) > 2000


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

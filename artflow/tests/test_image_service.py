from __future__ import annotations

import pytest

from api import image_service
from api.image_service import ImageModel, _build_input, normalize_quality_for_aspect_ratio


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

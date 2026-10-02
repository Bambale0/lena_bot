from __future__ import annotations

import pytest
from PIL import Image

from api import public_files, video_service
from api.video_service import VideoModel


def test_ensure_video_reference_aspect_url_fits_extreme_local_upload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    source_path = tmp_path / "wide.jpg"
    Image.new("RGB", (600, 120), "white").save(source_path)

    source_url = public_files.public_upload_url(source_path.name)
    fitted_url = public_files.ensure_video_reference_aspect_url(source_url)

    assert fitted_url and fitted_url != source_url
    fitted_path = public_files.local_upload_path_from_url(fitted_url)
    assert fitted_path and fitted_path.exists()
    with Image.open(fitted_path) as image:
        ratio = image.width / image.height
    assert ratio <= 2.5


@pytest.mark.asyncio
async def test_veo_compat_generate_rejects_empty_task_id(monkeypatch) -> None:
    async def fake_create_veo_task(payload):
        return {"code": 500, "msg": "Server Error", "data": None}

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", fake_create_veo_task)

    with pytest.raises(RuntimeError, match="Veo3 createTask failed"):
        await video_service._veo_generate(VideoModel.VEO_3_FAST, "cat", None, "16:9")


@pytest.mark.asyncio
async def test_veo_poll_status_handles_null_data_as_pending(monkeypatch) -> None:
    async def fake_get_veo_status(task_id):
        return {"code": 200, "msg": "success", "data": None}

    monkeypatch.setattr(video_service.kieai_client, "get_veo_status", fake_get_veo_status)

    assert await video_service.poll_veo_status("veo_task_1") is None


@pytest.mark.asyncio
async def test_veo_poll_status_reads_nested_response_result_urls(monkeypatch) -> None:
    async def fake_get_veo_status(task_id):
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "taskId": task_id,
                "successFlag": 1,
                "response": {
                    "resultUrls": ["https://cdn.example.test/video.mp4"],
                },
            },
        }

    monkeypatch.setattr(video_service.kieai_client, "get_veo_status", fake_get_veo_status)

    assert await video_service.poll_veo_status("veo_task_1") == "https://cdn.example.test/video.mp4"


@pytest.mark.asyncio
async def test_veo_poll_status_treats_flags_2_and_3_as_failure(monkeypatch) -> None:
    async def fake_get_veo_status(task_id):
        return {
            "code": 200,
            "msg": "success",
            "data": {"successFlag": 3, "errorMessage": "upstream rejected prompt"},
        }

    monkeypatch.setattr(video_service.kieai_client, "get_veo_status", fake_get_veo_status)

    with pytest.raises(RuntimeError, match="upstream rejected prompt"):
        await video_service.poll_veo_status("veo_task_1")


@pytest.mark.asyncio
async def test_generate_video_prepares_reference_urls_before_neironych_payload(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_ensure(url: str | None) -> str | None:
        return f"{url}?fit=video" if url else url

    async def fake_generate_product_video(**kwargs) -> str:
        calls.append(kwargs)
        return "task_1"

    monkeypatch.setattr(video_service, "ensure_video_reference_aspect_url", fake_ensure)
    monkeypatch.setattr(
        video_service.neironych_seedance_runtime,
        "generate_product_video",
        fake_generate_product_video,
    )

    result = await video_service.generate_video(
        VideoModel.SEEDANCE_2,
        "animate",
        image_url=["https://example.test/ref-a.jpg", "https://example.test/ref-b.jpg"],
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
    )

    assert result.task_id == "task_1"
    assert result.provider == "neironych"
    assert calls[0]["image_urls"] == [
        "https://example.test/ref-a.jpg?fit=video",
        "https://example.test/ref-b.jpg?fit=video",
    ]


@pytest.mark.asyncio
async def test_generate_video_does_not_cross_model_fallback_on_neironych_error(monkeypatch) -> None:
    async def fail_neironych(**kwargs):
        raise RuntimeError("Neironych Seedance validation failed: invalid image ratio")

    async def fail_comet(**kwargs):
        raise AssertionError("Comet fallback should not run for exact-model provider errors")

    monkeypatch.setattr(
        video_service.neironych_seedance_runtime,
        "generate_product_video",
        fail_neironych,
    )
    monkeypatch.setattr(video_service.comet_fallback, "generate_video", fail_comet)

    with pytest.raises(RuntimeError, match="invalid image ratio"):
        await video_service.generate_video(
            VideoModel.SEEDANCE_2,
            "animate",
            image_url="https://example.test/ref.jpg",
            duration=5,
            aspect_ratio="16:9",
            resolution="720p",
        )


def test_ensure_video_reference_aspect_url_can_upscale_provider_small_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(public_files, "UPLOAD_ROOT", tmp_path)
    source_path = tmp_path / "small.jpg"
    Image.new("RGB", (256, 600), "white").save(source_path, format="JPEG")
    source_url = public_files.public_upload_url(source_path.name)

    fitted_url = public_files.ensure_video_reference_aspect_url(
        source_url,
        min_width=300,
        min_pixels=407_696,
    )

    fitted_path = public_files.local_upload_path_from_url(fitted_url)
    assert fitted_path is not None
    with Image.open(fitted_path) as image:
        assert image.width >= 300
        assert image.width * image.height >= 407_696
        assert image.width / image.height >= 0.4


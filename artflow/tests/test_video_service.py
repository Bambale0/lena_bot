from __future__ import annotations

import pytest

from api import video_service
from api.video_service import VideoModel


@pytest.mark.asyncio
async def test_veo_generate_rejects_empty_task_id(monkeypatch) -> None:
    async def fake_create_veo_task(payload):
        return {"code": 500, "msg": "Server Error", "data": None}

    monkeypatch.setattr(video_service.kieai_client, "create_veo_task", fake_create_veo_task)

    with pytest.raises(RuntimeError, match="Veo3 createTask failed"):
        await video_service.generate_video(VideoModel.VEO_3_FAST, "cat", aspect_ratio="16:9")


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

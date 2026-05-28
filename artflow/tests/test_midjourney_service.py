from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from api import midjourney_service


def test_task_result_from_dict_ignores_null_buttons() -> None:
    result = midjourney_service.MJTaskResult.from_dict({
        "id": "task_blend_ok",
        "status": "SUCCESS",
        "imageUrl": "https://example.test/result.jpg",
        "buttons": None,
    })

    assert result.task_id == "task_blend_ok"
    assert result.is_success is True
    assert result.image_url == "https://example.test/result.jpg"
    assert result.buttons == []


def test_task_result_from_dict_reads_video_and_image_url_lists() -> None:
    result = midjourney_service.MJTaskResult.from_dict({
        "id": "task_video_ok",
        "status": "SUCCESS",
        "image_urls": ["https://example.test/preview.jpg"],
        "video_urls": ["https://example.test/video.mp4"],
    })

    assert result.image_urls == ["https://example.test/preview.jpg"]
    assert result.video_urls == ["https://example.test/video.mp4"]


def test_task_result_from_dict_reads_describe_prompt_fallbacks() -> None:
    result = midjourney_service.MJTaskResult.from_dict({
        "id": "task_describe_ok",
        "status": "SUCCESS",
        "prompt": "",
        "promptEn": "clean geometric icon prompt",
        "properties": {"finalPrompt": "fallback prompt"},
    })

    assert result.prompt == "clean geometric icon prompt"


@pytest.mark.asyncio
async def test_imagine_includes_notify_hook(monkeypatch) -> None:
    post_mock = AsyncMock(return_value={"result": "task_with_hook"})
    monkeypatch.setattr(midjourney_service.comet_client, "post", post_mock)

    task_id = await midjourney_service.imagine("cat portrait")

    assert task_id == "task_with_hook"
    payload = post_mock.await_args.args[1]
    assert payload["notifyHook"] == "https://example.test/webhook/comet/midjourney?secret=test-secret"


@pytest.mark.asyncio
async def test_imagine_retries_without_base64_on_client_error(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.cometapi.com/mj/submit/imagine")
    response = httpx.Response(422, request=request)
    post_mock = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("unprocessable", request=request, response=response),
            {"result": "task_retry_ok"},
        ]
    )
    monkeypatch.setattr(midjourney_service.comet_client, "post", post_mock)

    task_id = await midjourney_service.imagine(
        "https://example.test/ref.jpg cat portrait",
        base64_array=["data:image/jpeg;base64,abc"],
        reference_url="https://example.test/ref.jpg",
    )

    assert task_id == "task_retry_ok"
    assert post_mock.await_count == 2
    first_payload = post_mock.await_args_list[0].args[1]
    second_payload = post_mock.await_args_list[1].args[1]
    assert first_payload["base64Array"] == ["data:image/jpeg;base64,abc"]
    assert "base64Array" not in second_payload


@pytest.mark.asyncio
async def test_imagine_does_not_retry_without_reference_url(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.cometapi.com/mj/submit/imagine")
    response = httpx.Response(400, request=request)
    post_mock = AsyncMock(
        side_effect=httpx.HTTPStatusError("bad request", request=request, response=response)
    )
    monkeypatch.setattr(midjourney_service.comet_client, "post", post_mock)

    with pytest.raises(httpx.HTTPStatusError):
        await midjourney_service.imagine(
            "cat portrait",
            base64_array=["data:image/jpeg;base64,abc"],
            reference_url=None,
        )

    assert post_mock.await_count == 1


@pytest.mark.asyncio
async def test_poll_mj_video_prefers_video_urls(monkeypatch) -> None:
    get_mock = AsyncMock(return_value={
        "id": "task_vid",
        "status": "SUCCESS",
        "imageUrl": "https://example.test/poster.jpg",
        "video_urls": ["https://example.test/video.mp4"],
        "videoUrl": "",
    })
    monkeypatch.setattr(midjourney_service.comet_client, "get", get_mock)

    result = await midjourney_service.poll_mj_video("task_vid")

    assert result == "https://example.test/video.mp4"

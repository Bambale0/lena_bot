from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api import neironych_seedance_runtime, seedance25_adapter, video_service
from api.video_runtime_fixes import install_video_runtime_fixes


def test_fallback_task_id_round_trip() -> None:
    encoded = neironych_seedance_runtime.encode_task_id("req-123")
    assert encoded == "neironych:req-123"
    assert neironych_seedance_runtime.is_task_id(encoded) is True
    assert neironych_seedance_runtime.decode_task_id(encoded) == "req-123"


@pytest.mark.asyncio
async def test_seedance2_uses_kie_primary_and_does_not_call_fallback(monkeypatch) -> None:
    primary = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-123"}})
    fallback = AsyncMock(return_value="neur-should-not-run")
    monkeypatch.setattr(video_service.kieai_client, "create_task", primary)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", fallback)

    result = await video_service.generate_video(
        video_service.VideoModel.SEEDANCE_2,
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
    )

    assert result.task_id == "kie-123"
    assert result.provider == "kieai"
    primary.assert_awaited_once()
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_seedance2_falls_back_to_neironych_when_kie_fails(monkeypatch) -> None:
    primary = AsyncMock(side_effect=RuntimeError("kie unavailable"))
    fallback = AsyncMock(return_value="neur-123")
    monkeypatch.setattr(video_service.kieai_client, "create_task", primary)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", fallback)

    result = await video_service.generate_video(
        video_service.VideoModel.SEEDANCE_2,
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-42",
    )

    assert result.task_id == "neironych:neur-123"
    assert result.provider == "neironych"
    assert result.uses_webhook is False
    assert fallback.await_args.kwargs["product_model"] == "bytedance/seedance-2"
    assert fallback.await_args.kwargs["idempotency_key"] == "apix-video-42"


@pytest.mark.asyncio
async def test_seedance25_uses_kie_primary_and_does_not_call_fallback(monkeypatch) -> None:
    install_video_runtime_fixes()
    primary = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-25"}})
    fallback = AsyncMock(return_value="neur-should-not-run")
    monkeypatch.setattr(video_service.kieai_client, "create_task", primary)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", fallback)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
    )

    assert result.task_id == "kie-25"
    assert result.provider == "kieai"
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_seedance25_falls_back_to_neironych_when_kie_fails(monkeypatch) -> None:
    install_video_runtime_fixes()
    primary = AsyncMock(side_effect=RuntimeError("kie unavailable"))
    fallback = AsyncMock(return_value="neur-25")
    monkeypatch.setattr(video_service.kieai_client, "create_task", primary)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", fallback)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-25",
    )

    assert result.task_id == "neironych:neur-25"
    assert result.provider == "neironych"
    assert fallback.await_args.kwargs["product_model"] == seedance25_adapter.MODEL_KEY
    assert fallback.await_args.kwargs["idempotency_key"] == "apix-video-25"

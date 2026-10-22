from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.kling4_contract import KEYFRAME_MODEL, REFERENCE_MODEL, Kling4Input
from api.kling4_launch import get_kling4_quote, tariff_key


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds,expected", [(2.1, 10), (5, 10), (7.4, 13)])
async def test_input_billing_uses_max_input_and_output(monkeypatch, seconds, expected):
    from api import kling4_launch as module

    monkeypatch.setattr(module, "validate_media", AsyncMock(return_value=[seconds]))
    key = tariff_key(REFERENCE_MODEL, "720p", True)
    monkeypatch.setattr(
        module.repo,
        "get_model_cost",
        AsyncMock(return_value=SimpleNamespace(model_key=key, credits=17, is_active=True)),
    )
    quote = await get_kling4_quote(
        SimpleNamespace(),
        REFERENCE_MODEL,
        "A scene",
        Kling4Input(video_urls=["https://cdn.example.org/a.mp4"]),
    )
    assert quote.billable_seconds == expected
    assert quote.credits == expected * 17
    assert quote.tariff_key == key


@pytest.mark.asyncio
async def test_video_element_only_uses_live_verified_no_video_tariff(monkeypatch):
    from api import kling4_launch as module

    monkeypatch.setattr(module, "validate_media", AsyncMock(return_value=[3.1, 4.1]))
    monkeypatch.setattr(
        module.repo,
        "get_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=42.5, is_active=True)),
    )
    data = Kling4Input(
        duration=3,
        resolution="1080p",
        elements=[{"name": "Hero", "video_url": "https://cdn.example.org/a.mp4"}],
    )
    quote = await get_kling4_quote(None, REFERENCE_MODEL, "@Hero walks", data)
    assert quote.billable_seconds == 3
    assert quote.credits == 127.5
    assert not quote.tariff_key.endswith("__video_input=true")


@pytest.mark.asyncio
async def test_inactive_tariff_fails_closed_without_base_price_fallback(monkeypatch):
    from api import kling4_launch as module

    monkeypatch.setattr(module, "validate_media", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.repo, "get_model_cost", AsyncMock(return_value=None))
    with pytest.raises(ValueError):
        await get_kling4_quote(None, KEYFRAME_MODEL, "A scene", Kling4Input())


@pytest.mark.asyncio
async def test_media_rejects_unmeasurable_remote_input():
    from api.kling4_launch import validate_media

    with pytest.raises(ValueError):
        await validate_media(Kling4Input(video_urls=["https://cdn.example.org/a.mp4"]))


@pytest.mark.asyncio
async def test_video_service_accepts_kling4_only_with_verified_input(monkeypatch):
    from api import kieai_client, kling4_launch, video_service

    sent = AsyncMock(return_value={"code": 200, "data": {"taskId": "kling4-task"}})
    monkeypatch.setattr(kieai_client, "create_task", sent)
    monkeypatch.setattr(
        kling4_launch,
        "stage_kling4_payload",
        AsyncMock(
            return_value={
                "model": REFERENCE_MODEL,
                "input": {"prompt": "A scene", "duration": 3, "resolution": "720p"},
            }
        ),
    )
    model = video_service.VideoModel(REFERENCE_MODEL)
    with pytest.raises(ValueError):
        await video_service.generate_video(model, "A scene")
    result = await video_service.generate_video(
        model, "A scene", kling4_input=Kling4Input(duration=3)
    )
    assert result.task_id == "kling4-task"
    assert sent.await_count == 1


@pytest.mark.asyncio
async def test_voice_outside_verified_live_profile_rejected_before_payment(monkeypatch, tmp_path):
    from api import kling4_launch as module
    from api.media_gateway import MediaProbe

    file = tmp_path / "voice.wav"
    file.write_bytes(b"fixture")
    monkeypatch.setattr(module, "local_upload_path_from_url", lambda _url: file)
    monkeypatch.setattr(
        module, "probe_local_media", AsyncMock(return_value=MediaProbe(duration_seconds=4.9))
    )
    with pytest.raises(ValueError, match="5–30"):
        await module.validate_media(
            Kling4Input(
                voices=[{"name": "Narrator", "audio_url": "https://cdn.example.org/voice.wav"}]
            )
        )


@pytest.mark.asyncio
async def test_callback_status_excludes_echoed_input_urls(monkeypatch):
    from api import kling4_status as module

    monkeypatch.setattr(
        module.kieai_client,
        "get_task_status",
        AsyncMock(
            return_value={
                "code": 200,
                "data": {
                    "taskId": "task",
                    "state": "success",
                    "resultJson": '{"resultUrls": ["https://cdn.example.org/output.mp4"]}',
                    "param": '{"input":{"video_urls":["https://cdn.example.org/input.mp4"]}}',
                },
            }
        ),
    )
    result = await module.canonical_kling4_status("task")
    assert "param" not in result["data"]

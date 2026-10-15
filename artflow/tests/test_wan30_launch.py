"""Wan3 user request and money quote: no provider POST, no real credits."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import wan30_launch
from api.media_gateway import MediaKind, MediaProbe
from api.wan30_contract import build_kie_wan30_payload


@pytest.mark.asyncio
async def test_plain_text_wan3_quote_5s_720p_is_exact(monkeypatch):
    async def rate(session, key):
        mapping = {
            "wan/3-0-video": SimpleNamespace(credits=6, is_active=True),
            "wan/3-0-video__resolution=720p": SimpleNamespace(credits=12, is_active=True),
        }
        return mapping.get(key)
    monkeypatch.setattr(wan30_launch.repo, "get_model_cost", rate)
    request=await wan30_launch.create_wan30_request(
        model="wan/3-0-video", prompt="A waterfall", mode="text",
        duration=5, resolution="720p",
    )
    quote=await wan30_launch.get_wan30_quote(object(),request)
    assert quote.credits==60 and quote.rate==12
    assert quote.billable_seconds==5
    assert quote.stored_params()["wan30_billing"]["reserved_credits"]==60
    assert build_kie_wan30_payload(request)["input"]["duration"]==5


@pytest.mark.asyncio
async def test_video_reference_length_counted_before_quote_and_exposes_edit_mode(monkeypatch):
    monkeypatch.setattr(
        wan30_launch, "local_upload_path_from_url",
        lambda url: Path("/tmp/mocked-local-video.mp4"),
    )
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    probe=AsyncMock(return_value=MediaProbe(width=1280,height=720,duration_seconds=7.6))
    monkeypatch.setattr(wan30_launch, "probe_local_media", probe)
    request=await wan30_launch.create_wan30_request(
        model="wan/3-0-video-prime", prompt="Change to sunrise",
        mode="video", video_url="https://example.test/static/source.mp4",
        duration=5,resolution="480p",aspect_ratio="adaptive",
    )
    assert request.mode=="edit"
    assert request.reference_video_durations==(7.6,)
    assert build_kie_wan30_payload(request)["input"]["reference_video_urls"]==[
        "https://example.test/static/source.mp4"
    ]
    probe.assert_awaited_once()
    assert probe.await_args.args[1]==MediaKind.VIDEO
    async def rate(session, key):
        return SimpleNamespace(credits=9, is_active=True)
    monkeypatch.setattr(wan30_launch.repo, "get_model_cost", rate)
    quote=await wan30_launch.get_wan30_quote(object(),request)
    assert quote.billable_seconds==13  # ceil(7.6 input + 5 output)
    assert quote.credits==117
    assert quote.stored_params()["wan30_billing"]["input_video_seconds"]==7.6


@pytest.mark.asyncio
async def test_two_photos_become_first_and_last_frames():
    request=await wan30_launch.create_wan30_request(
        model="wan/3-0-video",prompt="A rabbit waves",mode="image",
        image_urls=["https://example.test/frame1.png","https://example.test/frame2.png"],
    )
    assert request.first_frame_url=="https://example.test/frame1.png"
    assert request.last_frame_url=="https://example.test/frame2.png"
    assert request.reference_image_urls==()


@pytest.mark.asyncio
async def test_external_unmeasurable_video_ref_is_rejected_without_provider_submission():
    with pytest.raises(ValueError, match="Загрузи"):
        await wan30_launch.create_wan30_request(
            model="wan/3-0-video",prompt="Edit",mode="video",
            video_url="https://remote.example.test/paid.mp4",
        )


@pytest.mark.asyncio
async def test_inactive_1080p_variant_never_falls_back_to_active_base(monkeypatch):
    exact=AsyncMock(side_effect=[
        SimpleNamespace(credits=24,is_active=False),
        SimpleNamespace(credits=6,is_active=True),
    ])
    monkeypatch.setattr(wan30_launch.repo,"get_model_cost", exact)
    request=await wan30_launch.create_wan30_request(
        model="wan/3-0-video",prompt="A boat",mode="text",
        resolution="1080p",
    )
    with pytest.raises(ValueError, match="недоступен"):
        await wan30_launch.get_wan30_quote(object(),request)
    assert exact.await_args_list[0].args[1]=="wan/3-0-video__resolution=1080p"



@pytest.mark.asyncio
async def test_frontend_repeated_image_url_not_mistaken_for_two_frames():
    same = "https://example.test/upload/user.png"
    request = await wan30_launch.create_wan30_request(
        model="wan/3-0-video", prompt="Sunlight in a garden",
        mode="image", image_urls=[same, same],
    )
    assert request.first_frame_url == same
    assert request.last_frame_url is None
    assert build_kie_wan30_payload(request)["input"]["first_frame_url"] == same


def test_wan3_contracts_are_in_provider_inventory():
    """The contract list includes both Wan3 modes for CI audit coverage."""
    from api.provider_contract_catalog import ALL_CONTRACTS
    from api.provider_operation_registry import PUBLIC_API_CONTRACT_IDS

    exposed = {c.contract_id for c in ALL_CONTRACTS if c.model in {
        "wan/3-0-video", "wan/3-0-video-prime",
    }}
    assert exposed == {"video.wan30", "video.wan30.prime"}
    assert exposed <= PUBLIC_API_CONTRACT_IDS


def test_unquoted_legacy_provider_operation_router_is_not_mounted():
    from main import app

    public_routes = {getattr(route, "path", "") for route in app.routes}
    assert not any("/provider-operations/" in route for route in public_routes)


@pytest.mark.asyncio
async def test_wan_primary_video_repeated_in_advanced_refs_is_only_charged_once(monkeypatch):
    source = "https://apixbotai.com/static/upload/input.mp4"
    monkeypatch.setattr(
        wan30_launch, "local_upload_path_from_url",
        lambda url: Path("/tmp/wantest-local-clip.mp4"),
    )
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    probe = AsyncMock(return_value=MediaProbe(width=1280, height=720, duration_seconds=7.5))
    monkeypatch.setattr(wan30_launch, "probe_local_media", probe)
    request = await wan30_launch.create_wan30_request(
        model="wan/3-0-video", prompt="Edit the same scene",
        mode="video", video_url=source, duration=5,
        options={"reference_video_urls": [source, source]},
    )
    assert request.reference_video_urls == (source,)
    assert request.reference_video_durations == (7.5,)
    probe.assert_awaited_once()


def test_wan_quote_persists_all_inputs_for_safe_remix_restoration():
    request = wan30_launch.Wan30Request(
        model="wan/3-0-video-prime", prompt="Edit in warm light",
        mode="edit", duration=7, resolution="1080p",
        reference_video_urls=("https://apixbotai.com/static/upload/video.mp4",),
        reference_video_durations=(4.5,), reference_audio_urls=(
            "https://apixbotai.com/static/upload/voice.mp3",),
        reference_audio_durations=(4.0,), reference_image_urls=(
            "https://apixbotai.com/static/upload/face.png",),
        reference_file_urls=("https://files.example.com/inventory.zip",),
        reference_link_urls=(), audio=False, nsfw_checker=True, seed=0,
    )
    quote = wan30_launch.Wan30Quote(
        request=request, billable_seconds=12, rate=18, credits=216, resolution="1080p",
    )
    stored = quote.stored_params()
    args = stored["wan30_request"]
    assert args["reference_video_urls"] == [
        "https://apixbotai.com/static/upload/video.mp4"
    ]
    assert args["reference_video_durations"] == [4.5]
    assert args["reference_audio_urls"] == [
        "https://apixbotai.com/static/upload/voice.mp3"
    ]
    assert args["reference_image_urls"] == [
        "https://apixbotai.com/static/upload/face.png"
    ]
    assert args["audio"] is False
    assert args["seed"] == 0
    assert args["nsfw_checker"] is True


def test_wan_live_smoke_runner_routes_through_user_quoted_checkout_not_legacy_api():
    import json

    import httpx

    from scripts import run_provider_live_smoke as smoke

    routes = []
    def fake_response(request):
        routes.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.url.path == "/api/v1/generate/video"
            payload = json.loads(request.content)
            assert payload["model"] == "wan/3-0-video"
            assert payload["duration"] == 5
            assert payload["resolution"] == "720p"
            return httpx.Response(202, json={"id": 777, "status": "processing"})
        assert request.url.path == "/api/v1/generations/777"
        return httpx.Response(200, json={
            "id": 777, "status": "done", "result_url": "https://cdn.example.com/clip.mp4",
        })

    with httpx.Client(transport=httpx.MockTransport(fake_response)) as client:
        result = smoke._run_case(
            client, "https://apixbotai.com", "video.wan30", poll_interval=0.0,
        )
    assert result["status"] == "completed"
    assert len(routes) == 2

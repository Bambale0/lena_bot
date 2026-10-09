"""Regression for APIX mixed-reference edits rejected by the Neironych gateway.

All HTTP is in-memory. Metadata is synthetic; no production credentials,
customer media, database, paid generation or Telegram delivery are used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from api import media_gateway, public_files
from api import neironych_seedance_runtime as runtime
from api.media_gateway import MediaProbe
from api.neironych_seedance import NeironychSeedanceClient
from core.neironych_seedance_contract import SeedanceContractError, normalize_seedance_request

MODEL = "bytedance/seedance-2-5"
VIDEO = "https://example.test/source.mp4"
IMAGE = "https://example.test/appearance.jpg"
AUDIO = "https://example.test/beat.mp3"


@pytest.fixture
async def wire(monkeypatch):
    requests = []
    admitted = []

    async def before_submit(idem, digest):
        admitted.append((idem, digest))

    def transport(request):
        body = json.loads(request.content)
        # Admission must persist the exact body hash BEFORE sending any POST.
        if admitted:
            assert admitted[-1][1] == hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
        requests.append((request, body))
        return httpx.Response(202, json={"request_id": "synthetic-seedance-0001"})

    async with httpx.AsyncClient(base_url="https://gateway.test", transport=httpx.MockTransport(transport)) as http:
        gateway = NeironychSeedanceClient("test-only-key", "https://gateway.test", client=http)
        monkeypatch.setattr(runtime, "_client", lambda: gateway)
        monkeypatch.setattr(public_files, "local_upload_path_from_url", lambda url: Path("/synthetic/source.mp4"))
        probe = AsyncMock(return_value=MediaProbe(width=1080, height=1920, duration_seconds=10.4))
        monkeypatch.setattr(media_gateway, "probe_local_media", probe)
        context = runtime.SubmissionContext(
            client_request_id="11111111-1111-4111-8111-111111111111",
            before_submit=before_submit,
        )
        yield SimpleNamespace(requests=requests, probe=probe, admitted=admitted, context=context)


@pytest.mark.asyncio
@pytest.mark.parametrize("images,audios", [([IMAGE], []), ([], [AUDIO]), ([IMAGE], [AUDIO]), ([IMAGE, IMAGE + "?v=2"], [])])
async def test_mixed_edit_uses_reference_preserving_assets_and_source_dimensions(wire, images, audios):
    result = await runtime.generate_product_video(
        product_model=MODEL, prompt="Follow the source footage and supplied references.",
        image_urls=images, video_urls=[VIDEO], audio_urls=audios,
        duration=-1, aspect_ratio="adaptive", resolution="480p", edit=True,
        idempotency_key="test-mode-contract-0001", submission_context=wire.context,
    )
    assert result == "synthetic-seedance-0001"
    assert len(wire.requests) == len(wire.admitted) == 1
    request, body = wire.requests[0]
    assert body["omni_reference_task_type"] == "reference"
    assert body["duration"] == 11  # same ceil(source) used by the precharge quote
    assert body["aspect_ratio"] == "9:16"
    assert body["resolution"] == "480p"
    assert body["reference_videos"] == [{"url": VIDEO}]
    assert body.get("reference_images", []) == [{"url": url} for url in images]
    assert body.get("reference_audios", []) == [{"url": url} for url in audios]
    assert request.headers["Idempotency-Key"] == "test-mode-contract-0001"
    assert request.headers["X-Client-Request-Id"] == wire.context.client_request_id
    wire.probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_video_edit_retains_documented_inherited_dimensions(wire):
    await runtime.generate_product_video(
        product_model=MODEL, prompt="Make the colors warmer.", video_urls=[VIDEO],
        duration=-1, aspect_ratio="adaptive", resolution="720p", edit=True,
        idempotency_key="test-mode-contract-0002",
    )
    body = wire.requests[0][1]
    assert body["omni_reference_task_type"] == "edit"
    assert body["reference_videos"] == [{"url": VIDEO}]
    assert not {"duration", "aspect_ratio", "reference_images", "reference_audios"}.intersection(body)
    wire.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_regular_mixed_reference_keeps_user_selected_duration_and_ratio(wire):
    await runtime.generate_product_video(
        product_model=MODEL, prompt="Follow the subject, motion and beat.",
        image_urls=[IMAGE], video_urls=[VIDEO], audio_urls=[AUDIO],
        duration=13, aspect_ratio="4:3", resolution="1080p", edit=False,
        idempotency_key="test-mode-contract-0003",
    )
    body = wire.requests[0][1]
    assert body["omni_reference_task_type"] == "reference"
    assert (body["duration"], body["aspect_ratio"], body["resolution"]) == (13, "4:3", "1080p")
    wire.probe.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("probe", [
    MediaProbe(width=1080, height=1920, duration_seconds=None),
    MediaProbe(width=1080, height=1920, duration_seconds=float("nan")),
    MediaProbe(width=1080, height=1920, duration_seconds=float("inf")),
    MediaProbe(width=1080, height=1920, duration_seconds=3.9),
    MediaProbe(width=1080, height=1920, duration_seconds=30.1),
    MediaProbe(width=0, height=1920, duration_seconds=10.4),
    MediaProbe(width=1080, height=None, duration_seconds=10.4),
])
async def test_mixed_edit_invalid_metadata_stops_before_admission_or_http(wire, probe):
    wire.probe.return_value = probe
    with pytest.raises(SeedanceContractError):
        await runtime.generate_product_video(
            product_model=MODEL, prompt="Follow the source.", image_urls=[IMAGE], video_urls=[VIDEO],
            duration=-1, aspect_ratio="adaptive", edit=True,
            idempotency_key="test-mode-contract-0004", submission_context=wire.context,
        )
    assert wire.requests == wire.admitted == []


@pytest.mark.asyncio
async def test_mixed_edit_untrusted_external_source_is_not_fetched(wire, monkeypatch):
    monkeypatch.setattr(public_files, "local_upload_path_from_url", lambda url: None)
    with pytest.raises(SeedanceContractError):
        await runtime.generate_product_video(
            product_model=MODEL, prompt="Follow the source.", image_urls=[IMAGE], video_urls=[VIDEO],
            duration=-1, aspect_ratio="adaptive", edit=True,
            idempotency_key="test-mode-contract-0005", submission_context=wire.context,
        )
    assert wire.requests == wire.admitted == []
    wire.probe.assert_not_awaited()


@pytest.mark.parametrize("extra", [
    {"reference_images": [{"url": IMAGE}]},
    {"reference_audios": [{"url": AUDIO}]},
    {"reference_videos": [{"url": VIDEO}, {"url": VIDEO + "?second=1"}]},
])
def test_raw_edit_rejects_extra_references_instead_of_silently_dropping_them(extra):
    with pytest.raises(SeedanceContractError, match="edit"):
        normalize_seedance_request("seedance-2.5", {
            "prompt": "Change the lighting.", "omni_reference_task_type": "edit",
            "reference_videos": [{"url": VIDEO}], **extra,
        })


def test_seedance_25_silent_control_matches_gateway_without_affecting_20():
    body = {"prompt": "Animate.", "generate_audio": False}
    assert normalize_seedance_request("seedance-2.5", body)["generate_audio"] is False
    with pytest.raises(SeedanceContractError):
        normalize_seedance_request("seedance-2.0", body)


@pytest.mark.asyncio
@pytest.mark.parametrize("width,height,seconds,ratio,output", [
    (1920, 1080, 4.0, "16:9", 4),
    (1080, 1920, 30.0, "9:16", 30),
    (1000, 1000, 10.01, "1:1", 11),
    (1440, 1080, 14.2, "4:3", 15),
    (1080, 1440, 7.0, "3:4", 7),
    (2520, 1080, 9.0, "21:9", 9),
])
async def test_source_dimensions_use_supported_ratios_and_quote_rounding(wire, width, height, seconds, ratio, output):
    wire.probe.return_value = MediaProbe(width=width, height=height, duration_seconds=seconds)
    await runtime.generate_product_video(
        product_model=MODEL, prompt="Follow the source.", image_urls=[IMAGE], video_urls=[VIDEO],
        duration=5, aspect_ratio="16:9", edit=True, idempotency_key="test-source-controls",
    )
    body = wire.requests[0][1]
    assert (body["duration"], body["aspect_ratio"]) == (output, ratio)


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["production_wrapper", "legacy_wrapper"])
async def test_both_shared_service_wrappers_reach_real_neironych_client_with_reference(wire, monkeypatch, entrypoint):
    from api import seedance25_adapter, video_runtime_fixes, video_service

    async def choose_neironych(_model, *, kie, neironych):
        return await neironych()

    monkeypatch.setattr(video_runtime_fixes, "submit_seedance", choose_neironych)
    monkeypatch.setattr(seedance25_adapter, "submit_seedance", choose_neironych)
    monkeypatch.setattr(video_runtime_fixes, "ensure_video_reference_aspect_url", lambda url, **kw: url)
    monkeypatch.setattr(video_runtime_fixes, "_validate_seedance_reference_video_url", AsyncMock())
    kwargs = dict(
        image_url=[IMAGE], reference_video_url=[VIDEO], duration=11, aspect_ratio="adaptive",
        resolution="480p", idempotency_key="test-wrappers-mode", neironych_submission=wire.context,
    )
    prompt = "Edit the video @Video1 with the appearance from @Image1."
    if entrypoint == "production_wrapper":
        result = await video_runtime_fixes._seedance_generate(video_service, prompt, (), kwargs)
    else:
        service = SimpleNamespace(
            VideoModel=video_service.VideoModel, VideoResult=video_service.VideoResult,
            generate_video=AsyncMock(side_effect=AssertionError("unexpected model route")),
        )
        seedance25_adapter._install_seedance25_generate_wrapper(service)
        result = await service.generate_video(video_service.VideoModel(MODEL), prompt, **kwargs)
    assert result.provider == "neironych"
    assert result.task_id == "neironych:synthetic-seedance-0001"
    body = wire.requests[0][1]
    assert body["omni_reference_task_type"] == "reference"
    assert body["prompt"] == prompt
    assert (body["duration"], body["aspect_ratio"]) == (11, "9:16")
    assert body["reference_images"] == [{"url": IMAGE}]
    assert body["reference_videos"] == [{"url": VIDEO}]


@pytest.mark.asyncio
@pytest.mark.parametrize("videos", [[], [VIDEO, VIDEO + "?other=1"]])
async def test_product_edit_requires_one_unambiguous_source_before_admission(wire, videos):
    with pytest.raises(SeedanceContractError):
        await runtime.generate_product_video(
            product_model=MODEL, prompt="Edit the source.", image_urls=[IMAGE], video_urls=videos,
            edit=True, idempotency_key="test-ambiguous-source", submission_context=wire.context,
        )
    assert wire.requests == wire.admitted == []
    wire.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_diagnostics_never_log_media_prompt_or_key(wire, caplog):
    with caplog.at_level("INFO", logger=runtime.__name__):
        await runtime.generate_product_video(
            product_model=MODEL, prompt="PRIVATE_CUSTOMER_PROMPT", image_urls=[IMAGE], video_urls=[VIDEO],
            duration=-1, aspect_ratio="adaptive", edit=True, idempotency_key="test-safe-mode-log",
        )
    assert "provider_mode=reference" in caplog.text
    assert "duration=11" in caplog.text and "aspect_ratio=9:16" in caplog.text
    for secret in ("PRIVATE_CUSTOMER_PROMPT", "test-only-key", IMAGE, VIDEO):
        assert secret not in caplog.text

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import seedance25_adapter, video_runtime_fixes
from db.models import GenerationType
from tests.test_feed_remix_prompt_security import (
    SECRET,
    SOURCE_IMAGE,
    USER_IMAGE,
)
from tests.test_feed_remix_prompt_security import (
    api_launch as api_launch,
)

MODEL = seedance25_adapter.MODEL_KEY
SOURCE_VIDEO = "https://example.test/source.mp4"


@pytest.fixture
def seedance_api(request, monkeypatch):
    launch = request.getfixturevalue("api_launch")
    probe = AsyncMock(return_value=7)
    monkeypatch.setattr(launch.routes, "seedance25_edit_billing_duration", probe)
    launch.source.gen_type = GenerationType.video
    launch.source.result_url = SOURCE_VIDEO
    launch.source.model = MODEL
    launch.probe = probe
    return launch


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["image", "video"])
@pytest.mark.parametrize("inputs", [{"change_request": "make the coat blue"}, {"image_url": USER_IMAGE}])
async def test_seedance_personalization_keeps_source_and_isolates_author(seedance_api, source_kind, inputs):
    routes = seedance_api.routes
    if source_kind == "image":
        seedance_api.source.gen_type = GenerationType.image
        seedance_api.source.result_url = SOURCE_IMAGE
        seedance_api.probe.return_value = None
    body = routes.FeedRemixRequest(model=MODEL, mode="text", duration=5, **inputs)
    quote = await routes.quote_feed_remix(77, body, seedance_api.session, seedance_api.user)
    await routes.remix_feed_post(77, body, seedance_api.session, seedance_api.user)

    submitted = seedance_api.generate.await_args
    assert SECRET not in submitted.args[1]
    assert "make the coat blue" in submitted.args[1] if inputs.get("change_request") else True
    expected_refs = ([SOURCE_IMAGE] if source_kind == "image" else []) + ([USER_IMAGE] if inputs.get("image_url") else [])
    assert (submitted.kwargs["image_url"] or []) == expected_refs
    assert submitted.kwargs["reference_video_url"] == ([SOURCE_VIDEO] if source_kind == "video" else None)
    assert submitted.kwargs["grok_mode"] == "multimodal"
    assert seedance25_adapter.is_explicit_video_edit_prompt(submitted.args[1]) is (source_kind == "video")
    expected_duration = 7 if source_kind == "video" else 5
    assert quote["cost_credits"] == expected_duration * 4
    assert seedance_api.charge.await_args.args[2] == expected_duration * 4
    assert seedance_api.save.await_args.kwargs["input_params"]["duration"] == expected_duration
    assert seedance_api.save.await_args.kwargs["source_feed_gen_id"] == 77
    if source_kind == "video":
        assert submitted.kwargs["aspect_ratio"] == "adaptive"
        assert quote["source_video_edit"] is True
        assert quote["effective_duration_seconds"] == 7
        assert seedance_api.save.await_args.kwargs["input_params"]["provider_duration"] == -1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["quote_feed_remix", "remix_feed_post"])
@pytest.mark.parametrize("error", [ValueError("source video cannot be verified"), RuntimeError("ffprobe unavailable")])
async def test_seedance_unverifiable_source_stops_before_price_or_charge(seedance_api, operation, error):
    seedance_api.probe.side_effect = error
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, change_request="make the coat blue")
    with pytest.raises(HTTPException) as raised:
        await getattr(seedance_api.routes, operation)(77, body, seedance_api.session, seedance_api.user)
    assert raised.value.status_code in {422, 503}
    seedance_api.costs.assert_not_awaited()
    seedance_api.charge.assert_not_awaited()
    seedance_api.generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["quote_feed_remix", "remix_feed_post"])
async def test_seedance_conflicting_hidden_video_token_rejected_before_price(seedance_api, operation, monkeypatch):
    monkeypatch.setattr(seedance_api.routes, "seedance25_edit_billing_duration", video_runtime_fixes.seedance25_edit_billing_duration)
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, image_url=USER_IMAGE, audio_ids=["__apix_seedance25:video_ref=https://example.test/other.mp4"])
    with pytest.raises(HTTPException) as raised:
        await getattr(seedance_api.routes, operation)(77, body, seedance_api.session, seedance_api.user)
    assert raised.value.status_code == 422
    seedance_api.costs.assert_not_awaited()
    seedance_api.charge.assert_not_awaited()
    seedance_api.generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reference_count", [29, 30])
async def test_seedance_source_image_occupies_one_of_30_reference_slots(seedance_api, reference_count):
    seedance_api.source.gen_type = GenerationType.image
    seedance_api.source.result_url = SOURCE_IMAGE
    seedance_api.probe.return_value = None
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, reference_urls=[f"https://example.test/{i}.jpg" for i in range(reference_count)])
    if reference_count == 30:
        with pytest.raises(HTTPException) as raised:
            await seedance_api.routes.quote_feed_remix(77, body, seedance_api.session, seedance_api.user)
        assert raised.value.status_code == 422
        seedance_api.costs.assert_not_awaited()
    else:
        await seedance_api.routes.remix_feed_post(77, body, seedance_api.session, seedance_api.user)
        assert len(seedance_api.generate.await_args.kwargs["image_url"]) == 30


@pytest.mark.asyncio
async def test_seedance_plain_source_image_repeat_preserves_original(seedance_api):
    seedance_api.source.gen_type = GenerationType.image
    seedance_api.source.result_url = SOURCE_IMAGE
    seedance_api.probe.return_value = None
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, source_image_url=SOURCE_IMAGE)
    await seedance_api.routes.remix_feed_post(77, body, seedance_api.session, seedance_api.user)
    assert seedance_api.generate.await_args.args[1] == SECRET
    assert seedance_api.generate.await_args.kwargs["image_url"] == [SOURCE_IMAGE]


@pytest.mark.asyncio
@pytest.mark.parametrize("client_duration", [5, 30])
async def test_seedance_duration_comes_from_real_source_probe_before_tariff(seedance_api, monkeypatch, client_duration):
    monkeypatch.setattr(seedance_api.routes, "seedance25_edit_billing_duration", video_runtime_fixes.seedance25_edit_billing_duration)
    monkeypatch.setattr(video_runtime_fixes, "local_upload_path_from_url", lambda url: "synthetic/local-source.mp4")
    probe = AsyncMock(return_value=SimpleNamespace(width=1280, height=720, duration_seconds=6.2))
    monkeypatch.setattr(video_runtime_fixes, "probe_local_media", probe)
    async def tariff(*args, **kwargs):
        probe.assert_awaited_once()
        assert kwargs["duration"] == 7
        return SimpleNamespace(credits=4, is_active=True)
    monkeypatch.setattr(seedance_api.routes.repo, "resolve_video_model_cost", AsyncMock(side_effect=tariff))
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, image_url=USER_IMAGE, duration=client_duration, audio_ids=[f"__apix_seedance25:duration={client_duration}"])
    quote = await seedance_api.routes.quote_feed_remix(77, body, seedance_api.session, seedance_api.user)
    assert quote["cost_credits"] == 28
    seedance_api.charge.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["kie", "neironych"])
@pytest.mark.parametrize("inputs", [{"change_request": "make the coat blue"}, {"image_url": USER_IMAGE}])
async def test_feed_video_intent_reaches_provider_appropriate_mode_contract(seedance_api, monkeypatch, provider, inputs):
    from api import neironych_seedance_runtime

    captured = {}
    async def select_provider(_model, *, kie, neironych):
        return await (kie() if provider == "kie" else neironych())
    monkeypatch.setattr(video_runtime_fixes, "submit_seedance", select_provider)
    monkeypatch.setattr(video_runtime_fixes, "ensure_video_reference_aspect_url", lambda url, **kwargs: url)
    validate = AsyncMock()
    monkeypatch.setattr(video_runtime_fixes, "_validate_seedance_reference_video_url", validate)
    service = seedance_api.routes.video_service
    monkeypatch.setattr(service, "_prepare_video_reference_urls", AsyncMock(side_effect=lambda urls: urls))
    monkeypatch.setattr(service, "_prepare_reference_video_url", AsyncMock(side_effect=lambda url: url))
    async def submit_neironych(**kwargs):
        captured.update(kwargs)
        return "synthetic-video-edit"
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit_neironych)
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "synthetic-video-edit"}})
    monkeypatch.setattr(service.kieai_client, "create_task", kie)
    async def dispatch(_model, prompt, **kwargs):
        return await video_runtime_fixes._seedance_generate(service, prompt, (), kwargs)
    seedance_api.generate.side_effect = dispatch
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, duration=5, audio_ids=["__apix_seedance25:duration=30"], **inputs)
    await seedance_api.routes.remix_feed_post(77, body, seedance_api.session, seedance_api.user)
    validate.assert_awaited_once_with(SOURCE_VIDEO, video_edit=True)
    if provider == "kie":
        payload = kie.await_args.args[0]["input"]
        assert payload["duration"] == -1
        assert payload["aspect_ratio"] == "adaptive"
        assert payload["reference_video_urls"] == [SOURCE_VIDEO]
        assert payload.get("reference_image_urls", []) == ([USER_IMAGE] if inputs.get("image_url") else [])
    else:
        assert captured["edit"] is True
        _model, payload = neironych_seedance_runtime.build_product_payload(**{
            key: value for key, value in captured.items()
            if key not in {"idempotency_key", "submission_context"}
        }, source_probe=SimpleNamespace(width=1280, height=720, duration_seconds=6.2))
        assert payload["reference_videos"] == [{"url": SOURCE_VIDEO}]
        if inputs.get("image_url"):
            assert payload["omni_reference_task_type"] == "reference"
            assert payload["reference_images"] == [{"url": USER_IMAGE}]
            assert (payload["duration"], payload["aspect_ratio"]) == (7, "16:9")
        else:
            assert payload["omni_reference_task_type"] == "edit"
            assert "duration" not in payload and "aspect_ratio" not in payload
    assert SECRET not in str(payload)
    assert seedance_api.charge.await_args.args[2] == 28


@pytest.mark.asyncio
async def test_same_source_video_token_deduplicates_without_dropping_user_photos(seedance_api):
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, image_url=USER_IMAGE, audio_ids=[f"__apix_seedance25:video_ref={SOURCE_VIDEO}"])
    await seedance_api.routes.remix_feed_post(77, body, seedance_api.session, seedance_api.user)
    assert seedance_api.probe.await_args.args[1] == [SOURCE_VIDEO]
    assert seedance_api.generate.await_args.kwargs["image_url"] == [USER_IMAGE]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["quote_feed_remix", "remix_feed_post"])
async def test_historical_external_source_uses_real_precharge_rejection(seedance_api, monkeypatch, operation):
    monkeypatch.setattr(seedance_api.routes, "seedance25_edit_billing_duration", video_runtime_fixes.seedance25_edit_billing_duration)
    body = seedance_api.routes.FeedRemixRequest(model=MODEL, image_url=USER_IMAGE)
    with pytest.raises(HTTPException) as raised:
        await getattr(seedance_api.routes, operation)(77, body, seedance_api.session, seedance_api.user)
    assert raised.value.status_code == 422
    assert "до списания" in raised.value.detail
    seedance_api.costs.assert_not_awaited()
    seedance_api.charge.assert_not_awaited()
    seedance_api.generate.assert_not_awaited()

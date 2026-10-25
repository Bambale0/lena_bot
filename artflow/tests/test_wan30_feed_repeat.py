"""Regression: Wan feed checkout must hand a verified recipe to the provider.

All examples are synthetic; only media probing, persistence and supplier IO
are replaced. The actual HTTP handlers, Wan builder and price resolver run.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api import miniapp_routes as routes
from api import wan30_launch
from api.miniapp_auth import get_miniapp_user
from api.wan30_contract import WAN30_MODELS, Wan30Request
from db.models import GenerationStatus, GenerationType
from db.session import get_session
from main import app

PHOTO = "https://example.test/reader.png"
AUTHOR = "https://example.test/author.png"
VIDEO = "https://example.test/original-input.mp4"
OUTPUT = "https://example.test/final-output.mp4"
SECRET = "Synthetic creator recipe; replace the subject with the reader."


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_explicit_duration_survives_all_wan_recipe_restores(harness, surface):
    recipe(harness, "wan/3-0-video")
    path = f"/api/{surface}/feed/77/remix"
    body = {"model": harness.source.model, "image_url": PHOTO, "duration_override": 20}
    quote = await harness.client.post(path + "/quote", json=body)
    assert quote.status_code == 200, quote.text
    assert quote.json().get("data", quote.json())["cost_credits"] == 104
    launched = await harness.client.post(path, json={**body, "quoted_credits": 104})
    assert launched.status_code == 202, launched.text
    assert harness.submit.await_args.args[0].duration == 20
    assert harness.source.input_params["wan30_request"]["duration"] == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [True, 15.5, "15", 0, 31])
async def test_duration_override_is_strict_before_debit(harness, seconds):
    recipe(harness, "wan/3-0-video")
    response = await harness.client.post("/api/v1/feed/77/remix", json={
        "model": harness.source.model, "image_url": PHOTO, "duration_override": seconds, "quoted_credits": 84,
    })
    assert response.status_code == 422, response.text
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_wan_output_override_keeps_reference_budget_guard(harness):
    recipe(harness, "wan/3-0-video")
    response = await harness.client.post("/api/v1/feed/77/remix", json={
        "model": harness.source.model, "image_url": PHOTO, "duration_override": 25, "quoted_credits": 124,
    })
    assert response.status_code == 422
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.fixture
async def harness(monkeypatch):
    source = SimpleNamespace(
        id=77,
        user_id=99,
        model="wan/3-0-video",
        gen_type=GenerationType.video,
        prompt=SECRET,
        result_url=OUTPUT,
        result_urls=None,
        is_public_feed=True,
    )
    user = SimpleNamespace(id=42, tg_id=777, credits=1000, is_banned=False)
    record = SimpleNamespace(
        id=99,
        user_id=42,
        gen_type=GenerationType.video,
        model=source.model,
        prompt=SECRET,
        status=GenerationStatus.pending,
        result_url=None,
        result_urls=None,
        credits_spent=0,
        created_at=datetime.now(timezone.utc),
        finished_at=None,
        is_public_feed=False,
        is_prompt_library=False,
        source_feed_gen_id=77,
        task_id=None,
        input_params="{}",
    )
    session = AsyncMock()
    state = SimpleNamespace(
        source=source,
        user=user,
        record=record,
        session=session,
        rate=4.0,
        active=True,
        events=[],
        saved={},
        durations={VIDEO: 5.2},
    )

    async def measured(url, kind):
        state.events.append("probe")
        if url not in state.durations:
            raise ValueError("Synthetic missing original media")
        return state.durations[url]

    async def rate(_session, key):
        state.events.append("price")
        return SimpleNamespace(model_key=key, credits=state.rate, is_active=state.active)

    async def charge(_session, user_id, amount):
        state.events.append("charge")
        return True

    async def save(*args, **kwargs):
        state.events.append("persist")
        state.saved = kwargs["input_params"]
        record.input_params = json.dumps(state.saved)
        record.credits_spent = args[5]
        record.model = args[2]
        return record

    async def submit(request, **kwargs):
        state.events.append("provider")
        if request.reference_video_urls or request.reference_audio_urls:
            assert state.events.index("probe") < state.events.index("charge")
        assert state.events.index("persist") < state.events.index("provider")
        return SimpleNamespace(task_id="synthetic-wan-task", provider="kieai")

    state.charge = AsyncMock(side_effect=charge)
    state.submit = AsyncMock(side_effect=submit)
    state.save = AsyncMock(side_effect=save)
    state.refund = AsyncMock()
    monkeypatch.setattr(wan30_launch, "_duration_for_owned_media", measured)
    monkeypatch.setattr(routes.repo, "get_model_cost", rate)
    monkeypatch.setattr(
        routes.repo,
        "resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=4.0, is_active=True)),
    )

    # Old generic pricing must not escape to network while reproducing RED.
    async def generic_seconds(normalized, **kwargs):
        from api.video_reference_billing import VideoSeconds

        refs = int(bool(normalized.get("reference_video_url")))
        return VideoSeconds(
            output=normalized["duration"],
            references=6 if refs else 0,
            billable=normalized["duration"] + (6 if refs else 0),
            reference_count=refs,
        )

    monkeypatch.setattr(routes, "measured_video_seconds", generic_seconds)
    monkeypatch.setattr(routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(routes.repo, "spend_credits", state.charge)
    monkeypatch.setattr(routes.repo, "create_generation", state.save)
    monkeypatch.setattr(routes.repo, "update_generation_task", AsyncMock())
    monkeypatch.setattr(routes.repo, "fail_generation_and_refund", state.refund)
    monkeypatch.setattr(routes.repo, "count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr(routes.repo, "increment_feed_share", AsyncMock())
    monkeypatch.setattr(routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(
        routes, "_register_seedance_callback_before_submit", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        routes,
        "make_submission_context",
        lambda *a, **k: SimpleNamespace(started=False, kie_started=False),
    )
    monkeypatch.setattr(routes, "persist_submission_result", AsyncMock(return_value=True))
    monkeypatch.setattr(routes.video_service.wan30_provider, "submit_wan30_provider", state.submit)

    async def db():
        yield session

    async def actor():
        return user

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[get_miniapp_user] = actor
    from api.web.generations import get_web_user_or_none

    app.dependency_overrides[get_web_user_or_none] = actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            state.client = client
            yield state
    finally:
        app.dependency_overrides.clear()


def recipe(harness, model, *, mode="edit", videos=(VIDEO,)):
    harness.source.model = model
    stored = asdict(
        Wan30Request(
            model=model,
            prompt=SECRET,
            mode=mode,
            reference_image_urls=(AUTHOR,),
            reference_video_urls=videos,
            reference_video_durations=tuple(5.2 for _ in videos),
            duration=15,
            resolution="480p",
            aspect_ratio="9:16",
            audio=False,
            seed=0,
        )
    )
    harness.source.input_params = {
        "model_key": model,
        "mode": "video" if videos else "image",
        "duration": 15,
        "aspect_ratio": "9:16",
        "resolution": "480p",
        "image_url": AUTHOR,
        "reference_video_url": videos[0] if videos else None,
        "wan30_request": json.loads(json.dumps(stored)),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_wan_feed_quote_and_launch_use_same_measured_recipe(harness, model, surface):
    recipe(harness, model)
    path = f"/api/{surface}/feed/77/remix"
    body = {"model": model, "image_url": PHOTO, "video_url": OUTPUT}
    quoted = await harness.client.post(path + "/quote", json=body)
    assert quoted.status_code == 200, quoted.text
    assert quoted.json().get("data", quoted.json())["cost_credits"] == 84
    assert quoted.json().get("data", quoted.json())["reference_seconds"] == 6
    harness.charge.assert_not_awaited()
    response = await harness.client.post(path, json={**body, "quoted_credits": 84})
    assert response.status_code == 202, response.text
    harness.submit.assert_awaited_once()
    request = harness.submit.await_args.args[0]
    assert isinstance(request, Wan30Request)
    assert request.mode == "edit"
    assert request.reference_video_urls == (VIDEO,)
    assert request.reference_image_urls == (PHOTO,)
    assert request.audio is False and request.seed == 0
    assert (
        request.duration == 15 and request.resolution == "480p" and request.aspect_ratio == "9:16"
    )
    assert harness.saved["wan30_billing"]["reserved_credits"] == 84
    assert harness.saved["wan30_request"]["reference_video_durations"] == [5.2]
    assert harness.saved["billing_total_seconds"] == 21
    assert harness.charge.await_args.args[2] == 84
    assert AUTHOR not in json.dumps(asdict(request)) and OUTPUT not in json.dumps(asdict(request))
    assert SECRET not in response.text and VIDEO not in response.text
    harness.refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["missing_media", "disabled_tariff", "stale_quote", "no_quote", "over_limit"]
)
async def test_wan_bad_repeat_never_debits_or_submits(harness, problem):
    recipe(harness, "wan/3-0-video")
    body = {"model": harness.source.model, "image_url": PHOTO, "quoted_credits": 84}
    if problem == "missing_media":
        harness.durations.clear()
    if problem == "disabled_tariff":
        harness.active = False
    if problem == "stale_quote":
        body["quoted_credits"] = 60
    if problem == "no_quote":
        body.pop("quoted_credits")
    if problem == "over_limit":
        harness.durations[VIDEO] = 16.0
    result = await harness.client.post("/api/v1/feed/77/remix", json=body)
    assert result.status_code == (409 if problem in {"stale_quote", "no_quote"} else 422), (
        result.text
    )
    harness.charge.assert_not_awaited()
    harness.save.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("mode", ["reference", "edit", "first", "first_last", "file", "link"])
async def test_wan_feed_keeps_slots_and_flags_without_author_photos(harness, model, mode):
    recipe(harness, model, mode=mode, videos=(VIDEO,) if mode == "edit" else ())
    snap = harness.source.input_params["wan30_request"]
    photos = [PHOTO]
    if mode == "first_last":
        photos.append("https://example.test/reader-last.png")
    if mode in {"first", "first_last"}:
        snap.update(
            reference_image_urls=[],
            first_frame_url=AUTHOR,
            last_frame_url=AUTHOR + "?end=1" if mode == "first_last" else None,
        )
    if mode == "file":
        snap["reference_file_urls"] = ["https://example.test/material.pdf"]
    if mode == "link":
        snap["reference_link_urls"] = ["https://example.test/material"]
    # Canonical-only history is valid: no top-level video alias required.
    harness.source.input_params = {"wan30_request": snap}
    body = {"model": model, "reference_urls": photos}
    quoted = await harness.client.post("/api/v1/feed/77/remix/quote", json=body)
    assert quoted.status_code == 200, quoted.text
    assert SECRET not in quoted.text and AUTHOR not in quoted.text and VIDEO not in quoted.text
    response = await harness.client.post(
        "/api/v1/feed/77/remix", json={**body, "quoted_credits": quoted.json()["cost_credits"]}
    )
    assert response.status_code == 202, response.text
    req = harness.submit.await_args.args[0]
    assert req.mode == mode
    assert req.audio is False and req.seed == 0
    assert req.reference_video_urls == ((VIDEO,) if mode == "edit" else ())
    assert req.first_frame_url == (PHOTO if mode in {"first", "first_last"} else None)
    assert req.last_frame_url == (photos[1] if mode == "first_last" else None)
    if mode not in {"first", "first_last"}:
        assert req.reference_image_urls == tuple(photos)
    assert AUTHOR not in str(asdict(req)) and OUTPUT not in str(asdict(req))


@pytest.mark.asyncio
async def test_multiple_original_video_and_audio_refs_remeasured_once(harness):
    second = "https://example.test/input-two.mp4"
    audio = "https://example.test/sound.wav"
    recipe(harness, "wan/3-0-video-prime", videos=(VIDEO, second, VIDEO))
    harness.source.input_params["wan30_request"].update(
        reference_audio_urls=[audio],
        reference_audio_durations=[999],
        reference_video_durations=[999, 999, 999],
    )
    harness.durations.update({second: 2.1, audio: 3})
    result = await harness.client.post(
        "/api/v1/feed/77/remix/quote", json={"model": harness.source.model, "image_url": PHOTO}
    )
    assert result.status_code == 200, result.text
    assert result.json()["billable_seconds"] == 23
    assert result.json()["cost_credits"] == 92
    assert harness.events.count("probe") == 3
    harness.charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_tariff_change_after_quote_requires_new_confirmation(harness):
    recipe(harness, "wan/3-0-video")
    body = {"model": harness.source.model, "image_url": PHOTO}
    quote = await harness.client.post("/api/v1/feed/77/remix/quote", json=body)
    harness.rate = 5
    response = await harness.client.post(
        "/api/v1/feed/77/remix", json={**body, "quoted_credits": quote.json()["cost_credits"]}
    )
    assert response.status_code == 409, response.text
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_price_rejected_even_with_no_video_ref(harness):
    recipe(harness, "wan/3-0-video", mode="reference", videos=())
    response = await harness.client.post(
        "/api/v1/feed/77/remix", json={"model": harness.source.model, "image_url": PHOTO}
    )
    assert response.status_code == 409
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_io_failure_returns_retryable_precharge_error(harness, monkeypatch):
    recipe(harness, "wan/3-0-video")
    monkeypatch.setattr(
        wan30_launch,
        "_duration_for_owned_media",
        AsyncMock(side_effect=OSError("synthetic storage failure")),
    )
    for suffix in ("/quote", ""):
        response = await harness.client.post(
            "/api/v1/feed/77/remix" + suffix,
            json={"model": harness.source.model, "image_url": PHOTO, "quoted_credits": 84},
        )
        assert response.status_code == 503, response.text
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
async def test_telegram_public_repeat_uses_the_same_recipe_and_quote(harness, monkeypatch, model):
    from api.wan30_feed_recipe import recipe_options
    from bot.handlers import video_gen

    recipe(harness, model)
    monkeypatch.setattr(video_gen, "_external_source_feed_id", AsyncMock(return_value=77))
    previous = {
        "mode": "image",
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "reference_video_url": OUTPUT,
    }
    for _ in range(2):  # Re-entering the confirmation path must preserve seed=0.
        prompt, photos, data, source_id = await video_gen._prepare_feed_video_inputs(
            session=harness.session,
            db_user=harness.user,
            source_feed_gen_id=77,
            model_key=model,
            prompt=SECRET,
            image_url=PHOTO,
            data=previous,
        )
        assert data["mode"] == "video" and data["duration"] == 15
        req = await wan30_launch.create_wan30_request(
            model=model,
            prompt=prompt,
            mode=data["mode"],
            image_urls=photos,
            video_url=data["reference_video_url"],
            duration=data["duration"],
            resolution=data["resolution"],
            aspect_ratio=data["aspect_ratio"],
            options=recipe_options(data),
        )
        quote = await wan30_launch.get_wan30_quote(harness.session, req)
        assert quote.credits == 84 and req.mode == "edit" and req.seed == 0 and req.audio is False
        assert req.reference_image_urls == (PHOTO,) and req.reference_video_urls == (VIDEO,)
        previous = data


@pytest.mark.asyncio
async def test_telegram_duration_choice_survives_restore_and_changes_fingerprint(harness, monkeypatch):
    from api.wan30_feed_recipe import recipe_options
    from bot.handlers import video_gen
    recipe(harness, "wan/3-0-video")
    monkeypatch.setattr(video_gen, "_external_source_feed_id", AsyncMock(return_value=77))
    fingerprints = []
    for duration in (15, 20):
        _, _, data, _ = await video_gen._prepare_feed_video_inputs(
            session=harness.session, db_user=harness.user, source_feed_gen_id=77,
            model_key=harness.source.model, prompt=SECRET, image_url=PHOTO,
            data={"duration": 5, "duration_override": duration},
        )
        assert data["duration"] == duration
        request = await wan30_launch.create_wan30_request(
            model=harness.source.model, prompt=SECRET, mode=data["mode"], image_urls=[PHOTO],
            video_url=data["reference_video_url"], duration=data["duration"], resolution=data["resolution"],
            aspect_ratio=data["aspect_ratio"], options=recipe_options(data),
        )
        quote = await wan30_launch.get_wan30_quote(harness.session, request)
        fingerprints.append(quote.stored_params())
    assert fingerprints[0] != fingerprints[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["kie", "neironych"])
async def test_unknown_paid_result_keeps_existing_recovery_without_refund_or_replay(
    harness, monkeypatch, provider
):
    from api.kieai_client import KieSubmissionOutcomeUnknown
    from api.neironych_seedance import NeironychSubmissionUnknown

    recipe(harness, "wan/3-0-video")
    ambiguous = (
        KieSubmissionOutcomeUnknown("synthetic response lost")
        if provider == "kie"
        else NeironychSubmissionUnknown("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "test-99")
    )
    harness.submit.side_effect = ambiguous
    recovery = AsyncMock(return_value=True)
    monkeypatch.setattr(routes.repo, "mark_kie_video_submission_unknown", recovery)
    monkeypatch.setattr(routes, "handle_submission_unknown", recovery)
    result = await harness.client.post(
        "/api/v1/feed/77/remix",
        json={
            "model": harness.source.model,
            "image_url": PHOTO,
            "quoted_credits": 84,
        },
    )
    assert result.status_code == 202, result.text
    recovery.assert_awaited_once()
    harness.submit.assert_awaited_once()
    harness.charge.assert_awaited_once()
    harness.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_confirmation_quotes_restored_settings_not_ui_defaults(harness, monkeypatch):
    from bot.handlers import video_gen

    recipe(harness, "wan/3-0-video")
    data = {
        "model_key": harness.source.model,
        "mode": "image",
        "duration": 5,
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "image_url": PHOTO,
        "reference_video_url": OUTPUT,
    }
    state = AsyncMock()
    state.get_data.return_value = data
    state.update_data.side_effect = lambda **values: data.update(values)
    monkeypatch.setattr(video_gen, "_external_source_feed_id", AsyncMock(return_value=77))
    monkeypatch.setattr(video_gen, "_video_reference_image_url", AsyncMock(return_value=PHOTO))
    monkeypatch.setattr(
        video_gen,
        "_resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
    )
    message = AsyncMock()
    launched = await video_gen._launch_video_generation_from_state(
        source_message=message,
        state=state,
        session=harness.session,
        db_user=harness.user,
        bot=AsyncMock(),
        prompt=SECRET,
        source_feed_gen_id=77,
        hidden_feed_prompt=True,
    )
    assert launched is False  # No confirmation yet, no debit/provider call.
    text = message.answer.await_args.args[0]
    assert "<b>84" in text and "<b>15" in text and "480p" in text
    assert data["wan30_quote"]["fingerprint"]
    first_quote = dict(data["wan30_quote"])
    data["duration_override"] = 20
    launched = await video_gen._launch_video_generation_from_state(
        source_message=message, state=state, session=harness.session, db_user=harness.user,
        bot=AsyncMock(), prompt=SECRET, source_feed_gen_id=77, hidden_feed_prompt=True,
        wan_confirmation_token=first_quote["token"],
    )
    assert launched is False
    assert data["wan30_quote"]["fingerprint"] != first_quote["fingerprint"]
    assert "<b>104" in message.answer.await_args.args[0]
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()
    assert SECRET not in str(message.answer.await_args)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("snapshot", [None, {}, {"wan30_request": "broken"}])
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_unknown_wan_source_never_quotes_rendered_output(harness, model, snapshot, surface):
    recipe(harness, model)
    harness.source.input_params = snapshot
    harness.durations[OUTPUT] = 5
    body = {"model": model, "image_url": PHOTO, "video_url": OUTPUT, "quoted_credits": 40}
    for suffix in ("/quote", ""):
        response = await harness.client.post(f"/api/{surface}/feed/77/remix" + suffix, json=body)
        assert response.status_code == 422, response.text
    assert not harness.events
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("snapshot", [None, {}, {"wan30_request": "broken"}])
async def test_bot_unknown_wan_source_does_not_substitute_output(
    harness, monkeypatch, model, snapshot
):
    from bot.handlers import video_gen
    from core.feed_remix_prompt import FeedRemixUnavailable

    recipe(harness, model)
    harness.source.input_params = snapshot
    monkeypatch.setattr(video_gen, "_external_source_feed_id", AsyncMock(return_value=77))
    with pytest.raises(FeedRemixUnavailable):
        await video_gen._prepare_feed_video_inputs(
            session=harness.session,
            db_user=harness.user,
            source_feed_gen_id=77,
            model_key=model,
            prompt=SECRET,
            image_url=PHOTO,
            data={"mode": "video", "reference_video_url": OUTPUT},
        )
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
async def test_bot_probe_failure_is_actionable_and_never_charges(
    harness, monkeypatch, model, error_type
):
    from bot.handlers import video_gen

    recipe(harness, model)
    state = AsyncMock()
    state.get_data.return_value = {
        "model_key": model,
        "mode": "image",
        "duration": 5,
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "reference_video_url": OUTPUT,
    }
    monkeypatch.setattr(video_gen, "_external_source_feed_id", AsyncMock(return_value=77))
    monkeypatch.setattr(video_gen, "_video_reference_image_url", AsyncMock(return_value=PHOTO))
    monkeypatch.setattr(
        wan30_launch,
        "_duration_for_owned_media",
        AsyncMock(side_effect=error_type("synthetic failure")),
    )
    message = AsyncMock()
    assert not await video_gen._launch_video_generation_from_state(
        source_message=message,
        state=state,
        session=harness.session,
        db_user=harness.user,
        bot=AsyncMock(),
        prompt=SECRET,
        source_feed_gen_id=77,
        hidden_feed_prompt=True,
    )
    text = message.answer.await_args.args[0]
    assert "не списаны" in text and "позже" in text
    assert SECRET not in text and VIDEO not in text
    harness.charge.assert_not_awaited()
    harness.submit.assert_not_awaited()
    harness.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(WAN30_MODELS))
@pytest.mark.parametrize("surface", ["v1", "web"])
@pytest.mark.parametrize("binding_outcome", ["bound", "deferred", "error"])
async def test_wan_feed_kie_only_submission_binds_durable_identity(
    harness, monkeypatch, model, surface, binding_outcome,
):
    """A KIE-only paid POST sets kie_started, never Neironych's started flag."""
    from core.seedance_reconciliation import persist_submission_result

    recipe(harness, model)
    context = SimpleNamespace(started=False, kie_started=False)
    monkeypatch.setattr(routes, "make_submission_context", lambda *a, **k: context)
    monkeypatch.setattr(routes, "persist_submission_result", persist_submission_result)
    mark_unknown = AsyncMock(return_value=True)
    monkeypatch.setattr(routes, "handle_submission_unknown", mark_unknown)
    marker = ("web:" if surface == "web" else "") + "kie-submit:99"
    canonical = ("web:" if surface == "web" else "") + "synthetic-wan-task"

    async def paid_submit(request, **kwargs):
        context.kie_started = True
        harness.record.task_id = marker
        harness.record.status = GenerationStatus.processing
        return SimpleNamespace(task_id="synthetic-wan-task", provider="kieai")

    harness.submit.side_effect = paid_submit

    async def bind(session, gen_id, provider_task_id):
        assert session is harness.session
        assert gen_id == harness.record.id
        assert provider_task_id == "synthetic-wan-task"
        assert harness.record.task_id == marker
        if binding_outcome == "error":
            raise RuntimeError("Synthetic commit acknowledgement lost")
        if binding_outcome == "deferred":
            return None
        harness.record.task_id = canonical
        return harness.record

    binder = AsyncMock(side_effect=bind)
    monkeypatch.setattr(routes.repo, "bind_kie_video_callback", binder)
    response = await harness.client.post(
        f"/api/{surface}/feed/77/remix",
        json={"model": model, "image_url": PHOTO, "quoted_credits": 84},
    )
    assert response.status_code == 202, response.text
    binder.assert_awaited_once_with(harness.session, harness.record.id, "synthetic-wan-task")
    assert harness.record.task_id == (canonical if binding_outcome == "bound" else marker)
    assert context.started is False and context.kie_started is True
    harness.submit.assert_awaited_once()
    harness.charge.assert_awaited_once()
    harness.refund.assert_not_awaited()
    routes.repo.update_generation_task.assert_not_awaited()
    if binding_outcome == "error":
        mark_unknown.assert_awaited_once_with(harness.session, harness.record.id, context)
    else:
        mark_unknown.assert_not_awaited()

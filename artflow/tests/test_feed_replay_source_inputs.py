"""A public video repeat replays the creator's input recipe, not the rendered MP4."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import seedance25_adapter
from api.miniapp_routes import _feed_card_out
from api.web.schemas import FeedCard
from bot.handlers import video_gen
from core import feed_remix_prompt
from db.models import GenerationType

pytest_plugins = ("tests.test_feed_remix_prompt_security",)

MODEL = seedance25_adapter.MODEL_KEY
USER = "https://example.test/visitor-photo.jpg"
AUTHOR_PHOTO = "https://example.test/author-photo.jpg"
RESULT_MP4 = "https://example.test/rendered-result.mp4"
AUTHOR_VIDEO = "https://example.test/original-input-video.mp4"
PROMPT = "A woman in a pearl jacket dances at dusk, with a cinematic camera move."


def origin(*, video_url=None):
    return {
        "mode": "multimodal",
        "image_url": AUTHOR_PHOTO,
        "reference_video_url": video_url,
        "duration": 10,
        "resolution": "480p",
        "aspect_ratio": "9:16",
    }


def test_origin_video_refs_include_only_author_input_not_rendered_result():
    source = SimpleNamespace(
        gen_type=GenerationType.video, result_url=RESULT_MP4, input_params=origin(),
    )
    assert feed_remix_prompt.original_feed_video_references(source) == []
    source.input_params = origin(video_url=AUTHOR_VIDEO)
    assert feed_remix_prompt.original_feed_video_references(source) == [AUTHOR_VIDEO]


@pytest.mark.asyncio
async def test_api_feed_video_created_from_photo_reuses_author_prompt_without_any_video(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.prompt = PROMPT
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(
        model=MODEL,
        image_url=USER,
        mode="multimodal",
        # Old clients submit the rendered MP4 here. Server must ignore it.
        video_url=RESULT_MP4,
        duration=10,
        aspect_ratio="9:16",
        resolution="480p",
    )
    quote = await api_launch.routes.quote_feed_remix(77, body, api_launch.session, api_launch.user)
    await api_launch.routes.remix_feed_post(77, body, api_launch.session, api_launch.user)
    submitted = api_launch.generate.await_args
    assert quote["cost_credits"] == 40
    assert submitted.args[1] == PROMPT
    assert submitted.kwargs["image_url"] == [USER]
    assert submitted.kwargs["reference_video_url"] is None
    saved = api_launch.save.await_args.kwargs["input_params"]
    assert saved["reference_video_url"] is None
    assert saved["duration"] == 10
    assert saved["aspect_ratio"] == "9:16"


@pytest.mark.asyncio
async def test_api_source_only_photo_repeat_cannot_inject_new_video_reference(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(model=MODEL, image_url=USER, video_url=AUTHOR_VIDEO)
    for fn in (api_launch.routes.quote_feed_remix, api_launch.routes.remix_feed_post):
        with pytest.raises(HTTPException) as exc:
            await fn(77, body, api_launch.session, api_launch.user)
        assert exc.value.status_code == 422
    api_launch.charge.assert_not_awaited()
    api_launch.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_feed_video_created_from_photo_reuses_author_prompt_no_video(video_launch):
    video_launch.source.model = MODEL
    video_launch.source.prompt = PROMPT
    video_launch.source.result_url = RESULT_MP4
    video_launch.source.input_params = origin()
    data = {
        **video_launch.data,
        "reference_video_url": RESULT_MP4,
        "feed_use_source_video_url": RESULT_MP4,
        "mode": "multimodal",
    }
    prompt, images, fixed, source_id = await video_gen._prepare_feed_video_inputs(
        session=video_launch.kwargs["session"],
        db_user=video_launch.kwargs["db_user"],
        source_feed_gen_id=77,
        model_key=MODEL,
        prompt=PROMPT,
        image_url=USER,
        data=data,
    )
    assert prompt == PROMPT
    assert images == [USER]
    assert fixed["reference_video_url"] is None
    assert fixed["feed_use_source_video_url"] is None
    assert source_id == 77


@pytest.mark.asyncio
async def test_bot_feed_video_uses_real_author_video_when_it_was_submitted(video_launch):
    video_launch.source.model = MODEL
    video_launch.source.prompt = PROMPT
    video_launch.source.result_url = RESULT_MP4
    video_launch.source.input_params = origin(video_url=AUTHOR_VIDEO)
    prompt, images, fixed, _ = await video_gen._prepare_feed_video_inputs(
        session=video_launch.kwargs["session"],
        db_user=video_launch.kwargs["db_user"],
        source_feed_gen_id=77,
        model_key=MODEL,
        prompt=PROMPT,
        image_url=USER,
        data={**video_launch.data, "reference_video_url": RESULT_MP4},
    )
    assert prompt == PROMPT
    assert images == [USER]
    assert fixed["reference_video_url"] == AUTHOR_VIDEO


@pytest.mark.asyncio
async def test_api_source_video_repeat_restores_creator_settings_before_quote(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(
        model=MODEL, image_url=USER, mode="text", duration=5,
        aspect_ratio="adaptive", resolution="720p",
    )
    quote = await api_launch.routes.quote_feed_remix(77, body, api_launch.session, api_launch.user)
    await api_launch.routes.remix_feed_post(77, body, api_launch.session, api_launch.user)
    submitted = api_launch.generate.await_args
    assert quote["cost_credits"] == 40
    assert submitted.kwargs["duration"] == 10
    assert submitted.kwargs["aspect_ratio"] == "9:16"
    assert submitted.kwargs["resolution"] == "480p"
    assert submitted.kwargs["reference_video_url"] is None


@pytest.mark.asyncio
async def test_api_source_video_repeat_rejects_switch_to_other_model(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(model="veo3_fast", image_url=USER)
    with pytest.raises(HTTPException) as raised:
        await api_launch.routes.quote_feed_remix(77, body, api_launch.session, api_launch.user)
    assert raised.value.status_code == 422
    api_launch.costs.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_feed_entry_does_not_stage_rendered_video_if_author_only_used_photo(monkeypatch):
    from bot.handlers import feed
    source = SimpleNamespace(
        id=77, model=MODEL, gen_type=GenerationType.video, prompt=PROMPT,
        input_params=origin(), result_url=RESULT_MP4,
    )
    monkeypatch.setattr(feed.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(feed.repo, "get_all_model_costs", AsyncMock(return_value=[]))
    call = SimpleNamespace(
        data="feed:use:77", message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock(),
    )
    state = AsyncMock()
    await feed.cb_feed_use(call, AsyncMock(), SimpleNamespace(id=42), state)
    params = state.update_data.await_args.kwargs
    assert params["feed_use_source_video_url"] is None
    assert params["feed_use_needs_video_reference"] is False


def test_feed_card_reports_only_public_recipe_capabilities_not_prompt():
    source = SimpleNamespace(
        id=77, user_id=99, model=MODEL, gen_type=GenerationType.video,
        prompt=PROMPT, result_url=RESULT_MP4, result_urls=None,
        likes_count=0, shares_count=0, created_at=datetime.now(timezone.utc),
        input_params=origin(), is_public_feed=True,
    )
    card = SimpleNamespace(generation=source, username="author", full_name=None,
                           aspect_ratio="9:16", remix_count=2, quality=None)
    mini = _feed_card_out(card, SimpleNamespace(id=42))
    web = FeedCard.from_feed_card(card).model_dump()
    for payload in (mini, web):
        assert payload["source_has_video_reference"] is False
        assert payload["original_duration"] == 10
        assert payload["original_aspect_ratio"] == "9:16"
        assert payload["original_resolution"] == "480p"
        assert "input_params" not in payload
        assert "reference_video_url" not in payload
    assert mini.get("prompt", "") == ""
    assert mini.get("prompt_visibility") == "hidden"
    source.input_params = origin(video_url=AUTHOR_VIDEO)
    assert _feed_card_out(card, None)["source_has_video_reference"] is True
    assert FeedCard.from_feed_card(card).source_has_video_reference is True


@pytest.mark.asyncio
async def test_api_photo_creator_replay_rejects_rendered_mp4_in_image_slots(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(model=MODEL, image_url=RESULT_MP4)
    with pytest.raises(HTTPException) as raised:
        await api_launch.routes.quote_feed_remix(77, body, api_launch.session, api_launch.user)
    assert raised.value.status_code == 422
    api_launch.charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_exact_replay_rejects_unrelated_control_tokens(api_launch):
    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    body = api_launch.routes.FeedRemixRequest(
        model=MODEL, image_url=USER, audio_ids=["__apix_seedance25:duration=30"],
    )
    with pytest.raises(HTTPException) as raised:
        await api_launch.routes.quote_feed_remix(77, body, api_launch.session, api_launch.user)
    assert raised.value.status_code == 422
    api_launch.charge.assert_not_awaited()


def test_source_provenance_is_unknown_if_no_input_snapshot():
    assert feed_remix_prompt.original_feed_video_references(
        SimpleNamespace(gen_type=GenerationType.video, result_url=RESULT_MP4, input_params=None)
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["kie", "neironych"])
async def test_creator_photo_replay_provider_payload_has_no_video_input(api_launch, monkeypatch, provider):
    """Provider contract: neither Kie nor Neironych receives the rendered MP4."""
    from api import neironych_seedance_runtime, video_runtime_fixes

    api_launch.source.gen_type = GenerationType.video
    api_launch.source.model = MODEL
    api_launch.source.prompt = PROMPT
    api_launch.source.result_url = RESULT_MP4
    api_launch.source.input_params = origin()
    service = api_launch.routes.video_service

    async def select_provider(_model, *, kie, neironych):
        return await (kie() if provider == "kie" else neironych())

    monkeypatch.setattr(video_runtime_fixes, "submit_seedance", select_provider)
    monkeypatch.setattr(video_runtime_fixes, "ensure_video_reference_aspect_url", lambda url, **kwargs: url)
    monkeypatch.setattr(service, "_prepare_video_reference_urls", AsyncMock(side_effect=lambda urls: urls))
    monkeypatch.setattr(service, "_prepare_reference_video_url", AsyncMock(side_effect=lambda url: url))
    captured = {}

    async def neironych_submit(**kwargs):
        captured.update(kwargs)
        return "synthetic-replay-task"

    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych_submit)
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "synthetic-replay-task"}})
    monkeypatch.setattr(service.kieai_client, "create_task", kie)

    async def dispatch(_model, prompt, **kwargs):
        return await video_runtime_fixes._seedance_generate(service, prompt, (), kwargs)

    api_launch.generate.side_effect = dispatch
    body = api_launch.routes.FeedRemixRequest(
        model=MODEL, image_url=USER, duration=5, resolution="720p",
    )
    await api_launch.routes.remix_feed_post(77, body, api_launch.session, api_launch.user)
    if provider == "kie":
        payload = kie.await_args.args[0]["input"]
        assert payload["reference_image_urls"] == [USER]
        assert not payload.get("reference_video_urls")
        assert payload["duration"] == 10
        assert payload["aspect_ratio"] == "9:16"
        assert payload["resolution"] == "480p"
        assert payload["prompt"] == PROMPT
    else:
        assert captured.get("reference_video_url") is None
        model_name, payload = neironych_seedance_runtime.build_product_payload(
            **{
                key: value for key, value in captured.items()
                if key not in {"idempotency_key", "submission_context"}
            },
            source_probe=None,
        )
        assert model_name
        assert payload.get("reference_videos") in (None, [])
        assert payload["reference_images"] == [{"url": USER}]
        assert payload["prompt"] == PROMPT
    assert RESULT_MP4 not in str(payload)

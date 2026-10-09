from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import genjutsu_adapter, seedance25_adapter, video_runtime_fixes
from bot.handlers import video_gen
from core.feed_remix_prompt import (
    FEED_REMIX_CONTEXT_KEY,
    build_feed_remix_prompt,
    feed_remix_context,
)
from db.models import GenerationType
from tests.test_feed_remix_prompt_security import (
    SECRET,
    SOURCE_IMAGE,
    USER_IMAGE,
)
from tests.test_feed_remix_prompt_security import (
    video_launch as _video_launch,
)

video_launch = _video_launch

MODEL = seedance25_adapter.MODEL_KEY
SOURCE_VIDEO = "https://example.test/public-source.mp4"


@pytest.fixture
def seedance_bot(video_launch, monkeypatch):
    fixture = video_launch
    fixture.data.update(model_key=MODEL, mode="multimodal", image_url=USER_IMAGE)
    previous = SimpleNamespace(
        id=88, user_id=42, prompt=SECRET, source_feed_gen_id=77, model=MODEL,
        input_params={},
    )
    fixture.previous = previous
    fixture.repo.get_generation_by_id.side_effect = (
        lambda _session, generation_id: previous if generation_id == 88 else fixture.source
    )
    monkeypatch.setattr("bot.handlers.genjutsu_replace.restore_result", AsyncMock(return_value=False))
    monkeypatch.setattr(
        video_gen, "_video_repeat_params_for_generation", AsyncMock(return_value=fixture.data),
    )
    monkeypatch.setattr(
        video_gen, "_video_reference_image_url",
        AsyncMock(side_effect=lambda *_args: fixture.data.get("image_url")),
    )
    fixture.events = []
    fixture.metadata = SimpleNamespace(width=1280, height=720, duration_seconds=6.2)

    async def probe(path, kind):
        assert path == Path("/tmp/feed-source-test.mp4")
        fixture.events.append("probe")
        return fixture.metadata

    fixture.probe = AsyncMock(side_effect=probe)
    monkeypatch.setattr(video_runtime_fixes, "probe_local_media", fixture.probe)
    monkeypatch.setattr(
        video_runtime_fixes, "local_upload_path_from_url",
        lambda url: Path("/tmp/feed-source-test.mp4") if url == SOURCE_VIDEO else None,
    )
    cost = SimpleNamespace(credits=4, display_name="Seedance", is_active=True)

    async def resolve_cost(*_args, **_kwargs):
        fixture.events.append("price")
        return cost

    async def spend(*_args, **_kwargs):
        fixture.events.append("charge")
        return True

    fixture.repo.resolve_video_model_cost.side_effect = resolve_cost
    fixture.repo.spend_credits.side_effect = spend
    fixture.call = SimpleNamespace(data="regen:video:88", answer=AsyncMock(), message=AsyncMock())

    async def run(operation):
        if operation == "launch":
            return await video_gen._launch_video_generation_from_state(
                **{**fixture.kwargs, "prompt": previous.prompt, "parent_generation_id": previous.id},
            )
        return await video_gen.cb_regen_video(
            fixture.call, fixture.kwargs["session"], fixture.kwargs["state"],
            fixture.kwargs["db_user"], fixture.kwargs["bot"],
        )

    fixture.run = run
    return fixture


def _trust_prompt(fixture, prompt):
    fixture.previous.prompt = prompt
    fixture.previous.input_params = {FEED_REMIX_CONTEXT_KEY: feed_remix_context(77, prompt)}


def _assert_no_charge(fixture):
    fixture.repo.resolve_video_model_cost.assert_not_awaited()
    fixture.repo.spend_credits.assert_not_awaited()
    fixture.repo.create_generation.assert_not_awaited()
    fixture.service.generate_video.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
@pytest.mark.parametrize("personalization", ["text", "photo"])
async def test_seedance_feed_source_image_uses_multimodal_without_author_text(
    seedance_bot, operation, personalization,
):
    fixture = seedance_bot
    fixture.source.gen_type = GenerationType.image
    fixture.source.result_url = SOURCE_IMAGE
    if personalization == "text":
        fixture.data["image_url"] = None
        _trust_prompt(fixture, build_feed_remix_prompt("", "make the coat blue", has_source_media=True))
    await fixture.run(operation)
    submitted = fixture.service.generate_video.await_args
    assert submitted is not None
    assert SECRET not in submitted.args[1]
    if personalization == "text":
        assert "make the coat blue" in submitted.args[1]
    assert video_gen._url_list(submitted.kwargs["image_url"]) == (
        [SOURCE_IMAGE, USER_IMAGE] if personalization == "photo" else [SOURCE_IMAGE]
    )
    assert not seedance25_adapter.is_explicit_video_edit_prompt(submitted.args[1])
    assert submitted.kwargs["reference_video_url"] is None
    fixture.probe.assert_not_awaited()
    assert fixture.repo.spend_credits.await_args.args[2] == 20
    saved = fixture.repo.create_generation.await_args
    assert SECRET not in saved.args[4]
    assert saved.kwargs["input_params"][FEED_REMIX_CONTEXT_KEY]["prompt"] == submitted.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
@pytest.mark.parametrize("personalization", ["text", "photo"])
async def test_seedance_feed_source_video_enters_edit_and_prices_actual_duration_first(
    seedance_bot, operation, personalization,
):
    fixture = seedance_bot
    if personalization == "text":
        fixture.data["image_url"] = None
        _trust_prompt(fixture, build_feed_remix_prompt("", "make the coat blue", has_source_media=True))
    await fixture.run(operation)
    submitted = fixture.service.generate_video.await_args
    assert submitted is not None
    assert submitted.args[1].startswith("Edit the video @Video1.")
    assert SECRET not in submitted.args[1]
    assert submitted.kwargs["reference_video_url"] == SOURCE_VIDEO
    assert submitted.kwargs["image_url"] == (USER_IMAGE if personalization == "photo" else None)
    assert not any("identity_transfer" in value for value in submitted.kwargs["audio_ids"] or [])
    assert "seedance_content_edit" not in submitted.kwargs
    assert submitted.kwargs["duration"] == 7
    assert submitted.kwargs["aspect_ratio"] == "adaptive"
    assert fixture.events == ["probe", "price", "charge"]
    assert fixture.repo.resolve_video_model_cost.await_args.kwargs["duration"] == 7
    assert fixture.repo.spend_credits.await_args.args[2] == 28
    saved = fixture.repo.create_generation.await_args
    assert saved.kwargs["input_params"]["duration"] == 7
    assert saved.kwargs["input_params"]["aspect_ratio"] == "adaptive"
    assert saved.kwargs["input_params"][FEED_REMIX_CONTEXT_KEY]["prompt"] == submitted.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
@pytest.mark.parametrize("extra", [
    {"reference_video_url": "https://example.test/other.mp4"},
    {"reference_video_url": [SOURCE_VIDEO, "https://example.test/other.mp4"]},
    {"audio_ids": ["__apix_seedance25:video_ref=https://example.test/other.mp4"]},
])
async def test_seedance_feed_extra_video_cannot_bypass_precharge_validation(seedance_bot, operation, extra):
    seedance_bot.data.update(extra)
    await seedance_bot.run(operation)
    _assert_no_charge(seedance_bot)
    seedance_bot.probe.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
@pytest.mark.parametrize("failure", ["missing", "nonlocal", "invalid_duration", "invalid_size", "probe_error"])
async def test_seedance_feed_invalid_video_fails_before_cost_or_charge(seedance_bot, operation, failure):
    fixture = seedance_bot
    if failure == "missing":
        fixture.source.result_url = None
    elif failure == "nonlocal":
        fixture.source.result_url = "https://elsewhere.test/not-local.mp4"
    elif failure == "invalid_duration":
        fixture.metadata.duration_seconds = 3
    elif failure == "invalid_size":
        fixture.metadata.width = 10
    else:
        fixture.probe.side_effect = RuntimeError("private ffprobe diagnostic")
    await fixture.run(operation)
    _assert_no_charge(fixture)
    messages = fixture.kwargs["source_message"].answer if operation == "launch" else fixture.call.answer
    assert messages.await_count == 1
    assert "private ffprobe diagnostic" not in messages.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
async def test_seedance_feed_repeated_safe_edits_keep_changes_and_dedup_source(seedance_bot, operation):
    fixture = seedance_bot
    safe_prompt = "Edit the video @Video1. Preserve the scene.\n\nmake the coat blue"
    _trust_prompt(fixture, safe_prompt)
    fixture.data.update(
        reference_video_url=[SOURCE_VIDEO, SOURCE_VIDEO],
        audio_ids=[f"__apix_seedance25:video_ref={SOURCE_VIDEO}", "__apix_seedance25:generate_audio=false"],
    )
    await fixture.run(operation)
    submitted = fixture.service.generate_video.await_args
    assert submitted is not None
    assert submitted.args[1] == safe_prompt
    assert submitted.kwargs["reference_video_url"] == SOURCE_VIDEO
    assert "__apix_seedance25:generate_audio=false" in submitted.kwargs["audio_ids"]
    assert submitted.kwargs["duration"] == 7
    assert fixture.events == ["probe", "price", "charge"]
    saved = fixture.repo.create_generation.await_args
    assert saved.kwargs["input_params"][FEED_REMIX_CONTEXT_KEY]["prompt"] == safe_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "regen"])
@pytest.mark.parametrize("source_reference", [SOURCE_VIDEO, [SOURCE_VIDEO, SOURCE_VIDEO]])
async def test_seedance_feed_plain_source_only_repeat_keeps_author_prompt(seedance_bot, operation, source_reference):
    fixture = seedance_bot
    fixture.data.update(image_url=None, reference_video_url=source_reference)
    await fixture.run(operation)
    submitted = fixture.service.generate_video.await_args
    assert submitted is not None
    assert submitted.args[1] == SECRET
    fixture.probe.assert_not_awaited()


@pytest.mark.parametrize("refs", [SOURCE_VIDEO, [SOURCE_VIDEO]])
def test_seedance_repeat_state_preserves_reference_video_type(refs):
    assert video_gen._video_state_from_repeat_params(MODEL, {"reference_video_url": refs})["reference_video_url"] == refs


@pytest.mark.asyncio
async def test_feed_video_source_keeps_existing_genjutsu_video_capability(seedance_bot, monkeypatch):
    fixture = seedance_bot
    monkeypatch.setitem(video_gen.VIDEO_CAPS, genjutsu_adapter.MOTION_MODEL, genjutsu_adapter.VIDEO_CAPS)
    prompt, image_url, data, source_id = await video_gen._prepare_feed_video_inputs(
        session=fixture.kwargs["session"], db_user=fixture.kwargs["db_user"],
        source_feed_gen_id=77, model_key=genjutsu_adapter.MOTION_MODEL, prompt=SECRET,
        image_url=USER_IMAGE, data={},
    )
    assert SECRET not in prompt
    assert image_url == USER_IMAGE
    assert data["reference_video_url"] == SOURCE_VIDEO
    assert source_id == 77

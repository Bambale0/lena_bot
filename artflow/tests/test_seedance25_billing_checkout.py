"""Seedance 2.5 normal routing and server-cost quote must never hide high tariff."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import video_reference_billing as billing
from api.seedance25_adapter import MODEL_KEY
from bot.handlers import video_gen


def test_seedance25_normal_launch_requires_price_confirmation_even_without_video():
    seconds = billing.VideoSeconds(output=5, references=0, billable=5, reference_count=0)
    assert video_gen._requires_video_price_confirmation(MODEL_KEY, seconds, None)
    assert not video_gen._requires_video_price_confirmation("bytedance/seedance-2", seconds, None)
    assert video_gen._requires_video_price_confirmation(
        "bytedance/seedance-2", seconds, "a-prior-token",
    )


@pytest.mark.asyncio
async def test_seedance25_1080p_quote_displays_quality_and_full_price():
    state = AsyncMock()
    message = SimpleNamespace(answer=AsyncMock())
    await video_gen._show_video_cost_quote(
        message, state, state_key="video_reference_quote",
        user_id=3, fingerprint="hash-3", duration=5,
        credits=65, resolution="1080p",
        callback_prefix="video_price_confirm:", context={"model_key": MODEL_KEY},
    )
    text = message.answer.await_args.args[0]
    assert "1080p" in text and "65" in text
    assert "5 сек" in text
    assert message.answer.await_args.kwargs["reply_markup"]


@pytest.mark.asyncio
async def test_seedance25_reference_quote_once_not_hidden_two_times(monkeypatch):
    from pathlib import Path
    path = Path("incoming.mp4")
    monkeypatch.setattr(billing, "local_upload_path_from_url", lambda _: path)
    probe = AsyncMock(return_value=SimpleNamespace(duration_seconds=7.5))
    monkeypatch.setattr(billing, "probe_local_media", probe)
    quote = await billing.measured_video_seconds({
        "duration": 5,
        "reference_video_url": ["https://apixbotai.com/static/upload/incoming.mp4"],
        "audio_ids": [
            "__apix_seedance25:video_ref=https://apixbotai.com/static/upload/incoming.mp4"
        ],
    }, per_second=True)
    assert (quote.output, quote.references, quote.billable, quote.reference_count) == (5, 8, 13, 1)
    assert video_gen._video_total_credits(MODEL_KEY, quote.billable, 7) == 91
    probe.assert_awaited_once()

@pytest.mark.asyncio
async def test_seedance25_plain_text_quote_before_any_actual_debit(monkeypatch):
    data = {
        "model_key": MODEL_KEY,
        "mode": "text",
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "adaptive",
        "credits": 7.0,
        "image_url": None, "audio_ids": [],
    }
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    async def update(**values):
        data.update(values)
    state.update_data = AsyncMock(side_effect=update)
    source = SimpleNamespace(answer=AsyncMock())
    user = SimpleNamespace(id=42, credits=500)
    monkeypatch.setattr(
        video_gen, "_video_reference_image_url", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        video_gen, "_resolve_video_model_cost", AsyncMock(
            return_value=SimpleNamespace(credits=7.0, is_active=True, display_name="Seedance 2.5"),
        ),
    )
    monkeypatch.setattr(
        video_gen, "_seedance_edit_duration_from_state", AsyncMock(return_value=None),
    )
    spent = AsyncMock()
    submitted = AsyncMock()
    monkeypatch.setattr(video_gen.repo, "spend_credits", spent)
    monkeypatch.setattr(video_gen.video_service, "generate_video", submitted)

    launched = await video_gen._launch_video_generation_from_state(
        source_message=source, state=state, session=AsyncMock(),
        db_user=user, bot=AsyncMock(), prompt="One winter train",
    )
    assert launched is False
    spent.assert_not_awaited()
    submitted.assert_not_awaited()
    confirmation = data["video_reference_quote"]
    assert confirmation["model_key"] == MODEL_KEY
    assert confirmation["token"]
    text = source.answer.await_args.args[0]
    assert "720p" in text and "35" in text
    assert "5 сек" in text


@pytest.mark.asyncio
async def test_seedance25_invalidated_quote_does_not_charge_user(monkeypatch):
    data = {
        "model_key": MODEL_KEY, "mode": "text", "duration": 5,
        "resolution": "720p", "aspect_ratio": "adaptive",
        "credits": 7.0, "audio_ids": [],
        "video_reference_quote": {
            "token": "expired_token", "user_id": 42,
            "fingerprint": "outdated_order", "model_key": MODEL_KEY,
        },
    }
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data)
    async def update(**values):
        data.update(values)
    state.update_data = AsyncMock(side_effect=update)
    source = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(video_gen, "_video_reference_image_url", AsyncMock(return_value=None))
    monkeypatch.setattr(video_gen, "_resolve_video_model_cost", AsyncMock(
        return_value=SimpleNamespace(credits=7.0, is_active=True, display_name="Seedance 2.5"),
    ))
    monkeypatch.setattr(
        video_gen, "_seedance_edit_duration_from_state", AsyncMock(return_value=None),
    )
    spend = AsyncMock()
    monkeypatch.setattr(video_gen.repo, "spend_credits", spend)
    assert await video_gen._launch_video_generation_from_state(
        source_message=source, state=state, session=AsyncMock(),
        db_user=SimpleNamespace(id=42, credits=500), bot=AsyncMock(),
        prompt="One winter train", price_confirmation_token="expired_token",
    ) is False
    spend.assert_not_awaited()
    assert data["video_reference_quote"]["token"] != "expired_token"

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes
from api import video_reference_billing as billing


@pytest.mark.asyncio
async def test_video_billable_seconds_sum_unique_reference_lengths_once(monkeypatch) -> None:
    durations = {"first.mp4": 4.2, "second.mp4": 2.3}
    monkeypatch.setattr(billing, "local_upload_path_from_url", lambda url: Path(url))
    probe = AsyncMock(side_effect=lambda path, _kind: SimpleNamespace(duration_seconds=durations[path.name]))
    monkeypatch.setattr(billing, "probe_local_media", probe)

    result = await billing.measured_video_seconds({
        "duration": 5,
        "reference_video_url": ["first.mp4", "second.mp4", "first.mp4"],
    }, per_second=True)

    assert (result.output, result.references, result.billable, result.reference_count) == (5, 7, 12, 2)
    assert probe.await_count == 2


@pytest.mark.asyncio
async def test_seedance_control_video_references_are_counted_without_mutating_payload(monkeypatch) -> None:
    monkeypatch.setattr(billing, "local_upload_path_from_url", lambda url: Path(url))
    monkeypatch.setattr(billing, "probe_local_media", AsyncMock(return_value=SimpleNamespace(duration_seconds=5)))
    normalized = {
        "duration": 8,
        "reference_video_url": ["first.mp4"],
        "audio_ids": ["__apix_seedance25:video_ref=second.mp4", "__apix_seedance25:video_ref=first.mp4"],
    }
    result = await billing.measured_video_seconds(normalized, per_second=True)
    assert (result.references, result.billable, result.reference_count) == (10, 18, 2)
    assert normalized["reference_video_url"] == ["first.mp4"]


@pytest.mark.asyncio
async def test_flat_video_tariff_does_not_add_reference_seconds(monkeypatch) -> None:
    monkeypatch.setattr(billing, "local_upload_path_from_url", lambda url: Path(url))
    probe = AsyncMock(return_value=SimpleNamespace(duration_seconds=4.2))
    monkeypatch.setattr(billing, "probe_local_media", probe)

    result = await billing.measured_video_seconds({
        "duration": 8, "reference_video_url": "input.mp4",
    }, per_second=False)

    assert (result.output, result.references, result.billable) == (8, 5, 8)
    probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_unmeasurable_reference_fails_before_payment(monkeypatch) -> None:
    monkeypatch.setattr(billing, "local_upload_path_from_url", lambda _url: None)

    with pytest.raises(ValueError, match="Загрузи видеореференс"):
        await billing.measured_video_seconds({
            "duration": 5, "reference_video_url": "https://remote.test/input.mp4",
        }, per_second=True)


@pytest.mark.asyncio
async def test_midjourney_video_quote_uses_flat_database_tariff(monkeypatch) -> None:
    tariff = SimpleNamespace(credits=24, is_active=True, model_key="midjourney-video")
    monkeypatch.setattr(miniapp_routes.repo, "get_model_cost", AsyncMock(return_value=tariff))
    quote = await miniapp_routes.quote_video_generation(
        body=miniapp_routes.VideoGenRequest(model="midjourney-video", prompt="Camera moves"),
        session=SimpleNamespace(),
        user=SimpleNamespace(credits=25),
    )
    assert (quote["cost_credits"], quote["reference_seconds"], quote["can_run"]) == (24, 0, True)

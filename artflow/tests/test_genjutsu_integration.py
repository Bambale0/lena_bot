from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api import genjutsu_adapter, higgsfield_client, miniapp_routes
from api.genjutsu_pricing import (
    MOTION_MODEL,
    OBJECT_MODEL,
    genjutsu_model_cost_rows,
)
from api.media_gateway import MediaProbe
from api.provider_contract_catalog import CONTRACTS_BY_ID
from api.provider_operation_registry import PollKind, get_operation_spec
from api.provider_smoke_manifest import SMOKE_CASES
from api.video_service import VideoModel
from bot.ui.model_labels import all_known_model_keys


def test_genjutsu_models_are_runtime_catalogued_and_publicly_named() -> None:
    assert VideoModel(MOTION_MODEL).value == MOTION_MODEL
    assert VideoModel(OBJECT_MODEL).value == OBJECT_MODEL
    assert MOTION_MODEL in all_known_model_keys()
    assert OBJECT_MODEL in all_known_model_keys()

    motion = CONTRACTS_BY_ID["video.genjutsu.motion"]
    obj = CONTRACTS_BY_ID["video.genjutsu.object"]
    assert motion.provider == "higgsfield"
    assert obj.provider == "higgsfield"
    assert motion.telegram and motion.miniapp
    assert obj.telegram and obj.miniapp
    assert "video.genjutsu.motion" in SMOKE_CASES
    assert "video.genjutsu.object" in SMOKE_CASES

    assert get_operation_spec("video.genjutsu.motion").poll_kind == PollKind.HIGGSFIELD
    assert get_operation_spec("video.genjutsu.object").poll_kind == PollKind.HIGGSFIELD


def test_genjutsu_configuration_requires_key_pair(monkeypatch) -> None:
    monkeypatch.setattr(genjutsu_adapter.settings, "HIGGSFIELD_CREDENTIALS", "")
    assert genjutsu_adapter.is_genjutsu_configured() is False

    monkeypatch.setattr(
        genjutsu_adapter.settings,
        "HIGGSFIELD_CREDENTIALS",
        "key-id:key-secret",
    )
    assert genjutsu_adapter.is_genjutsu_configured() is True


def test_genjutsu_miniapp_surface_is_hidden_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(genjutsu_adapter.settings, "HIGGSFIELD_CREDENTIALS", "")
    monkeypatch.setattr(genjutsu_adapter, "install_genjutsu_provider_support", lambda: None)
    monkeypatch.setattr(genjutsu_adapter, "_install_miniapp_normalizer", lambda _routes: None)
    monkeypatch.setattr(genjutsu_adapter, "_install_miniapp_reconciler", lambda _routes: None)

    class Routes:
        VIDEO_CAPS = {
            MOTION_MODEL: {"requires_video_input": True},
            OBJECT_MODEL: {"requires_video_input": True},
            "existing/model": {},
        }
        _VIDEO_MODEL_ORDER = [MOTION_MODEL, "existing/model", OBJECT_MODEL]

    genjutsu_adapter.install_genjutsu_miniapp(Routes)

    assert MOTION_MODEL not in Routes.VIDEO_CAPS
    assert OBJECT_MODEL not in Routes.VIDEO_CAPS
    assert Routes._VIDEO_MODEL_ORDER == ["existing/model"]


def test_genjutsu_pricing_is_admin_backed_per_resolution() -> None:
    rows = genjutsu_model_cost_rows()
    keys = {row["model_key"] for row in rows}
    assert MOTION_MODEL in keys
    assert OBJECT_MODEL in keys
    assert f"{MOTION_MODEL}__resolution=480p" in keys
    assert f"{MOTION_MODEL}__resolution=720p" in keys
    assert f"{OBJECT_MODEL}__resolution=480p" in keys
    assert f"{OBJECT_MODEL}__resolution=720p" in keys


def test_validate_inputs_requires_source_video_and_limits_refs() -> None:
    with pytest.raises(ValueError, match="at least one reference image"):
        genjutsu_adapter.validate_inputs(
            image_urls=[],
            video_url="https://example.test/source.mp4",
            resolution="480p",
        )

    with pytest.raises(ValueError, match="at most 8"):
        genjutsu_adapter.validate_inputs(
            image_urls=[f"https://example.test/{idx}.jpg" for idx in range(9)],
            video_url="https://example.test/source.mp4",
            resolution="480p",
        )

    with pytest.raises(ValueError, match="source video"):
        genjutsu_adapter.validate_inputs(
            image_urls=["https://example.test/ref.jpg"],
            video_url=None,
            resolution="480p",
        )


@pytest.mark.asyncio
async def test_source_duration_is_measured_and_rounded_up(monkeypatch) -> None:
    from api import media_gateway

    monkeypatch.setattr(
        genjutsu_adapter,
        "local_upload_path_from_url",
        lambda _url: Path("/tmp/source.mp4"),
    )
    monkeypatch.setattr(
        media_gateway,
        "probe_local_media",
        AsyncMock(return_value=MediaProbe(duration_seconds=4.01)),
    )

    assert await genjutsu_adapter.resolve_source_duration_seconds(
        "https://apix.example/static/upload/source.mp4"
    ) == 5


@pytest.mark.asyncio
async def test_source_duration_rejects_unowned_external_url(monkeypatch) -> None:
    monkeypatch.setattr(genjutsu_adapter, "local_upload_path_from_url", lambda _url: None)
    with pytest.raises(ValueError, match="must be uploaded to APIX"):
        await genjutsu_adapter.resolve_source_duration_seconds(
            "https://third-party.example/source.mp4"
        )


@pytest.mark.asyncio
async def test_motion_transfer_sends_exact_provider_payload(monkeypatch) -> None:
    submit = AsyncMock(return_value="hf-task-1")
    monkeypatch.setattr(genjutsu_adapter.higgsfield_client, "submit", submit)
    monkeypatch.setattr(
        genjutsu_adapter.settings,
        "HIGGSFIELD_GENJUTSU_MOTION_ENDPOINT",
        "higgsfield/genjutsu/motion-transfer/v1.0",
    )

    result = await genjutsu_adapter.create_motion_transfer(
        prompt="Replace the actor with @Image1",
        video_url="https://example.test/source.mp4",
        image_urls=["https://example.test/ref.jpg"],
        resolution="720p",
    )

    assert result.task_id == "hf-task-1"
    assert result.provider == "higgsfield"
    assert result.uses_webhook is False
    submit.assert_awaited_once_with(
        "higgsfield/genjutsu/motion-transfer/v1.0",
        {
            "prompt": "Replace the actor with @Image1",
            "video_url": "https://example.test/source.mp4",
            "image_urls": ["https://example.test/ref.jpg"],
            "resolution": "720p",
        },
    )


@pytest.mark.asyncio
async def test_higgsfield_poll_maps_terminal_states(monkeypatch) -> None:
    monkeypatch.setattr(
        higgsfield_client,
        "get_status",
        AsyncMock(
            return_value={
                "status": "completed",
                "request_id": "hf-task-1",
                "video": {"url": "https://cdn.example/result.mp4"},
            }
        ),
    )
    assert (
        await higgsfield_client.poll_video_status("hf-task-1")
        == "https://cdn.example/result.mp4"
    )

    monkeypatch.setattr(
        higgsfield_client,
        "get_status",
        AsyncMock(return_value={"status": "nsfw", "detail": "blocked"}),
    )
    with pytest.raises(higgsfield_client.HiggsfieldError, match="nsfw"):
        await higgsfield_client.poll_video_status("hf-task-2")


@pytest.mark.asyncio
async def test_completed_genjutsu_result_is_mirrored_locally(monkeypatch) -> None:
    monkeypatch.setattr(
        genjutsu_adapter.higgsfield_client,
        "poll_video_status",
        AsyncMock(return_value="https://provider.example/result.mp4"),
    )
    mirror = AsyncMock(return_value="https://apix.example/static/upload/provider-results/result.mp4")
    monkeypatch.setattr(genjutsu_adapter, "mirror_url", mirror)

    url = await genjutsu_adapter.poll_genjutsu_video("hf-task-3")

    assert url == "https://apix.example/static/upload/provider-results/result.mp4"
    mirror.assert_awaited_once_with(
        "https://provider.example/result.mp4",
        subdir="provider-results",
    )


def test_miniapp_contract_requires_both_refs_and_source_video() -> None:
    with pytest.raises(miniapp_routes.HTTPException) as missing_video:
        miniapp_routes._normalize_video_request(
            model_key=MOTION_MODEL,
            mode="image",
            duration=5,
            aspect_ratio=None,
            resolution="480p",
            image_url="https://example.test/ref.jpg",
            reference_urls=[],
            video_url=None,
        )
    assert missing_video.value.status_code == 422

    normalized = miniapp_routes._normalize_video_request(
        model_key=MOTION_MODEL,
        mode="image",
        duration=5,
        aspect_ratio=None,
        resolution="720p",
        image_url="https://example.test/ref.jpg",
        reference_urls=["https://example.test/ref2.jpg"],
        video_url="https://example.test/source.mp4",
    )
    assert normalized["mode"] == "image"
    assert normalized["reference_video_url"] == "https://example.test/source.mp4"
    assert normalized["resolution"] == "720p"
    assert normalized["image_url"] == [
        "https://example.test/ref.jpg",
        "https://example.test/ref2.jpg",
    ]


def test_user_surfaces_render_genjutsu_media_requirements() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")
    types = (root / "webapp/src/lib/types.ts").read_text(encoding="utf-8")
    telegram = (root / "bot/handlers/video_gen.py").read_text(encoding="utf-8")

    assert "requires_video_input?: boolean" in types
    assert "requires_reference_images?: boolean" in types
    assert "duration_from_source?: boolean" in types
    assert "selectedModel?.requires_video_input" in frontend
    assert "!selectedModel?.duration_from_source && durations.length" in frontend
    assert "is_genjutsu_video_mode" in telegram
    assert "resolve_genjutsu_source_duration" in telegram

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api import neironych_seedance_runtime, seedance25_adapter, video_service
from api.video_runtime_fixes import install_video_runtime_fixes
from core.config import Settings, settings


@pytest.fixture(autouse=True)
def kie_primary_mode(monkeypatch):
    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "kieai")


def test_neironych_task_id_round_trip() -> None:
    encoded = neironych_seedance_runtime.encode_task_id("req-123")
    assert encoded == "neironych:req-123"
    assert neironych_seedance_runtime.is_task_id(encoded) is True
    assert neironych_seedance_runtime.decode_task_id(encoded) == "req-123"


@pytest.mark.asyncio
async def test_seedance2_uses_kie_primary_and_does_not_call_neironych(monkeypatch) -> None:
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-123"}})
    neironych = AsyncMock(return_value="neur-should-not-run")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)

    result = await video_service.generate_video(
        video_service.VideoModel.SEEDANCE_2,
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-42",
    )

    assert result.task_id == "kie-123"
    assert result.provider == "kieai"
    assert kie.await_args.args[0]["model"] == "bytedance/seedance-2"
    neironych.assert_not_awaited()


@pytest.mark.asyncio
async def test_seedance2_falls_back_to_neironych_when_kie_fails(monkeypatch) -> None:
    kie = AsyncMock(side_effect=RuntimeError("kie unavailable"))
    neironych = AsyncMock(return_value="neur-123")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)

    result = await video_service.generate_video(
        video_service.VideoModel.SEEDANCE_2,
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-42",
    )

    assert result.task_id == "neironych:neur-123"
    assert result.provider == "neironych"
    kie.assert_awaited_once()
    assert neironych.await_args.kwargs["idempotency_key"] == "apix-video-42"


@pytest.mark.asyncio
async def test_seedance25_uses_kie_primary_and_does_not_call_neironych(monkeypatch) -> None:
    install_video_runtime_fixes()
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-25"}})
    neironych = AsyncMock(return_value="neur-should-not-run")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-25",
    )

    assert result.task_id == "kie-25"
    assert result.provider == "kieai"
    assert kie.await_args.args[0]["model"] == seedance25_adapter.MODEL_KEY
    neironych.assert_not_awaited()


@pytest.mark.asyncio
async def test_seedance25_falls_back_to_neironych_when_kie_fails(monkeypatch) -> None:
    install_video_runtime_fixes()
    kie = AsyncMock(side_effect=RuntimeError("kie unavailable"))
    neironych = AsyncMock(return_value="neur-25")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "animate",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        idempotency_key="apix-video-25",
    )

    assert result.task_id == "neironych:neur-25"
    assert result.provider == "neironych"
    kie.assert_awaited_once()
    assert neironych.await_args.kwargs["idempotency_key"] == "apix-video-25"


def test_seedance_primary_setting_defaults_to_neironych_and_rejects_unknown_provider(monkeypatch):
    monkeypatch.delenv("SEEDANCE_PRIMARY_PROVIDER", raising=False)
    assert Settings(_env_file=None).SEEDANCE_PRIMARY_PROVIDER == "neironych"
    with pytest.raises(ValidationError, match="SEEDANCE_PRIMARY_PROVIDER"):
        Settings(_env_file=None, SEEDANCE_PRIMARY_PROVIDER="comet")


@pytest.mark.parametrize("provider", ["kieai", "neironych"])
def test_seedance_primary_environment_overrides_default(monkeypatch, provider):
    monkeypatch.setenv("SEEDANCE_PRIMARY_PROVIDER", provider)
    assert Settings(_env_file=None).SEEDANCE_PRIMARY_PROVIDER == provider


@pytest.mark.asyncio
@pytest.mark.parametrize("model_key", ["bytedance/seedance-2", seedance25_adapter.MODEL_KEY])
@pytest.mark.parametrize("primary_fails", [False, True])
async def test_seedance_neironych_order_can_be_restored(monkeypatch, model_key, primary_fails):
    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    neironych = AsyncMock(
        side_effect=RuntimeError("neironych unavailable") if primary_fails else None,
        return_value="neur-restored",
    )
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-secondary"}})
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)

    result = await video_service.generate_video(video_service.VideoModel(model_key), "animate")

    assert result.provider == ("kieai" if primary_fails else "neironych")
    assert result.task_id == ("kie-secondary" if primary_fails else "neironych:neur-restored")
    neironych.assert_awaited_once()
    if primary_fails:
        kie.assert_awaited_once()
    else:
        kie.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model_key", ["bytedance/seedance-2", seedance25_adapter.MODEL_KEY])
async def test_seedance_reports_both_submission_failures(monkeypatch, model_key):
    kie = AsyncMock(return_value={"code": 503, "msg": "kie unavailable"})
    neironych = AsyncMock(side_effect=RuntimeError("neironych unavailable"))
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)

    with pytest.raises(RuntimeError, match="primary kieai and neironych fallback") as error:
        await video_service.generate_video(video_service.VideoModel(model_key), "animate")

    assert "kie unavailable" in str(error.value)
    assert "neironych unavailable" in str(error.value)
    kie.assert_awaited_once()
    neironych.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["reference", "content_edit", "identity"])
async def test_seedance25_kie_primary_preserves_media_roles_and_callback(monkeypatch, mode):
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-media"}})
    neironych = AsyncMock(return_value="should-not-run")
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    kwargs = {}
    if mode == "content_edit":
        kwargs = {
            "seedance_reference_roles": ["identity_primary", "clothing"],
            "seedance_content_edit": {"number": "25", "clothing": "red cotton"},
        }
    images = ["https://example.test/face.jpg", "https://example.test/shirt.jpg"]
    audio = "https://example.test/voice.mp3"
    tokens = [audio] if mode == "reference" else []
    if mode == "identity":
        tokens = ["__apix_seedance25:identity_transfer=true"]

    result = await video_service.generate_video(
        video_service.VideoModel(seedance25_adapter.MODEL_KEY),
        "use the source motion",
        image_url=images,
        reference_video_url=["https://example.test/source.mp4"],
        audio_ids=tokens,
        duration=10,
        aspect_ratio="9:16",
        resolution="480p",
        callback_url="https://example.test/callback",
        **kwargs,
    )

    payload = kie.await_args.args[0]
    assert payload["model"] == seedance25_adapter.MODEL_KEY
    data = payload["input"]
    assert data["reference_image_urls"] == images
    assert data["reference_video_urls"] == ["https://example.test/source.mp4"]
    assert data["resolution"] == "480p"
    assert data["duration"] == (10 if mode == "reference" else -1)
    assert data["aspect_ratio"] == ("9:16" if mode == "reference" else "adaptive")
    if mode == "reference":
        assert data["reference_audio_urls"] == [audio]
        assert data["prompt"] == "use the source motion"
    elif mode == "content_edit":
        assert "@Image2 is the clothing" in data["prompt"]
        assert 'must read exactly "25"' in data["prompt"]
    else:
        assert "@Image1" in data["prompt"] and "@Video1" in data["prompt"]
        assert data["generate_audio"] is False
    assert kie.await_args.kwargs["callback_url"] == "https://example.test/callback"
    assert result.provider == "kieai" and result.uses_webhook is True
    neironych.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kie_fails", [False, True])
async def test_seedance25_legacy_service_wrapper_uses_same_provider_order(monkeypatch, kie_fails):
    kie = AsyncMock(
        side_effect=RuntimeError("kie unavailable") if kie_fails else None,
        return_value={"code": 200, "data": {"taskId": "kie-legacy"}},
    )
    neironych = AsyncMock(return_value="neur-legacy")
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)
    service = SimpleNamespace(
        VideoModel=video_service.VideoModel,
        VideoResult=video_service.VideoResult,
        generate_video=AsyncMock(),
        kieai_client=SimpleNamespace(create_task=kie),
        _prepare_video_reference_urls=AsyncMock(return_value=[]),
    )
    seedance25_adapter._install_seedance25_generate_wrapper(service)

    result = await service.generate_video(video_service.VideoModel(seedance25_adapter.MODEL_KEY), "animate")

    assert result.provider == ("neironych" if kie_fails else "kieai")
    kie.assert_awaited_once()
    if kie_fails:
        neironych.assert_awaited_once()
    else:
        neironych.assert_not_awaited()


@pytest.fixture(autouse=True)
def isolate_seedance_admission(monkeypatch):
    # These tests cover provider payloads, not live Redis coordination.
    from unittest.mock import AsyncMock

    from api import seedance_provider_routing
    monkeypatch.setattr(seedance_provider_routing, "neironych_route_paused", AsyncMock(return_value=False))


@pytest.fixture
def default_primary_mode(monkeypatch, kie_primary_mode):
    monkeypatch.delenv("SEEDANCE_PRIMARY_PROVIDER", raising=False)
    default_settings = Settings(_env_file=None)
    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", default_settings.SEEDANCE_PRIMARY_PROVIDER)


@pytest.mark.asyncio
@pytest.mark.parametrize("model_key", ["bytedance/seedance-2", seedance25_adapter.MODEL_KEY])
@pytest.mark.parametrize("primary_fails", [False, True])
async def test_seedance_default_routes_neironych_then_kie(
    monkeypatch, default_primary_mode, model_key, primary_fails,
):
    install_video_runtime_fixes()
    calls = []

    async def submit_neironych(**kwargs):
        calls.append("neironych")
        assert kwargs["product_model"] == model_key
        assert kwargs["idempotency_key"] == "default-route"
        if primary_fails:
            raise RuntimeError("neironych unavailable")
        return "neur-default"

    async def submit_kie(payload, **kwargs):
        calls.append("kieai")
        assert payload["model"] == model_key
        return {"code": 200, "data": {"taskId": "kie-fallback"}}

    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", submit_neironych)
    monkeypatch.setattr(video_service.kieai_client, "create_task", submit_kie)
    result = await video_service.generate_video(
        video_service.VideoModel(model_key), "animate", idempotency_key="default-route",
    )

    assert calls == (["neironych", "kieai"] if primary_fails else ["neironych"])
    assert result.provider == ("kieai" if primary_fails else "neironych")
    assert result.task_id == ("kie-fallback" if primary_fails else "neironych:neur-default")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [video_service.VideoModel.SEEDANCE_2_FAST, video_service.VideoModel.SEEDANCE_2_MINI])
async def test_seedance_fast_mini_still_use_kie_with_default_primary(
    monkeypatch, default_primary_mode, model,
):
    kie = AsyncMock(return_value={"code": 200, "data": {"taskId": "kie-fast-mini"}})
    neironych = AsyncMock()
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie)
    monkeypatch.setattr(neironych_seedance_runtime, "generate_product_video", neironych)

    result = await video_service.generate_video(model, "animate")

    assert result.provider == "kieai"
    assert result.task_id == "kie-fast-mini"
    assert kie.await_args.args[0]["model"] == model.value
    neironych.assert_not_awaited()

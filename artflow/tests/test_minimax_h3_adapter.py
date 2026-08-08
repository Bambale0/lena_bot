from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import minimax_h3_adapter as h3
from api import video_service
from api.minimax_h3_pricing import (
    T2V_RESOLUTION_CREDITS,
    credits_per_second,
    minimax_h3_model_cost_rows,
)


def test_h3_public_caps_match_official_model_spec() -> None:
    caps = h3.PUBLIC_CAPS
    assert caps["modes"] == ["text", "image", "video"]
    assert caps["duration_options"] == list(range(4, 16))
    assert caps["resolutions"] == ["2K", "768P"]
    assert caps["aspect_ratios"] == ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
    assert caps["max_refs"] == 9
    assert caps["max_reference_videos"] == 3
    assert caps["max_reference_audios"] == 3
    assert caps["max_reference_files"] == 12
    assert caps["native_audio"] is True
    assert caps["auto_route_by_inputs"] is True
    assert "max_audio_ids" not in caps
    assert "max_character_ids" not in caps


@pytest.mark.parametrize(
    ("images", "videos", "audios", "expected"),
    [
        ([], [], [], h3.T2V_MODEL),
        (["a.jpg"], [], [], h3.I2V_MODEL),
        (["a.jpg", "b.jpg"], [], [], h3.I2V_MODEL),
        (["a.jpg", "b.jpg", "c.jpg"], [], [], h3.REFERENCE_MODEL),
        (["a.jpg"], ["motion.mp4"], [], h3.REFERENCE_MODEL),
        (["a.jpg"], [], ["voice.wav"], h3.REFERENCE_MODEL),
    ],
)
def test_h3_route_is_inferred_from_actual_inputs(images, videos, audios, expected) -> None:
    assert h3.route_for_inputs(images=images, videos=videos, audios=audios) == expected


def test_h3_reference_limits_match_official_spec() -> None:
    h3.validate_reference_set(
        images=[f"{index}.jpg" for index in range(6)],
        videos=[f"{index}.mp4" for index in range(3)],
        audios=[f"{index}.wav" for index in range(3)],
    )
    with pytest.raises(ValueError, match="at most 9 reference images"):
        h3.validate_reference_set(images=[f"{index}.jpg" for index in range(10)], videos=[], audios=[])
    with pytest.raises(ValueError, match="at most 3 reference videos"):
        h3.validate_reference_set(images=["a.jpg"], videos=[f"{index}.mp4" for index in range(4)], audios=[])
    with pytest.raises(ValueError, match="at most 3 reference audio"):
        h3.validate_reference_set(images=["a.jpg"], videos=[], audios=[f"{index}.wav" for index in range(4)])
    with pytest.raises(ValueError, match="at most 12 mixed"):
        h3.validate_reference_set(
            images=[f"{index}.jpg" for index in range(8)],
            videos=[f"{index}.mp4" for index in range(3)],
            audios=[f"{index}.wav" for index in range(2)],
        )
    with pytest.raises(ValueError, match="accompanied by an image or video"):
        h3.validate_reference_set(images=[], videos=[], audios=["voice.wav"])


def test_h3_t2v_payload_has_full_quality_duration_and_ratio() -> None:
    assert h3._t2v_input(
        prompt="cinematic city",
        duration=15,
        aspect_ratio="21:9",
        resolution="2K",
    ) == {
        "prompt": "cinematic city",
        "duration": 15,
        "aspect_ratio": "21:9",
        "resolution": "2K",
    }


def test_h3_i2v_payload_maps_one_or_two_images_to_frames() -> None:
    assert h3._i2v_input(
        prompt="move naturally",
        duration=8,
        resolution="768P",
        images=["https://example.test/first.jpg", "https://example.test/last.jpg"],
    ) == {
        "prompt": "move naturally",
        "duration": 8,
        "resolution": "768P",
        "first_frame_url": "https://example.test/first.jpg",
        "last_frame_url": "https://example.test/last.jpg",
    }


def test_h3_reference_payload_supports_all_modalities_and_quality() -> None:
    assert h3._reference_input(
        prompt="keep the character consistent",
        duration=12,
        aspect_ratio="adaptive",
        resolution="2K",
        images=["https://example.test/character.jpg"],
        videos=["https://example.test/motion.mp4"],
        audios=["https://example.test/voice.wav"],
    ) == {
        "prompt": "keep the character consistent",
        "duration": 12,
        "aspect_ratio": "adaptive",
        "resolution": "2K",
        "reference_image_urls": ["https://example.test/character.jpg"],
        "reference_video_urls": ["https://example.test/motion.mp4"],
        "reference_audio_urls": ["https://example.test/voice.wav"],
    }


def test_h3_duration_and_quality_are_safely_normalized() -> None:
    assert h3._duration(2) == 4
    assert h3._duration(99) == 15
    assert h3._resolution("768p") == "768P"
    assert h3._resolution("2K") == "2K"


def test_h3_internal_provider_models_remain_registered() -> None:
    assert video_service.VideoModel(h3.T2V_MODEL).value == h3.T2V_MODEL
    assert video_service.VideoModel(h3.I2V_MODEL).value == h3.I2V_MODEL
    assert video_service.VideoModel(h3.REFERENCE_MODEL).value == h3.REFERENCE_MODEL


def test_h3_pricing_has_public_quality_variants() -> None:
    rows = minimax_h3_model_cost_rows()
    keys = {row["model_key"] for row in rows}
    assert h3.T2V_MODEL in keys
    assert h3.I2V_MODEL in keys
    assert h3.REFERENCE_MODEL in keys
    assert len(rows) == 3 + len(T2V_RESOLUTION_CREDITS)
    for model in h3.MODEL_KEYS:
        assert credits_per_second(model, resolution="768P") == 10
        assert credits_per_second(model, resolution="2K") == 14


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _fake_routes():
    def normalize_urls(*urls):
        return [str(url) for url in urls if str(url or "").strip()]

    def original(**kwargs):
        return kwargs

    return SimpleNamespace(
        _normalize_video_request=original,
        _normalize_public_urls=normalize_urls,
        HTTPException=_FakeHTTPException,
        VIDEO_CAPS={},
        _VIDEO_MODEL_ORDER=[],
        _FRIENDLY_MODEL_NAMES={},
    )


def _normalize(routes, **overrides):
    body = dict(
        model_key=h3.PUBLIC_MODEL,
        mode="text",
        duration=6,
        aspect_ratio="adaptive",
        resolution="2K",
        image_url=None,
        reference_urls=[],
        video_url=None,
        audio_ids=[],
        character_ids=[],
        video_start=None,
        video_end=None,
        seed=None,
        grok_mode=None,
    )
    body.update(overrides)
    return routes._normalize_video_request(**body)


def test_h3_miniapp_uses_one_public_model_and_auto_routes(monkeypatch) -> None:
    routes = _fake_routes()
    monkeypatch.setattr(h3, "install_minimax_h3_provider_support", lambda: None)
    h3.install_minimax_h3_miniapp(routes)

    text = _normalize(routes)
    assert text["provider_model"] == h3.T2V_MODEL
    assert text["mode"] == "text"
    assert text["aspect_ratio"] == "16:9"  # adaptive is invalid for T2V
    assert text["resolution"] == "2K"

    one_frame = _normalize(routes, image_url="https://example.test/first.jpg")
    assert one_frame["provider_model"] == h3.I2V_MODEL
    assert one_frame["mode"] == "image"
    assert one_frame["aspect_ratio"] is None

    first_last = _normalize(
        routes,
        image_url="https://example.test/first.jpg",
        reference_urls=["https://example.test/last.jpg"],
    )
    assert first_last["provider_model"] == h3.I2V_MODEL
    assert first_last["image_url"] == [
        "https://example.test/first.jpg",
        "https://example.test/last.jpg",
    ]

    reference = _normalize(
        routes,
        image_url="https://example.test/person.jpg",
        video_url="https://example.test/motion.mp4",
        audio_ids=["https://example.test/voice.wav"],
    )
    assert reference["provider_model"] == h3.REFERENCE_MODEL
    assert reference["mode"] == "video"
    assert reference["reference_video_url"] == ["https://example.test/motion.mp4"]
    assert reference["audio_ids"] == ["https://example.test/voice.wav"]
    assert reference["aspect_ratio"] == "adaptive"

    assert routes.VIDEO_CAPS[h3.PUBLIC_MODEL]["resolutions"] == ["2K", "768P"]
    assert h3.I2V_MODEL not in routes._VIDEO_MODEL_ORDER
    assert h3.REFERENCE_MODEL not in routes._VIDEO_MODEL_ORDER


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("images", "video", "audio", "expected_model"),
    [
        ([], None, [], h3.T2V_MODEL),
        (["https://example.test/first.jpg"], None, [], h3.I2V_MODEL),
        (
            ["https://example.test/a.jpg", "https://example.test/b.jpg", "https://example.test/c.jpg"],
            None,
            [],
            h3.REFERENCE_MODEL,
        ),
        (["https://example.test/person.jpg"], "https://example.test/motion.mp4", ["https://example.test/beat.wav"], h3.REFERENCE_MODEL),
    ],
)
async def test_h3_generate_wrapper_routes_public_family_by_media(
    monkeypatch,
    images,
    video,
    audio,
    expected_model,
) -> None:
    calls: list[tuple[dict, str | None]] = []

    async def create_task(payload, callback_url=None):
        calls.append((payload, callback_url))
        return {"code": 200, "data": {"taskId": "h3-task"}}

    async def prepare_images(value):
        if not value:
            return []
        return [value] if isinstance(value, str) else list(value)

    async def prepare_video(value):
        return value

    async def upload_media(value, upload_path):
        return value

    monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
    monkeypatch.setattr(video_service, "_prepare_video_reference_urls", prepare_images)
    monkeypatch.setattr(video_service, "_prepare_reference_video_url", prepare_video)
    monkeypatch.setattr(video_service, "_upload_local_media", upload_media)

    result = await video_service.generate_video(
        video_service.VideoModel(h3.PUBLIC_MODEL),
        "reference scene",
        image_url=images,
        duration=6,
        aspect_ratio="adaptive",
        resolution="768P",
        reference_video_url=video,
        audio_ids=audio,
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "h3-task"
    assert calls[0][0]["model"] == expected_model
    assert calls[0][0]["input"]["resolution"] == "768P"
    assert calls[0][0]["input"]["duration"] == 6
    assert calls[0][1] == "https://example.test/callback"


def test_audio_cannot_be_only_h3_reference() -> None:
    with pytest.raises(ValueError, match="accompanied by an image or video"):
        h3.validate_reference_set(images=[], videos=[], audios=["https://example.test/voice.wav"])

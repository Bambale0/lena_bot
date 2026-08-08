from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import seedance25_adapter as s25


@pytest.mark.parametrize(
    ("images", "videos", "audios", "expected"),
    [
        ([], [], [], "text"),
        (["one.jpg"], [], [], "image"),
        (["one.jpg", "two.jpg"], [], [], "multimodal"),
        (["one.jpg"], ["motion.mp4"], [], "multimodal"),
        (["one.jpg"], [], ["sound.wav"], "multimodal"),
        ([], ["motion.mp4"], [], "multimodal"),
        ([], [], ["sound.wav"], "multimodal"),
    ],
)
def test_route_is_derived_only_from_actual_references(images, videos, audios, expected) -> None:
    assert s25.route_for_inputs(images=images, videos=videos, audios=audios) == expected


def test_one_photo_is_first_frame_and_aspect_ratio_is_adaptive() -> None:
    payload = s25._seedance25_params(
        {
            "reference_image_urls": ["https://example.test/first.jpg"],
            "aspect_ratio": "16:9",
            "duration": 5,
            "resolution": "720p",
        }
    )
    assert payload["first_frame_url"] == "https://example.test/first.jpg"
    assert payload["aspect_ratio"] == "adaptive"
    assert "last_frame_url" not in payload
    assert "reference_image_urls" not in payload


def test_two_photos_are_multimodal_refs_not_first_last_frames() -> None:
    payload = s25._seedance25_params(
        {
            "reference_image_urls": [
                "https://example.test/a.jpg",
                "https://example.test/b.jpg",
            ],
            "aspect_ratio": "9:16",
            "duration": 10,
            "resolution": "720p",
        }
    )
    assert payload["reference_image_urls"] == [
        "https://example.test/a.jpg",
        "https://example.test/b.jpg",
    ]
    assert payload["aspect_ratio"] == "9:16"
    assert "first_frame_url" not in payload
    assert "last_frame_url" not in payload


def test_video_or_audio_forces_multimodal_reference_payload() -> None:
    payload = s25._seedance25_params(
        {
            "reference_image_urls": ["https://example.test/a.jpg"],
            "reference_video_urls": ["https://example.test/motion.mp4"],
            "reference_audio_urls": ["https://example.test/voice.wav"],
            "duration": 15,
            "resolution": "480p",
        }
    )
    assert payload["reference_image_urls"] == ["https://example.test/a.jpg"]
    assert payload["reference_video_urls"] == ["https://example.test/motion.mp4"]
    assert payload["reference_audio_urls"] == ["https://example.test/voice.wav"]
    assert "first_frame_url" not in payload
    assert "last_frame_url" not in payload


def test_legacy_first_last_fields_are_collapsed_into_multimodal_refs() -> None:
    payload = s25._seedance25_params(
        {
            "first_frame_url": "https://example.test/first.jpg",
            "last_frame_url": "https://example.test/last.jpg",
        }
    )
    assert payload["reference_image_urls"] == [
        "https://example.test/first.jpg",
        "https://example.test/last.jpg",
    ]
    assert "first_frame_url" not in payload
    assert "last_frame_url" not in payload


def test_ui_scenario_control_is_ignored() -> None:
    audio_refs, video_refs, options = s25._control_payload(
        [
            f"{s25.CONTROL_PREFIX}scenario=first_last",
            f"{s25.CONTROL_PREFIX}video_ref=https://example.test/motion.mp4",
            "https://example.test/voice.wav",
        ]
    )
    assert audio_refs == ["https://example.test/voice.wav"]
    assert video_refs == ["https://example.test/motion.mp4"]
    assert "mode" not in options


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _routes():
    def normalize_urls(*values):
        return [str(value) for value in values if str(value or "").strip()]

    def original(**kwargs):
        return kwargs

    return SimpleNamespace(
        _normalize_video_request=original,
        _normalize_public_urls=normalize_urls,
        HTTPException=_FakeHTTPException,
        VIDEO_CAPS={},
        _VIDEO_MODEL_ORDER=[],
    )


def _normalize(routes, **changes):
    body = dict(
        model_key=s25.MODEL_KEY,
        mode="first_last",
        duration=5,
        aspect_ratio="16:9",
        resolution="720p",
        image_url=None,
        reference_urls=[],
        video_url=None,
        video_start=None,
        video_end=None,
        audio_ids=[],
        character_ids=[],
        seed=None,
        grok_mode=None,
    )
    body.update(changes)
    return routes._normalize_video_request(**body)


def test_miniapp_normalizer_ignores_manual_mode_and_routes_from_media(monkeypatch) -> None:
    routes = _routes()
    monkeypatch.setattr(s25, "install_seedance25_provider_support", lambda: None)
    s25.install_seedance25_miniapp(routes)

    text = _normalize(routes)
    assert text["mode"] == "text"

    one = _normalize(routes, image_url="https://example.test/one.jpg")
    assert one["mode"] == "image"
    assert one["image_url"] == "https://example.test/one.jpg"
    assert one["aspect_ratio"] == "adaptive"

    two = _normalize(
        routes,
        image_url="https://example.test/one.jpg",
        reference_urls=["https://example.test/two.jpg"],
    )
    assert two["mode"] == "multimodal"
    assert two["image_url"] == [
        "https://example.test/one.jpg",
        "https://example.test/two.jpg",
    ]

    mixed = _normalize(
        routes,
        image_url="https://example.test/one.jpg",
        video_url="https://example.test/motion.mp4",
        audio_ids=["https://example.test/voice.wav"],
    )
    assert mixed["mode"] == "multimodal"
    assert mixed["reference_video_url"] == ["https://example.test/motion.mp4"]
    assert mixed["audio_ids"] == ["https://example.test/voice.wav"]

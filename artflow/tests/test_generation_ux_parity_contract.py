from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from api.video_request_compat import install_video_request_compat

ROOT = Path(__file__).resolve().parents[1]


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _fake_routes():
    def normalize_urls(*values):
        return [str(value) for value in values if value]

    def normalize_choice(value, allowed, *, field_name, default=None):
        if value is None:
            return default or allowed[0]
        if value not in allowed:
            raise HTTPException(422, f"bad {field_name}")
        return value

    def original(**kwargs):
        return {"mode": kwargs.get("mode")}

    return SimpleNamespace(
        VIDEO_CAPS={
            "kling-3.0/motion-control": {
                "modes": ["motion"],
                "max_refs": 1,
                "has_resolution": True,
                "resolutions": ["720p", "1080p"],
            }
        },
        HTTPException=HTTPException,
        _normalize_video_resolution=lambda model, resolution: resolution,
        _normalize_public_urls=normalize_urls,
        _normalize_choice=normalize_choice,
        _normalize_video_request=original,
    )


def test_motion_compat_preserves_image_and_video_inputs():
    routes = _fake_routes()
    install_video_request_compat(routes)
    normalized = routes._normalize_video_request(
        model_key="kling-3.0/motion-control",
        mode="motion",
        duration=5,
        aspect_ratio=None,
        resolution="1080p",
        image_url="https://cdn.example/character.jpg",
        reference_urls=[],
        video_url="https://cdn.example/motion.mp4",
    )
    assert normalized["mode"] == "motion"
    assert normalized["image_url"] == "https://cdn.example/character.jpg"
    assert normalized["reference_video_url"] == "https://cdn.example/motion.mp4"
    assert normalized["resolution"] == "1080p"


def test_motion_compat_requires_both_media_inputs():
    routes = _fake_routes()
    install_video_request_compat(routes)
    with pytest.raises(HTTPException, match="image reference"):
        routes._normalize_video_request(
            model_key="kling-3.0/motion-control",
            mode="motion",
            duration=5,
            aspect_ratio=None,
            resolution="720p",
            image_url=None,
            reference_urls=[],
            video_url="https://cdn.example/motion.mp4",
        )


def test_canonical_screen_validates_advanced_video_contract():
    src = (ROOT / "webapp/src/features/generation-screen.tsx").read_text()
    for token in (
        "invalidSeed",
        "invalidTrim",
        "mediaQuotaExceeded",
        "missingVideo",
        "GEMINI_MAX_MEDIA_SLOTS",
        "video_input_prices",
        "price_table",
    ):
        assert token in src


def test_app_sends_full_video_contract():
    src = (ROOT / "webapp/src/app/App.tsx").read_text()
    for token in (
        "video_url: draft.videoUrl",
        "video_start: draft.videoStart",
        "video_end: draft.videoEnd",
        "audio_ids: draft.audioIds",
        "character_ids: draft.characterIds",
        "seed: draft.seed",
        "grok_mode: draft.grokMode",
    ):
        assert token in src

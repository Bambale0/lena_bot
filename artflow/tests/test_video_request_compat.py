from __future__ import annotations

from types import SimpleNamespace

from api.video_request_compat import install_video_request_compat


def _routes():
    captured = {}

    def original(**kwargs):
        captured.update(kwargs)
        return dict(kwargs)

    def normalize_resolution(_model_key, value):
        return value

    return SimpleNamespace(
        VIDEO_CAPS={
            "bytedance/seedance-2": {
                "modes": ["text", "image"],
                "duration_options": [3, 5, 8, 10, 15],
                "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"],
                "has_resolution": True,
                "resolutions": ["480p", "720p", "1080p"],
                "mode_options": [],
            },
            "strict-video": {
                "modes": ["text"],
                "duration_options": [5, 10],
                "aspect_ratios": ["16:9"],
                "has_resolution": True,
                "resolutions": ["720p"],
                "mode_options": ["normal"],
            },
        },
        _normalize_video_request=original,
        _normalize_video_resolution=normalize_resolution,
        captured=captured,
    )


def test_video_compat_downgrades_stale_video_mode_for_seedance() -> None:
    routes = _routes()
    install_video_request_compat(routes)

    result = routes._normalize_video_request(
        model_key="bytedance/seedance-2",
        mode="video",
        duration=15,
        aspect_ratio="9:16",
        resolution="480p",
        image_url=None,
        reference_urls=[],
        video_url="https://cdn.example/motion.mp4",
        grok_mode="normal",
    )

    assert result["mode"] == "text"
    assert result["video_url"] is None
    assert result["duration"] == 15
    assert result["resolution"] == "480p"
    assert result["aspect_ratio"] == "9:16"


def test_video_compat_uses_image_mode_when_stale_video_has_image_refs() -> None:
    routes = _routes()
    install_video_request_compat(routes)

    result = routes._normalize_video_request(
        model_key="bytedance/seedance-2",
        mode="video",
        duration=15,
        aspect_ratio="9:16",
        resolution="480p",
        image_url="https://cdn.example/ref.png",
        reference_urls=[],
        video_url=None,
    )

    assert result["mode"] == "image"
    assert result["image_url"] == "https://cdn.example/ref.png"


def test_video_compat_clamps_stale_discrete_values() -> None:
    routes = _routes()
    install_video_request_compat(routes)

    result = routes._normalize_video_request(
        model_key="strict-video",
        mode="video",
        duration=15,
        aspect_ratio="9:16",
        resolution="480p",
        image_url=None,
        reference_urls=[],
        video_url="https://cdn.example/motion.mp4",
        grok_mode="spicy",
    )

    assert result["mode"] == "text"
    assert result["video_url"] is None
    assert result["duration"] == 5
    assert result["resolution"] == "720p"
    assert result["aspect_ratio"] == "16:9"
    assert result["grok_mode"] == "normal"

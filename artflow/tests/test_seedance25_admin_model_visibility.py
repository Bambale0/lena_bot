from __future__ import annotations

from pathlib import Path


def test_seedance25_model_registered_after_api_bootstrap():
    import api  # noqa: F401 - import side effects install provider adapters
    from api import kie_model_specs, video_service
    from api.seedance25_adapter import MODEL_KEY

    assert video_service.VideoModel(MODEL_KEY).value == MODEL_KEY
    spec = kie_model_specs.VIDEO_SPECS[MODEL_KEY]
    assert spec.model == MODEL_KEY
    assert spec.supported_modes == ("text", "image", "first_last", "reference", "multimodal", "video")
    assert spec.reference_field is None
    assert spec.param_builder is not None


def test_seedance25_caps_match_official_limits():
    import api  # noqa: F401
    from api.seedance25_adapter import VIDEO_CAPS

    assert VIDEO_CAPS["resolutions"] == ["480p", "720p"]
    assert "1080p" not in VIDEO_CAPS["resolutions"]
    assert -1 in VIDEO_CAPS["duration_options"]
    assert 4 in VIDEO_CAPS["duration_options"]
    assert 30 in VIDEO_CAPS["duration_options"]
    assert VIDEO_CAPS["max_reference_images"] == 30
    assert VIDEO_CAPS["max_reference_videos"] == 10
    assert VIDEO_CAPS["max_reference_audios"] == 10
    assert VIDEO_CAPS["output_formats"] == ["mp4", "mov"]
    assert VIDEO_CAPS["supports_audio_generation"] is True
    assert VIDEO_CAPS["supports_return_last_frame"] is True


def test_seedance25_builder_uses_first_last_frame_scenario():
    import api  # noqa: F401
    from api.seedance25_adapter import _seedance25_params

    payload = _seedance25_params(
        {
            "mode": "image",
            "reference_urls": ["https://cdn.example/first.png", "https://cdn.example/last.png"],
            "duration": 15,
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "return_last_frame": True,
            "generate_audio": False,
            "output_format": "mov",
        }
    )

    assert payload["first_frame_url"] == "https://cdn.example/first.png"
    assert payload["last_frame_url"] == "https://cdn.example/last.png"
    assert "reference_image_urls" not in payload
    assert "reference_video_urls" not in payload
    assert payload["duration"] == 15
    assert payload["resolution"] == "720p"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["return_last_frame"] is True
    assert payload["generate_audio"] is False
    assert payload["output_format"] == "mov"


def test_seedance25_builder_uses_multimodal_reference_scenario():
    import api  # noqa: F401
    from api.seedance25_adapter import _seedance25_params

    payload = _seedance25_params(
        {
            "mode": "multimodal",
            "reference_urls": ["https://cdn.example/ref.png"],
            "reference_video_urls": ["https://cdn.example/ref.mp4"],
            "reference_audio_urls": ["https://cdn.example/ref.mp3"],
            "duration": -1,
            "resolution": "480p",
            "aspect_ratio": "adaptive",
        }
    )

    assert payload["reference_image_urls"] == ["https://cdn.example/ref.png"]
    assert payload["reference_video_urls"] == ["https://cdn.example/ref.mp4"]
    assert payload["reference_audio_urls"] == ["https://cdn.example/ref.mp3"]
    assert "first_frame_url" not in payload
    assert "last_frame_url" not in payload
    assert payload["duration"] == -1
    assert payload["resolution"] == "480p"
    assert payload["aspect_ratio"] == "adaptive"


def test_seedance25_miniapp_hook_is_installed_in_bootstrap():
    source = Path("api/__init__.py").read_text(encoding="utf-8")
    assert "install_seedance25_provider_support()" in source
    assert "install_seedance25_miniapp(module)" in source


def test_admin_model_visibility_is_not_public_admin_ids():
    backend = Path("api/admin_model_visibility.py").read_text(encoding="utf-8")
    frontend = Path("webapp/src/lib/admin-model-visibility.ts").read_text(encoding="utf-8")
    main = Path("webapp/src/main.tsx").read_text(encoding="utf-8")

    assert "/me/permissions" in backend
    assert "settings.ADMIN_IDS" in backend
    assert "ADMIN_IDS" not in frontend
    assert "html:not([data-apix-admin=\"true\"])" in frontend
    assert "installAdminModelVisibility()" in main

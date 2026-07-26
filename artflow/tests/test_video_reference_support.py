from api.kie_model_specs import VIDEO_SPECS, build_kie_input
from api.video_service import VideoModel
from bot.keyboards.models import VIDEO_CAPS, video_mode_kb
from bot.services.video_reference_support import install_video_reference_support


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_seedance_family_exposes_video_mode():
    install_video_reference_support()
    for model in (
        VideoModel.SEEDANCE_2,
        VideoModel.SEEDANCE_2_FAST,
        VideoModel.SEEDANCE_2_MINI,
    ):
        caps = VIDEO_CAPS[model.value]
        assert "video" in caps["modes"]
        assert caps["supports_video_input"] is True
        assert caps["max_video_refs"] == 3
        assert "🎞️ Видео → Видео" in _labels(video_mode_kb(model.value))
        assert "video" in VIDEO_SPECS[model.value].supported_modes


def test_seedance_payload_uses_reference_video_urls():
    install_video_reference_support()
    model, payload = build_kie_input(
        model=VideoModel.SEEDANCE_2.value,
        prompt="Follow the reference motion",
        params={
            "duration": 5,
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "reference_video_url": [
                "https://cdn.example/a.mp4",
                "https://cdn.example/b.mov",
            ],
        },
    )
    assert model == VideoModel.SEEDANCE_2.value
    assert payload["reference_video_urls"] == [
        "https://cdn.example/a.mp4",
        "https://cdn.example/b.mov",
    ]
    assert "reference_image_urls" not in payload

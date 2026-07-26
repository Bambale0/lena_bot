from api.grok15_adapter import (
    GROK_15_PROVIDER_MODEL,
    normalize_grok15_payload,
)
from api.video_service import VideoModel
from bot.keyboards.models import VIDEO_CAPS, VIDEO_MODEL_DESC


def test_grok15_translates_legacy_text_payload():
    payload = normalize_grok15_payload(
        {
            "model": "grok-imagine/text-to-video",
            "input": {
                "prompt": "A cinematic robot walking through rain",
                "duration": 30,
                "aspect_ratio": "16:9",
                "resolution": "720p",
                "mode": "spicy",
            },
        }
    )

    assert payload == {
        "model": GROK_15_PROVIDER_MODEL,
        "input": {
            "prompt": "A cinematic robot walking through rain",
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "duration": 15,
            "nsfw_checker": False,
        },
    }


def test_grok15_supports_up_to_seven_image_references():
    payload = normalize_grok15_payload(
        {
            "model": "grok-imagine/image-to-video",
            "input": {
                "prompt": "Bring the scene to life",
                "image_urls": [f"https://example.com/{index}.png" for index in range(9)],
                "duration": 8,
                "aspect_ratio": "unsupported",
                "resolution": "4k",
                "task_id": "legacy-task-id",
            },
        }
    )

    assert payload["model"] == GROK_15_PROVIDER_MODEL
    assert len(payload["input"]["image_urls"]) == 7
    assert payload["input"]["aspect_ratio"] == "auto"
    assert payload["input"]["resolution"] == "480p"
    assert "task_id" not in payload["input"]


def test_non_grok_payload_is_untouched():
    payload = {"model": "bytedance/seedance-2", "input": {"prompt": "test"}}
    assert normalize_grok15_payload(payload) is payload


def test_grok15_ui_capabilities_match_provider_contract():
    caps = VIDEO_CAPS[VideoModel.GROK_T2V]

    assert caps["modes"] == ["text", "image"]
    assert caps["max_refs"] == 7
    assert caps["aspect_ratios"] == ["auto", "1:1", "16:9", "9:16", "3:2", "2:3"]
    assert caps["resolutions"] == ["480p", "720p"]
    assert max(caps["duration_options"]) == 15
    assert caps["native_audio"] is True
    assert "1.5 Preview" in VIDEO_MODEL_DESC[VideoModel.GROK_T2V]

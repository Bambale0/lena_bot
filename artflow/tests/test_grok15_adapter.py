from api.grok15_adapter import (
    GROK_15_PROVIDER_MODEL,
    normalize_grok15_payload,
)
from bot.keyboards import models as model_keyboards
from bot.keyboards.models import VIDEO_CAPS, VIDEO_MODEL_DESC
from bot.services.grok_versions import GROK_15, install_grok_versions


def test_legacy_grok_payload_is_untouched():
    payload = {
        "model": "grok-imagine/text-to-video",
        "input": {
            "prompt": "A cinematic robot walking through rain",
            "duration": 30,
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "mode": "spicy",
        },
    }
    assert normalize_grok15_payload(payload) is payload


def test_grok15_normalizes_dedicated_text_payload():
    payload = normalize_grok15_payload(
        {
            "model": GROK_15_PROVIDER_MODEL,
            "input": {
                "prompt": "A cinematic robot walking through rain",
                "duration": 30,
                "aspect_ratio": "16:9",
                "resolution": "720p",
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
            "model": GROK_15_PROVIDER_MODEL,
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


def test_grok_versions_have_separate_ui_capabilities_and_picker_entries():
    install_grok_versions()

    legacy = VIDEO_CAPS["grok-imagine/text-to-video"]
    new = VIDEO_CAPS[GROK_15]

    assert legacy["modes"] == ["text"]
    assert max(legacy["duration_options"]) == 30
    assert legacy["mode_options"] == ["fun", "normal", "spicy"]

    assert new["modes"] == ["text", "image"]
    assert new["max_refs"] == 7
    assert new["aspect_ratios"] == ["auto", "1:1", "16:9", "9:16", "3:2", "2:3"]
    assert new["resolutions"] == ["480p", "720p"]
    assert max(new["duration_options"]) == 15
    assert new["native_audio"] is True
    assert "1.5" in VIDEO_MODEL_DESC[GROK_15]

    groups = {key: [str(getattr(item, "value", item)) for item in items] for key, items in model_keyboards._VIDEO_GROUPS}
    assert GROK_15 in groups["fast"]
    assert GROK_15 in groups["i2v"]
    assert "grok-imagine/text-to-video" in groups["fast"]
    assert "grok-imagine/image-to-video" in groups["i2v"]

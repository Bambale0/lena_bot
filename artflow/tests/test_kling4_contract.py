from __future__ import annotations

import pytest

from api.kling4_contract import KEYFRAME_MODEL, REFERENCE_MODEL, Kling4Input, build_kling4_payload

URL = "https://cdn.example.org/input.png"


def payload(model=REFERENCE_MODEL, **values):
    return build_kling4_payload(
        model,
        "Camera follows @Hero" if values.get("elements") else "Camera follows the subject",
        Kling4Input(**values),
    )


@pytest.mark.parametrize("model", [REFERENCE_MODEL, KEYFRAME_MODEL])
@pytest.mark.parametrize("duration", [3, 5, 30])
@pytest.mark.parametrize("resolution", ["720p", "1080p"])
def test_exact_models_integer_duration_and_resolution(model, duration, resolution):
    assert payload(model, duration=duration, resolution=resolution) == {
        "model": model,
        "input": {
            "prompt": "Camera follows the subject",
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": "16:9",
        },
    }


@pytest.mark.parametrize("duration", [True, "5", 5.0, 2, 31])
def test_rejects_non_integer_or_out_of_range_duration(duration):
    with pytest.raises(ValueError):
        payload(duration=duration)


def test_reference_sources_use_exact_field_names():
    result = payload(
        image_urls=[URL], video_urls=["https://cdn.example.org/video.mp4"], keep_original_sound=True
    )["input"]
    assert result["image_urls"] == [URL]
    assert result["video_urls"] == ["https://cdn.example.org/video.mp4"]
    assert result["keep_original_sound"] is True
    assert result["aspect_ratio"] == "auto"


@pytest.mark.parametrize(
    "name",
    ["Hero", "image_1", "VIDEO_2", "first_frame", "object_1", "audio_2", "keyframe_1", "Герой"],
)
def test_shared_name_conflicts_and_reserved_names(name):
    with pytest.raises(ValueError):
        payload(
            elements=[{"name": "Hero", "image_urls": [URL, URL]}],
            voices=[{"name": name, "audio_url": URL}],
        )


def test_longest_tag_match_and_case_preservation():
    data = Kling4Input(
        elements=[
            {"name": "Hero", "image_urls": [URL, URL]},
            {"name": "Hero_2", "image_urls": [URL, URL]},
        ]
    )
    assert (
        build_kling4_payload(REFERENCE_MODEL, "@Hero_2 meets @Hero.", data)["input"]["elements"][1][
            "name"
        ]
        == "Hero_2"
    )
    for prompt in ["@Hero_23", "@hero", "@missing", "@image_1"]:
        with pytest.raises(ValueError):
            build_kling4_payload(REFERENCE_MODEL, prompt, data)


@pytest.mark.parametrize(
    "duration,count,valid",
    [(3, 4, True), (3, 5, False), (5, 6, True), (5, 7, False), (9, 10, True)],
)
def test_keyframe_limit_includes_first_and_last(duration, count, valid):
    data = Kling4Input(
        duration=duration,
        first_frame_url=URL,
        keyframe_urls=[URL] * (count - 2),
        last_frame_url=URL,
    )
    if valid:
        assert (
            len(
                build_kling4_payload(KEYFRAME_MODEL, "@first_frame to @last_frame", data)["input"][
                    "keyframe_urls"
                ]
            )
            == count - 2
        )
    else:
        with pytest.raises(ValueError):
            build_kling4_payload(KEYFRAME_MODEL, "@first_frame to @last_frame", data)


def test_keyframe_rejects_reference_fields_and_missing_first_frame():
    for fields in [
        {"image_urls": [URL]},
        {"video_urls": [URL]},
        {"keyframe_urls": [URL]},
        {"last_frame_url": URL},
    ]:
        with pytest.raises(ValueError):
            payload(KEYFRAME_MODEL, **fields)


def test_reference_quotas_and_exclusive_element_sources():
    for fields in [
        {"image_urls": [URL] * 11},
        {"video_urls": [URL] * 6},
        {
            "image_urls": [URL] * 10,
            "video_urls": [URL] * 5,
            "voices": [{"name": "Voice", "audio_url": URL}],
        },
        {"elements": [{"name": "Hero", "image_urls": [URL, URL], "video_url": URL}]},
        {"elements": [{"name": "Hero", "video_url": URL, "tag": "animal"}]},
        {"elements": [{"name": "Hero", "image_urls": [URL, URL], "tag": "prop", "voice_url": URL}]},
        {"first_frame_url": URL},
    ]:
        with pytest.raises(ValueError):
            payload(**fields)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "https://localhost/a",
        "https://10.0.0.1/a",
        "file:///tmp/a",
        "https://u:p@cdn.example.org/a",
    ],
)
def test_rejects_non_public_reference_urls(url):
    with pytest.raises(ValueError):
        payload(image_urls=[url])

"""Wan 3 standard/Prime provider contract and safe request billing invariants."""
import pytest

from api.wan30_contract import (
    Wan30Request,
    build_kie_wan30_payload,
    build_neironych_wan30_payload,
    wan30_max_billable_seconds,
    wan30_supported_by_neironych,
)


def test_kie_wan30_standard_text_contract():
    task = Wan30Request(
        model="wan/3-0-video", prompt="A cat jumps into the garden",
        resolution="480p", aspect_ratio="9:16", duration=5,
        audio=False, seed=0, nsfw_checker=True,
    )
    payload = build_kie_wan30_payload(task)
    assert payload == {
        "model": "wan/3-0-video",
        "input": {
            "prompt": "A cat jumps into the garden",
            "resolution": "480P",
            "aspect_ratio": "9:16",
            "duration": 5,
            "audio": False,
            "seed": 0,
            "nsfw_checker": True,
        },
    }
    assert wan30_max_billable_seconds(task) == 5


def test_kie_wan30_prime_multimodal_preserves_order_and_all_14_fields():
    task = Wan30Request(
        model="wan/3-0-video-prime", prompt="Edit @Video 1 using @Image 2",
        reference_image_urls=("https://example.test/a.png", "https://example.test/b.png"),
        reference_video_urls=("https://example.test/base.mp4",),
        reference_audio_urls=("https://example.test/voice.mp3",),
        reference_video_durations=(7.0,),
        reference_audio_durations=(3.0,),
        resolution="1080p", aspect_ratio="adaptive", duration=5,
        audio=True, seed=0, nsfw_checker=False, mode="edit",
    )
    payload = build_kie_wan30_payload(task)
    assert payload["model"] == "wan/3-0-video-prime"
    assert payload["input"]["reference_image_urls"] == [
        "https://example.test/a.png", "https://example.test/b.png",
    ]
    assert payload["input"]["reference_video_urls"] == ["https://example.test/base.mp4"]
    assert payload["input"]["reference_audio_urls"] == ["https://example.test/voice.mp3"]
    assert payload["input"]["audio"] is True
    assert payload["input"]["seed"] == 0
    assert payload["input"]["nsfw_checker"] is False
    assert payload["input"]["duration"] == 5
    assert wan30_max_billable_seconds(task) == 12


def test_wan30_file_or_link_do_not_mix_and_are_kept_for_kie():
    task = Wan30Request(
        model="wan/3-0-video", prompt="Render this brief",
        reference_file_urls=("https://example.test/brief.pdf",),
    )
    assert build_kie_wan30_payload(task)["input"]["reference_file_urls"] == [
        "https://example.test/brief.pdf",
    ]
    assert not wan30_supported_by_neironych(task)
    with pytest.raises(ValueError, match="cannot be combined"):
        build_kie_wan30_payload(Wan30Request(
            model="wan/3-0-video", prompt="brief",
            reference_file_urls=("https://example.test/a.pdf",),
            reference_link_urls=("https://example.test",),
        ))


@pytest.mark.parametrize("kwargs,expected", [
    ({"model":"wan/3-0-video","prompt":"a","last_frame_url":"https://example.test/last.png"}, "last_frame_url"),
    ({"model":"wan/3-0-video","prompt":"a","first_frame_url":"https://example.test/start.png",
      "reference_image_urls":("https://example.test/img.png",)}, "cannot be combined"),
    ({"model":"wan/3-0-video","prompt":"a","reference_video_urls":("https://example.test/a.mp4",)}, "measured"),
    ({"model":"wan/3-0-video","prompt":"a","reference_video_urls":("https://example.test/a.mp4",),
      "reference_video_durations":(17,)}, "15"),
    ({"model":"wan/3-0-video","prompt":"a","reference_video_urls":("https://example.test/a.mp4",),
      "reference_video_durations":(13,), "duration":20}, "30"),
    ({"model":"wan/3-0-video","prompt":"a","seed":-1}, "seed"),
    ({"model":"wan/3-0-video","prompt":"a","reference_image_urls":("http://localhost/private.png",)}, "https"),
    ({"model":"wan/3-0-video","prompt":"a","mode":"edit"}, "source video"),
    ({"model":"wan/3-0-video","prompt":"a","reference_image_urls":tuple("https://example.test/"+str(i) for i in range(11))}, "10"),
])
def test_wan30_invalid_payload_rejected_before_billing(kwargs,expected):
    with pytest.raises(ValueError, match=expected):
        build_kie_wan30_payload(Wan30Request(**kwargs))


def test_auto_maximum_reserves_30_total_even_with_video_refs():
    task = Wan30Request(
        model="wan/3-0-video", prompt="Continue",
        reference_video_urls=("https://example.test/video.mp4",),
        reference_video_durations=(7.0,), duration=-1,
    )
    assert wan30_max_billable_seconds(task)==30
    assert build_kie_wan30_payload(task)["input"]["duration"]==-1


def test_neironych_media_roles_and_false_audio_are_translated():
    task = Wan30Request(
        model="wan/3-0-video",prompt="Use @Image 1",
        reference_image_urls=("https://example.test/person.jpg",),
        duration=5,audio=False,seed=0,
    )
    assert wan30_supported_by_neironych(task)
    body = build_neironych_wan30_payload(task,provider_model="wan-approved-model")
    assert body["model"]=="wan-approved-model"
    assert body["mode"]=="reference"
    assert body["reference_images"]==[{"url":"https://example.test/person.jpg"}]
    assert body["generate_audio"] is False
    assert body["seed"] == 0



@pytest.mark.parametrize("case", [
    {"nsfw_checker": False},
    {"first_frame_url": "https://example.test/scene.png", "aspect_ratio": "9:16"},
])
def test_neironych_unavailable_for_options_it_cannot_preserve(case):
    task = Wan30Request(model="wan/3-0-video", prompt="A mountain",
                        **case)
    assert not wan30_supported_by_neironych(task)
    assert build_kie_wan30_payload(task)["input"]["prompt"] == "A mountain"

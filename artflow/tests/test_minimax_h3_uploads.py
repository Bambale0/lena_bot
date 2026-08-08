from types import SimpleNamespace

from api.web import minimax_h3_uploads as uploads


def _upload(filename: str, content_type: str):
    return SimpleNamespace(filename=filename, content_type=content_type)


def test_h3_upload_accepts_official_media_families_and_limits():
    assert uploads._kind_and_limit(_upload("ref.heic", "image/heic")) == (
        "image",
        30 * 1024 * 1024,
        None,
    )
    assert uploads._kind_and_limit(_upload("motion.mov", "video/quicktime")) == (
        "video",
        50 * 1024 * 1024,
        None,
    )
    assert uploads._kind_and_limit(_upload("voice.wav", "audio/wav")) == (
        "audio",
        15 * 1024 * 1024,
        None,
    )


def test_h3_video_probe_enforces_codec_dimensions_fps_and_duration():
    valid = {
        "format": {"duration": "12.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    assert uploads._validate_video_probe(valid) is None

    too_long = {**valid, "format": {"duration": "15.5"}}
    assert "between 2 and 15" in str(uploads._validate_video_probe(too_long))

    bad_codec = {
        **valid,
        "streams": [{**valid["streams"][0], "codec_name": "vp9"}],
    }
    assert "H.264" in str(uploads._validate_video_probe(bad_codec))

    bad_fps = {
        **valid,
        "streams": [{**valid["streams"][0], "avg_frame_rate": "120/1"}],
    }
    assert "23.976 and 60 FPS" in str(uploads._validate_video_probe(bad_fps))


def test_h3_audio_probe_enforces_format_and_duration():
    valid = {
        "format": {"duration": "8.0"},
        "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
    }
    assert uploads._validate_audio_probe(valid) is None

    invalid_codec = {
        "format": {"duration": "8.0"},
        "streams": [{"codec_type": "audio", "codec_name": "aac"}],
    }
    assert "MP3 or WAV" in str(uploads._validate_audio_probe(invalid_codec))

    too_short = {
        "format": {"duration": "1.0"},
        "streams": [{"codec_type": "audio", "codec_name": "mp3"}],
    }
    assert "between 2 and 15" in str(uploads._validate_audio_probe(too_short))


def test_h3_rejects_unsupported_reference_extensions():
    kind, limit, error = uploads._kind_and_limit(_upload("clip.webm", "video/webm"))
    assert kind is None
    assert limit == 0
    assert error == "Unsupported MiniMax H3 reference format"

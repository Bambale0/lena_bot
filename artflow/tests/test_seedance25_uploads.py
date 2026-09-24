from types import SimpleNamespace

from api.web import seedance25_uploads as uploads


def _file(name: str, content_type: str):
    return SimpleNamespace(filename=name, content_type=content_type)


def test_seedance25_upload_accepts_image_video_and_audio_families() -> None:
    assert uploads._kind_and_limit(_file("ref.webp", "image/webp")) == (
        "image",
        30 * 1024 * 1024,
        None,
    )
    assert uploads._kind_and_limit(_file("ref.mkv", "video/x-matroska")) == (
        "video",
        50 * 1024 * 1024,
        None,
    )
    assert uploads._kind_and_limit(_file("ref.ogg", "audio/ogg")) == (
        "audio",
        15 * 1024 * 1024,
        None,
    )


def test_seedance25_upload_rejects_unknown_reference_format() -> None:
    kind, limit, error = uploads._kind_and_limit(_file("ref.txt", "text/plain"))
    assert kind is None
    assert limit == 0
    assert "unsupported reference format" in str(error)


def test_seedance25_video_probe_accepts_valid_reference() -> None:
    payload = {
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280}],
        "format": {"duration": "12.633333"},
    }
    assert uploads._validate_video_probe(payload) is None


def test_seedance25_video_probe_rejects_too_long_reference() -> None:
    payload = {
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280}],
        "format": {"duration": "36.86"},
    }
    assert "2 and 30 seconds" in str(uploads._validate_video_probe(payload))


def test_seedance25_video_probe_rejects_low_pixel_count() -> None:
    payload = {
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 352, "height": 640}],
        "format": {"duration": "12"},
    }
    assert "pixel count" in str(uploads._validate_video_probe(payload)).lower()


def test_seedance25_upload_rejects_mkv_for_kie_reference_video() -> None:
    kind, limit, error = uploads._kind_and_limit(_file("ref.mkv", "video/x-matroska"))
    assert kind is None
    assert limit == 0
    assert "MP4 or MOV" in str(error)

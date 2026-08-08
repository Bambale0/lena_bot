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

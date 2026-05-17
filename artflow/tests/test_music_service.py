from api.music_service import default_music_callback_url, extract_music_urls
from core.config import settings


def test_extract_music_urls_one_url_per_track():
    payload = {
        "code": 200,
        "data": {
            "callbackType": "complete",
            "data": [
                {
                    "audio_url": "https://tempfile.aiquickdraw.com/r/track1.mp3",
                    "source_audio_url": "https://tempfile.aiquickdraw.com/r/track1.mp3",
                    "source_stream_audio_url": "https://cdn1.suno.ai/track1.mp3",
                    "stream_audio_url": "https://musicfile.kie.ai/track1",
                },
                {
                    "audio_url": "https://tempfile.aiquickdraw.com/r/track2.mp3",
                    "source_audio_url": "https://tempfile.aiquickdraw.com/r/track2.mp3",
                },
            ],
            "task_id": "x",
        },
        "msg": "All generated successfully.",
    }
    assert extract_music_urls(payload) == [
        "https://tempfile.aiquickdraw.com/r/track1.mp3",
        "https://tempfile.aiquickdraw.com/r/track2.mp3",
    ]


def test_extract_music_urls_ignores_duplicates():
    payload = {
        "code": 200,
        "data": {
            "callbackType": "complete",
            "data": [
                {
                    "audio_url": "https://tempfile.aiquickdraw.com/r/track1.mp3",
                    "source_audio_url": "https://tempfile.aiquickdraw.com/r/track1.mp3",
                    "stream_audio_url": "https://musicfile.kie.ai/track1",
                },
            ],
            "task_id": "x",
        },
        "msg": "All generated successfully.",
    }
    result = extract_music_urls(payload)
    assert len(result) == 1
    assert result[0] == "https://tempfile.aiquickdraw.com/r/track1.mp3"


def test_default_music_callback_url_includes_secret(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_URL", "https://example.test/")
    monkeypatch.setattr(settings, "KIE_WEBHOOK_SECRET", "secret with space")

    assert default_music_callback_url() == "https://example.test/webhook/kie/music?secret=secret+with+space"

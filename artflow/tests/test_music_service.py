import pytest

from api.music_service import (
    build_music_generation_payload,
    default_music_callback_url,
    extract_music_urls,
    extract_suno_provider_voice_id,
    extract_suno_validate_phrase,
    is_supported_suno_voice_audio,
)
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


def test_build_music_generation_payload_keeps_legacy_non_custom_shape(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_URL", "https://example.test")
    monkeypatch.setattr(settings, "KIE_WEBHOOK_SECRET", "")

    payload = build_music_generation_payload("lo-fi study beat", model_key="suno/v5.5")

    assert payload["customMode"] is False
    assert payload["model"] == "V5_5"
    assert payload["prompt"] == "lo-fi study beat"
    assert "voiceId" not in payload
    assert "style" not in payload
    assert "title" not in payload


def test_build_music_generation_payload_uses_custom_voice(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_URL", "https://example.test")

    payload = build_music_generation_payload(
        "Verse about the summer",
        model_key="suno/v5.5",
        style="pop, bright vocal",
        title="Summer Signal",
        voice_id="voice_123",
    )

    assert payload["customMode"] is True
    assert payload["voiceId"] == "voice_123"
    assert payload["style"] == "pop, bright vocal"
    assert payload["title"] == "Summer Signal"


def test_build_music_generation_payload_rejects_voice_without_custom_fields():
    with pytest.raises(ValueError, match="style"):
        build_music_generation_payload("lyrics", voice_id="voice_123", title="Track")

    with pytest.raises(ValueError, match="title"):
        build_music_generation_payload("lyrics", voice_id="voice_123", style="pop")

    with pytest.raises(ValueError, match="vocal"):
        build_music_generation_payload(
            "lyrics",
            instrumental=True,
            voice_id="voice_123",
            style="pop",
            title="Track",
        )


def test_suno_voice_extractors_and_audio_detection():
    payload = {
        "code": 200,
        "data": {
            "taskId": "voice-task",
            "validateInfo": "Sing this exact phrase",
            "voiceId": "voice_abc",
        },
    }

    assert extract_suno_validate_phrase(payload) == "Sing this exact phrase"
    assert extract_suno_provider_voice_id(payload) == "voice_abc"
    assert is_supported_suno_voice_audio(b"ID3payload", "application/octet-stream", "voice.bin")
    assert not is_supported_suno_voice_audio(b"not audio", "text/plain", "voice.txt")

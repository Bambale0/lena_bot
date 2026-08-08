from __future__ import annotations

import pytest

from api import suno_full_service
from api.suno_source_audio import (
    SunoSourceOperation,
    inspect_source_audio,
    start_source_audio_task,
)


@pytest.mark.asyncio
async def test_source_audio_duration_and_format_validation(monkeypatch):
    monkeypatch.setattr("api.suno_source_audio._probe_audio", lambda path: 123.4)
    duration, filename, mime = await inspect_source_audio(
        b"fake-audio-bytes",
        filename="demo.mp3",
        content_type="audio/mpeg",
    )
    assert duration == 123.4
    assert filename == "source.mp3"
    assert mime == "audio/mpeg"


@pytest.mark.asyncio
async def test_source_audio_rejects_more_than_eight_minutes(monkeypatch):
    monkeypatch.setattr("api.suno_source_audio._probe_audio", lambda path: 481.0)
    with pytest.raises(ValueError, match="8 minutes"):
        await inspect_source_audio(
            b"fake-audio-bytes",
            filename="demo.wav",
            content_type="audio/wav",
        )


@pytest.mark.asyncio
async def test_cover_dispatches_to_official_upload_cover(monkeypatch):
    calls = []

    async def upload_and_cover(upload_url, prompt, **kwargs):
        calls.append((upload_url, prompt, kwargs))
        return suno_full_service.SunoTask(task_id="cover-task", operation="upload-cover")

    monkeypatch.setattr(suno_full_service, "upload_and_cover", upload_and_cover)
    task = await start_source_audio_task(
        operation="cover",
        upload_url="https://example.test/source.mp3",
        prompt="turn this into cinematic synthwave",
        model_key="suno/v5.5",
    )

    assert task.task_id == "cover-task"
    assert calls[0][0] == "https://example.test/source.mp3"
    assert calls[0][1] == "turn this into cinematic synthwave"
    assert calls[0][2]["custom_mode"] is False


@pytest.mark.asyncio
async def test_extend_uses_continue_at(monkeypatch):
    calls = []

    async def upload_and_extend(upload_url, prompt, **kwargs):
        calls.append((upload_url, prompt, kwargs))
        return suno_full_service.SunoTask(task_id="extend-task", operation="upload-extend")

    monkeypatch.setattr(suno_full_service, "upload_and_extend", upload_and_extend)
    await start_source_audio_task(
        operation=SunoSourceOperation.EXTEND,
        upload_url="https://example.test/source.wav",
        prompt="continue naturally",
        model_key="suno/v5.5",
        continue_at=59.5,
    )
    assert calls[0][2]["continue_at"] == 59.5
    assert calls[0][2]["use_custom_parameters"] is False


@pytest.mark.asyncio
async def test_add_vocals_and_instrumental_use_supported_provider_model(monkeypatch):
    vocal_calls = []
    instrumental_calls = []

    async def add_vocals(upload_url, **kwargs):
        vocal_calls.append((upload_url, kwargs))
        return suno_full_service.SunoTask(task_id="vocals-task", operation="add-vocals")

    async def add_instrumental(upload_url, **kwargs):
        instrumental_calls.append((upload_url, kwargs))
        return suno_full_service.SunoTask(task_id="instrumental-task", operation="add-instrumental")

    monkeypatch.setattr(suno_full_service, "add_vocals", add_vocals)
    monkeypatch.setattr(suno_full_service, "add_instrumental", add_instrumental)

    await start_source_audio_task(
        operation="add_vocals",
        upload_url="https://example.test/source.mp3",
        prompt="new chorus lyrics",
        style="indie pop",
        title="New Chorus",
    )
    await start_source_audio_task(
        operation="add_instrumental",
        upload_url="https://example.test/source.mp3",
        prompt="warm cinematic arrangement",
        style="cinematic orchestral",
        title="Orchestral Version",
    )

    assert vocal_calls[0][1]["model"] == suno_full_service.SunoModel.V4_5PLUS
    assert instrumental_calls[0][1]["model"] == suno_full_service.SunoModel.V4_5PLUS
    assert instrumental_calls[0][1]["tags"] == "cinematic orchestral"


def test_source_operation_enum_is_public_product_contract():
    assert {item.value for item in SunoSourceOperation} == {
        "cover",
        "extend",
        "add_vocals",
        "add_instrumental",
    }

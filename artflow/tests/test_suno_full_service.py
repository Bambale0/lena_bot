from __future__ import annotations

import pytest

from api import suno_full_service as suno
from api.suno_full_service import SeparationType, SunoModel, SunoTuning


@pytest.mark.asyncio
async def test_generate_music_simple_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": "music_simple"}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    result = await suno.generate_music(
        "A relaxed evening jazz track",
        model=SunoModel.V5,
        instrumental=True,
        callback_url="https://example.test/callback",
    )

    assert result.task_id == "music_simple"
    assert calls == [
        (
            "/api/v1/generate",
            {
                "prompt": "A relaxed evening jazz track",
                "customMode": False,
                "instrumental": True,
                "model": "V5",
                "callBackUrl": "https://example.test/callback",
            },
        )
    ]


@pytest.mark.asyncio
async def test_generate_music_custom_all_tuning_fields(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": "music_custom"}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.generate_music(
        "[Verse] Lyrics",
        model=SunoModel.V5_5,
        custom_mode=True,
        instrumental=False,
        style="Electronic pop",
        title="Neon Night",
        tuning=SunoTuning(
            negative_tags="metal",
            vocal_gender="f",
            style_weight=0.61,
            weirdness_constraint=0.72,
            audio_weight=0.65,
            persona_id="persona_123",
            persona_model="style_persona",
            voice_id="voice_123",
        ),
    )

    assert calls[0][1] == {
        "prompt": "[Verse] Lyrics",
        "customMode": True,
        "instrumental": False,
        "model": "V5_5",
        "style": "Electronic pop",
        "title": "Neon Night",
        "negativeTags": "metal",
        "vocalGender": "f",
        "styleWeight": 0.61,
        "weirdnessConstraint": 0.72,
        "audioWeight": 0.65,
        "personaId": "persona_123",
        "personaModel": "style_persona",
        "voiceId": "voice_123",
    }


@pytest.mark.asyncio
async def test_simple_mode_rejects_custom_fields(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(suno.kieai_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="Simple Suno mode"):
        await suno.generate_music(
            "A track",
            custom_mode=False,
            style="Jazz",
        )


@pytest.mark.asyncio
async def test_extend_original_parameters_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": "extend_task"}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.extend_music("audio_123")

    assert calls == [
        (
            "/api/v1/generate/extend",
            {"audioId": "audio_123", "defaultParamFlag": False},
        )
    ]


@pytest.mark.asyncio
async def test_extend_custom_parameters_exact_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": "extend_task"}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.extend_music(
        "audio_123",
        use_custom_parameters=True,
        prompt="Continue with a bridge",
        model="V5",
        style="Pop",
        title="Extended Song",
        continue_at=60,
        tuning=SunoTuning(persona_id="persona_1", persona_model="style_persona"),
    )

    assert calls[0][1] == {
        "audioId": "audio_123",
        "defaultParamFlag": True,
        "prompt": "Continue with a bridge",
        "model": "V5",
        "style": "Pop",
        "title": "Extended Song",
        "continueAt": 60.0,
        "personaId": "persona_1",
        "personaModel": "style_persona",
    }


@pytest.mark.asyncio
async def test_upload_cover_and_extend_paths(monkeypatch) -> None:
    paths: list[str] = []

    async def fake_post(path: str, payload: dict) -> dict:
        paths.append(path)
        return {"code": 200, "data": {"taskId": str(len(paths))}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.upload_and_cover(
        "https://example.test/source.mp3",
        "Turn this into jazz",
    )
    await suno.upload_and_extend(
        "https://example.test/source.mp3",
        "Continue the source",
        continue_at=30,
    )

    assert paths == [
        "/api/v1/generate/upload-cover",
        "/api/v1/generate/upload-extend",
    ]


@pytest.mark.asyncio
async def test_add_instrumental_and_vocals_paths(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": str(len(calls))}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.add_instrumental(
        "https://example.test/vocal.mp3",
        title="New instrumental",
        tags="jazz, piano",
        tuning=SunoTuning(negative_tags="metal"),
    )
    await suno.add_vocals(
        "https://example.test/instrumental.mp3",
        prompt="[Verse] Hello",
        style="Pop",
        title="New vocals",
        tuning=SunoTuning(vocal_gender="m"),
    )

    assert calls[0][0] == "/api/v1/generate/add-instrumental"
    assert calls[0][1]["tags"] == "jazz, piano"
    assert calls[1][0] == "/api/v1/generate/add-vocals"
    assert calls[1][1]["vocalGender"] == "m"


@pytest.mark.asyncio
async def test_replace_section_validates_range_before_billing(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(suno.kieai_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="between 6 and 60"):
        await suno.replace_section(
            "task",
            "audio",
            prompt="Replacement",
            tags="Jazz",
            title="Song",
            infill_start_s=10,
            infill_end_s=12,
        )


@pytest.mark.asyncio
async def test_persona_returns_persona_id(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {
            "code": 200,
            "data": {
                "personaId": "persona_1",
                "name": "Singer",
                "description": "Voice",
            },
        }

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    result = await suno.generate_persona(
        "task_1",
        "audio_1",
        name="Singer",
        description="Voice",
        vocal_start=0,
        vocal_end=30,
        style="Pop",
    )

    assert result["personaId"] == "persona_1"
    assert calls[0][0] == "/api/v1/generate/generate-persona"


@pytest.mark.asyncio
async def test_mashup_requires_exactly_two_uploads(monkeypatch) -> None:
    async def forbidden_post(path: str, payload: dict) -> dict:
        raise AssertionError("invalid request must not reach provider")

    monkeypatch.setattr(suno.kieai_client, "post", forbidden_post)

    with pytest.raises(ValueError, match="exactly two"):
        await suno.generate_mashup(
            ["https://example.test/one.mp3"],
            "Combine",
        )


@pytest.mark.asyncio
async def test_lyrics_timestamp_style_and_cover_paths(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        if path == "/api/v1/generate/get-timestamped-lyrics":
            return {"code": 200, "data": {"alignedWords": []}}
        if path == "/api/v1/style/generate":
            return {"code": 200, "data": {"result": "boosted"}}
        return {"code": 200, "data": {"taskId": str(len(calls))}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.generate_lyrics("A song about summer")
    assert await suno.get_timestamped_lyrics("task", "audio") == {"alignedWords": []}
    assert await suno.boost_style("Pop, mysterious") == {"result": "boosted"}
    await suno.generate_cover_art("task")

    assert [path for path, _ in calls] == [
        "/api/v1/lyrics",
        "/api/v1/generate/get-timestamped-lyrics",
        "/api/v1/style/generate",
        "/api/v1/suno/cover/generate",
    ]


@pytest.mark.asyncio
async def test_wav_stems_midi_and_music_video_paths(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"taskId": str(len(calls))}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)

    await suno.convert_to_wav("task", "audio")
    await suno.separate_stems("task", "audio", separation_type=SeparationType.STEMS)
    await suno.generate_midi("separation_task", callback_url="https://example.test/callback")
    await suno.create_music_video(
        "task",
        "audio",
        author="Artist",
        domain_name="music.example.test",
    )

    assert [path for path, _ in calls] == [
        "/api/v1/wav/generate",
        "/api/v1/vocal-removal/generate",
        "/api/v1/midi/generate",
        "/api/v1/mp4/generate",
    ]
    assert calls[1][1]["type"] == "split_stem"


@pytest.mark.asyncio
async def test_polling_endpoints(monkeypatch) -> None:
    paths: list[str] = []

    async def fake_get(path: str) -> dict:
        paths.append(path)
        return {"code": 200, "data": {"taskId": "task"}}

    monkeypatch.setattr(suno.kieai_client, "get", fake_get)

    await suno.get_music_task("task")
    await suno.get_lyrics_task("task")
    await suno.get_wav_task("task")
    await suno.get_stem_task("task")
    await suno.get_midi_task("task")
    await suno.get_music_video_task("task")
    await suno.get_cover_art_task("task")

    assert paths == [
        "/api/v1/generate/record-info?taskId=task",
        "/api/v1/lyrics/record-info?taskId=task",
        "/api/v1/wav/record-info?taskId=task",
        "/api/v1/vocal-removal/record-info?taskId=task",
        "/api/v1/midi/record-info?taskId=task",
        "/api/v1/mp4/record-info?taskId=task",
        "/api/v1/suno/cover/record-info?taskId=task",
    ]


@pytest.mark.asyncio
async def test_custom_voice_full_lifecycle(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    get_calls: list[str] = []

    async def fake_post(path: str, payload: dict) -> dict:
        post_calls.append((path, payload))
        if path == "/api/v1/voice/check-voice":
            return {"code": 200, "data": {"isAvailable": True}}
        return {"code": 200, "data": {"taskId": str(len(post_calls))}}

    async def fake_get(path: str) -> dict:
        get_calls.append(path)
        return {"code": 200, "data": {"status": "success"}}

    monkeypatch.setattr(suno.kieai_client, "post", fake_post)
    monkeypatch.setattr(suno.kieai_client, "get", fake_get)

    await suno.create_voice_validation(
        "https://example.test/source.mp3",
        vocal_start_s=0,
        vocal_end_s=10,
    )
    await suno.regenerate_voice_validation("validation_task")
    await suno.create_custom_voice(
        "validation_task",
        "https://example.test/verify.mp3",
        voice_name="My Voice",
        singer_skill_level="beginner",
    )
    await suno.get_voice_validation("validation_task")
    await suno.get_custom_voice("voice_task")
    assert await suno.check_custom_voice("voice_task") is True

    assert [path for path, _ in post_calls] == [
        "/api/v1/voice/validate",
        "/api/v1/voice/regenerate",
        "/api/v1/voice/generate",
        "/api/v1/voice/check-voice",
    ]
    assert get_calls == [
        "/api/v1/voice/validate-info?taskId=validation_task",
        "/api/v1/voice/record-info?taskId=voice_task",
    ]

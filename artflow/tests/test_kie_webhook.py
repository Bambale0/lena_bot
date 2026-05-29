from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
import main

from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_processing, is_success


def test_extract_task_id_from_nested_data_payload() -> None:
    payload = {"data": {"payload": "{\"taskId\":\"abc-123\"}"}}
    assert extract_task_id(payload) == "abc-123"


def test_extract_result_urls_deduplicates_ordered_urls() -> None:
    payload = {"data": {"resultUrls": ["https://a.test/1.png", "https://a.test/1.png"]}, "url": "https://a.test/2.png"}
    assert extract_result_urls(payload) == ["https://a.test/1.png", "https://a.test/2.png"]


def test_extract_result_urls_filters_uploaded_reference_urls() -> None:
    payload = {
        "data": {
            "resultJson": (
                '{"resultUrls": ['
                '"https://tempfile.aiquickdraw.com/qwen2/result.png",'
                '"https://tempfile.redpandaai.co/kieai/x/images/apix-refs/input.png"'
                "]}"
            )
        }
    }
    assert extract_result_urls(payload) == ["https://tempfile.aiquickdraw.com/qwen2/result.png"]


def test_extract_result_urls_supports_result_image_url_callback_shape() -> None:
    payload = {
        "code": 200,
        "data": {
            "taskId": "task_seedream_1",
            "info": {
                "originImageUrl": "https://a.test/original.png",
                "resultImageUrl": "https://a.test/result.png",
            },
        },
    }
    assert extract_result_urls(payload) == ["https://a.test/result.png"]


def test_extract_result_urls_supports_comet_kling_task_result_shape() -> None:
    payload = {
        "code": 0,
        "data": {
            "task_id": "kling_task_1",
            "task_status": "succeed",
            "task_result": {
                "videos": [
                    {"id": "video_1", "url": "https://cdn.test/video.mp4"},
                ]
            },
        },
    }

    assert extract_task_id(payload) == "kling_task_1"
    assert is_success(payload) is True
    assert extract_result_urls(payload) == ["https://cdn.test/video.mp4"]


def test_extract_result_urls_supports_comet_v1_video_shape() -> None:
    payload = {
        "id": "task_1",
        "status": "completed",
        "video_url": "https://cdn.test/v1-video.mp4",
    }

    assert extract_task_id(payload) == "task_1"
    assert is_success(payload) is True
    assert extract_result_urls(payload) == ["https://cdn.test/v1-video.mp4"]


def test_is_success_true_for_result_image_url_callback_shape() -> None:
    payload = {
        "code": 200,
        "data": {
            "taskId": "task_seedream_1",
            "info": {"resultImageUrl": "https://a.test/result.png"},
        },
    }
    assert is_success(payload) is True


def test_is_success_false_for_failed_state() -> None:
    assert is_success({"code": 200, "data": {"state": "failed"}}) is False


def test_is_processing_true_for_comet_submitted_status() -> None:
    assert is_processing({"code": 0, "data": {"task_status": "submitted"}}) is True


def test_extract_error_prefers_nested_message() -> None:
    assert extract_error({"data": {"failMsg": "bad prompt"}}) == "bad prompt"


def test_kie_result_caption_hides_feed_prompt() -> None:
    gen = SimpleNamespace(prompt="secret feed prompt", source_feed_gen_id=42)
    assert main._kie_result_caption(gen) == "✅ <b>Готово!</b>"


def test_kie_result_caption_hides_own_prompt_preview() -> None:
    gen = SimpleNamespace(prompt="own prompt", source_feed_gen_id=None)
    assert main._kie_result_caption(gen) == "✅ <b>Готово!</b>"


def test_prompt_menu_text_does_not_inline_prompt() -> None:
    text = main._prompt_menu_text("portrait <cinematic>")

    assert text == "Что делаем дальше?"


def test_prompt_menu_text_hides_empty_prompt() -> None:
    assert main._prompt_menu_text(None) == "Что делаем дальше?"


def test_prompt_menu_preview_hides_repeats() -> None:
    gen = SimpleNamespace(action_type="repeat")
    assert main._prompt_menu_preview_for_generation(gen, "repeat prompt") is None


def test_prompt_menu_preview_hides_stringified_repeats() -> None:
    gen = SimpleNamespace(action_type="ImageGenerationAction.repeat")
    assert main._prompt_menu_preview_for_generation(gen, "repeat prompt") is None


def test_prompt_menu_preview_keeps_initial_generations() -> None:
    gen = SimpleNamespace(action_type="initial")
    assert main._prompt_menu_preview_for_generation(gen, "own prompt") == "own prompt"


@pytest.mark.asyncio
async def test_prompt_actions_allowed_for_own_feed_source(monkeypatch) -> None:
    get_generation_by_id = AsyncMock(return_value=SimpleNamespace(user_id=42))
    monkeypatch.setattr(main.repo, "get_generation_by_id", get_generation_by_id)

    allowed = await main._prompt_actions_allowed_for_generation(
        AsyncMock(),
        SimpleNamespace(user_id=42, source_feed_gen_id=77),
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_prompt_actions_hidden_for_other_author_feed_source(monkeypatch) -> None:
    get_generation_by_id = AsyncMock(return_value=SimpleNamespace(user_id=7))
    monkeypatch.setattr(main.repo, "get_generation_by_id", get_generation_by_id)

    allowed = await main._prompt_actions_allowed_for_generation(
        AsyncMock(),
        SimpleNamespace(user_id=42, source_feed_gen_id=77),
    )

    assert allowed is False


class _FakeSessionContext:
    async def __aenter__(self):
        return _FAKE_SESSION

    async def __aexit__(self, exc_type, exc, tb):
        return False


_FAKE_SESSION = object()


@pytest.mark.asyncio
async def test_kie_webhook_maps_comet_kind_to_prefixed_task_id(monkeypatch) -> None:
    get_generation_by_task_id = AsyncMock(
        return_value=SimpleNamespace(
            id=77,
            user_id=42,
            status=SimpleNamespace(value="processing"),
            gen_type=main.GenerationType.video,
            image_session_id=None,
            model="kling-2.6/image-to-video",
            prompt="animate",
            credits_spent=10,
            source_feed_gen_id=None,
            action_type=None,
        )
    )
    finish_generation = AsyncMock()

    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", get_generation_by_task_id)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=42, tg_id=555111)))
    monkeypatch.setattr(main.repo, "finish_generation", finish_generation)
    monkeypatch.setattr(main, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(main, "bot", None)

    payload = {
        "code": 0,
        "data": {
            "task_id": "kling_task_1",
            "task_status": "succeed",
            "task_result": {"videos": [{"url": "https://cdn.test/video.mp4"}]},
        },
    }

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/kie?secret=expected-secret&provider=comet&comet_kind=kling-image2video",
            json=payload,
        )

    assert response.status_code == 200
    assert get_generation_by_task_id.await_args.args == (_FAKE_SESSION, "comet:kling-image2video:kling_task_1")
    finish_generation.assert_awaited_once()
    assert finish_generation.await_args.args[1:] == (77, "https://cdn.test/video.mp4")

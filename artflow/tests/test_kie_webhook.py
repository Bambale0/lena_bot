from __future__ import annotations

from types import SimpleNamespace

import main

from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_success


def test_extract_task_id_from_nested_data_payload() -> None:
    payload = {"data": {"payload": "{\"taskId\":\"abc-123\"}"}}
    assert extract_task_id(payload) == "abc-123"


def test_extract_result_urls_deduplicates_ordered_urls() -> None:
    payload = {"data": {"resultUrls": ["https://a.test/1.png", "https://a.test/1.png"]}, "url": "https://a.test/2.png"}
    assert extract_result_urls(payload) == ["https://a.test/1.png", "https://a.test/2.png"]


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


def test_extract_error_prefers_nested_message() -> None:
    assert extract_error({"data": {"failMsg": "bad prompt"}}) == "bad prompt"


def test_kie_result_caption_hides_feed_prompt() -> None:
    gen = SimpleNamespace(prompt="secret feed prompt", source_feed_gen_id=42)
    assert main._kie_result_caption(gen) == "✅ <b>Готово!</b>"


def test_kie_result_caption_hides_own_prompt_preview() -> None:
    gen = SimpleNamespace(prompt="own prompt", source_feed_gen_id=None)
    assert main._kie_result_caption(gen) == "✅ <b>Готово!</b>"

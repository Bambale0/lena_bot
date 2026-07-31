from __future__ import annotations

from types import SimpleNamespace

from core.trends import (
    TREND_TAG,
    build_trend_tags,
    is_trend_prompt,
    trend_kind,
    trend_public_payload,
    trend_settings,
)
from db.models import PromptStatus


def prompt(**overrides):
    values = {
        "id": 7,
        "author_id": 1,
        "title": "Portrait",
        "description": "Upload a portrait",
        "prompt_text": "SECRET CANONICAL PROMPT",
        "preview_url": "https://cdn.example/preview.jpg",
        "model": "nano-banana-pro",
        "tags": [TREND_TAG],
        "likes": 2,
        "uses_count": 5,
        "status": PromptStatus.approved,
        "is_public": True,
        "created_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_public_trend_payload_never_exposes_prompt():
    payload = trend_public_payload(prompt())
    assert "prompt" not in payload
    assert "prompt_text" not in payload
    assert "prompt_template" not in payload
    assert payload["uses_count"] == 5


def test_video_settings_roundtrip_through_tags():
    tags = build_trend_tags("video", {
        "scenario": "image",
        "duration": 8,
        "ratio": "9:16",
        "resolution": "720p",
        "requires_reference": True,
    })
    item = prompt(tags=tags)
    assert is_trend_prompt(item)
    assert trend_kind(item) == "video"
    settings = trend_settings(item)
    assert settings["scenario"] == "image"
    assert settings["duration"] == 8
    assert settings["ratio"] == "9:16"
    assert settings["resolution"] == "720p"
    assert settings["requires_reference"] is True


def test_non_trend_is_not_accepted():
    assert not is_trend_prompt(prompt(tags=["cinematic"]))


def test_source_files_keep_admin_and_canonical_contracts():
    api = open("api/trends_routes.py", encoding="utf-8").read()
    mini = open("api/miniapp_routes.py", encoding="utf-8").read()
    bot = open("bot/handlers/trends.py", encoding="utf-8").read()
    web = open("webapp/src/main.jsx", encoding="utf-8").read()

    assert "Admin access required" in api
    assert '@router.post("/admin/trends"' in api
    assert '@router.post("/admin/trends/{trend_id}/archive")' in api
    assert 'user_prompt = prompt_source.prompt_text' in mini
    assert 'prompt_id: int | None = None' in mini
    assert 'hidden_prompt' in mini
    assert 'callback_data="menu:trends"' in open("bot/ui/main_menu.py", encoding="utf-8").read()
    assert 'Command("trends")' in bot
    assert 'api("/trends?limit=80")' in web
    assert 'api("/feed?source=top_day' not in web
    assert 'prompt_template' in web

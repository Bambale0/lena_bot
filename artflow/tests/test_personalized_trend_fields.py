from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.trend_user_fields import (
    TrendUserFieldsError,
    normalize_trend_user_fields,
    render_trend_prompt,
)
from core.trends import trend_admin_payload, trend_public_payload


def _trend(**overrides):
    values = {
        "id": 7, "author_id": 1, "title": "Birthday", "description": "Birthday",
        "prompt_text": "Happy birthday {{Возраст}}", "preview_url": "https://cdn.example/x.jpg",
        "model": "nano-banana-pro", "tags": ["trend"], "likes": 0, "uses_count": 9,
        "status": SimpleNamespace(value="approved"), "is_public": True, "created_at": None,
        "trend_user_fields": [{"key": "Возраст", "label": "Возраст", "type": "number", "required": True, "min": 1, "max": 120}],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_personalized_prompt_is_rendered_server_side() -> None:
    fields = normalize_trend_user_fields(_trend().trend_user_fields, prompt="Happy birthday {{Возраст}}")
    assert render_trend_prompt("Happy birthday {{Возраст}}", fields, {"Возраст": "28"}) == "Happy birthday 28"
    with pytest.raises(TrendUserFieldsError):
        render_trend_prompt("Happy birthday {{Возраст}}", fields, {"Возраст": "121"})


def test_public_payload_exposes_schema_but_not_hidden_prompt() -> None:
    payload = trend_public_payload(_trend())
    assert payload["user_fields"][0]["key"] == "Возраст"
    assert "prompt_template" not in payload and "prompt_text" not in payload


def test_old_trend_can_be_upgraded_in_place() -> None:
    legacy = _trend(prompt_text="Birthday video", trend_user_fields=[])
    assert trend_admin_payload(legacy)["settings"]["user_fields"] == []
    routes = open("api/trends_routes.py", encoding="utf-8").read()
    screen = open("webapp/src/features/trends-screen.tsx", encoding="utf-8").read()
    assert '@router.post("/admin/trends/{trend_id}/update")' in routes
    assert 'prompt.trend_user_fields = normalized_user_fields' in routes
    assert 'const endpoint = editingId ? `/admin/trends/${editingId}/update` : "/admin/trends"' in screen
    assert 'setUserFields(Array.isArray(settings.user_fields) ? settings.user_fields.slice(0, 6) : [])' in screen

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.trends import (
    TREND_TAG,
    build_trend_tags,
    render_trend_prompt,
    trend_public_payload,
    trend_settings,
)
from db.models import PromptStatus


def _prompt(tags: list[str], prompt_text: str = "Wear {{outfit}} with number {{number}}.") -> SimpleNamespace:
    return SimpleNamespace(
        id=77,
        author_id=1,
        title="Персональный тренд",
        description="Меняем номер, одежду и референсы",
        prompt_text=prompt_text,
        preview_url="https://cdn.example/trend.mp4",
        model="bytedance/seedance-2-5",
        tags=tags,
        likes=0,
        uses_count=1,
        status=PromptStatus.approved,
        is_public=True,
        created_at=None,
    )


def _settings() -> dict:
    return {
        "scenario": "image",
        "duration": 8,
        "resolution": "720p",
        "requires_reference": True,
        "min_references": 1,
        "max_references": 3,
        "user_fields": [
            {
                "key": "number",
                "label": "Номер",
                "type": "number",
                "required": True,
                "placeholder": "25",
                "max_length": 6,
            },
            {
                "key": "outfit",
                "label": "Одежда",
                "type": "text",
                "required": False,
                "placeholder": "Красное платье",
                "max_length": 80,
            },
        ],
    }


def test_trend_user_fields_and_reference_limits_roundtrip_without_exposing_prompt() -> None:
    item = _prompt(build_trend_tags("video", _settings()))

    settings = trend_settings(item)
    assert settings["min_references"] == 1
    assert settings["max_references"] == 3
    assert settings["user_fields"] == _settings()["user_fields"]

    public = trend_public_payload(item)
    assert public["min_references"] == 1
    assert public["max_references"] == 3
    assert public["user_fields"] == _settings()["user_fields"]
    assert "prompt" not in public
    assert "prompt_text" not in public
    assert "prompt_template" not in public


def test_render_trend_prompt_substitutes_fields_and_keeps_user_overrides_priority() -> None:
    item = _prompt(build_trend_tags("video", _settings()))
    settings = trend_settings(item)

    rendered = render_trend_prompt(
        item.prompt_text,
        settings["user_fields"],
        {"number": "25", "outfit": "чёрная кожаная куртка"},
    )

    assert "Wear чёрная кожаная куртка with number 25." in rendered
    assert "Номер: 25" in rendered
    assert "Одежда: чёрная кожаная куртка" in rendered
    assert "приоритет" in rendered.lower()


def test_render_trend_prompt_rejects_invalid_number_and_unknown_field() -> None:
    item = _prompt(build_trend_tags("video", _settings()))
    fields = trend_settings(item)["user_fields"]

    with pytest.raises(ValueError, match="Номер"):
        render_trend_prompt(item.prompt_text, fields, {"number": "twenty", "outfit": ""})

    with pytest.raises(ValueError, match="лишние"):
        render_trend_prompt(item.prompt_text, fields, {"number": "25", "hacker": "x"})


def test_trend_run_contract_accepts_multiple_signed_assets_and_user_values() -> None:
    source = open("api/trends_routes.py", encoding="utf-8").read()
    mini = open("api/miniapp_routes.py", encoding="utf-8").read()
    runner = open("webapp/src/features/trend-runner.tsx", encoding="utf-8").read()
    admin = open("webapp/src/features/trends-screen.tsx", encoding="utf-8").read()

    assert "asset_ids: list[str]" in source
    assert "user_values: dict[str, str]" in source
    assert "min_references" in source and "max_references" in source
    assert "trend_user_values" in mini
    assert "user_values: userValues" in runner
    assert "asset_ids:" in runner
    assert "Номер" in admin
    assert "Одежда" in admin
    assert "Минимум фото" in admin
    assert "Максимум фото" in admin

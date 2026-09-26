from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.trends import build_trend_tags, trend_public_payload, trend_user_fields
from db.models import PromptStatus


def _prompt(*, prompt_text: str, tags: list[str], trend_user_fields=None):
    return SimpleNamespace(
        id=7,
        author_id=1,
        title="Birthday",
        description="Personalized trend",
        prompt_text=prompt_text,
        preview_url="https://cdn.example/preview.jpg",
        model="nano-banana-pro",
        tags=tags,
        trend_user_fields=trend_user_fields,
        likes=0,
        uses_count=1,
        status=PromptStatus.approved,
        is_public=True,
        created_at=None,
    )


def test_trend_user_fields_support_numbers_and_clothing() -> None:
    from core.trend_user_fields import normalize_trend_user_fields

    fields = normalize_trend_user_fields(
        [
            {"key": "Число", "label": "Число"},
            {"key": "Одежда", "label": "Одежда"},
        ],
        prompt="Birthday cake {{Число}}",
    )

    assert fields == [
        {"key": "Число", "label": "Число", "type": "number", "required": True, "max_length": 160},
        {"key": "Одежда", "label": "Одежда", "type": "text", "required": True, "max_length": 160},
    ]


def test_legacy_placeholders_become_user_fields_automatically() -> None:
    from core.trend_user_fields import normalize_trend_user_fields

    fields = normalize_trend_user_fields([], prompt="Cake with {{Число}} candles; outfit: {{Одежда}}")

    assert [item["key"] for item in fields] == ["Число", "Одежда"]
    assert [item["type"] for item in fields] == ["number", "text"]


def test_render_trend_prompt_replaces_values_and_prioritizes_overrides() -> None:
    from core.trend_user_fields import render_trend_prompt

    fields = [
        {"key": "Число", "label": "Число", "type": "number", "required": True, "max_length": 160},
        {"key": "Одежда", "label": "Одежда", "type": "text", "required": True, "max_length": 160},
    ]
    rendered = render_trend_prompt(
        "A cake with {{Число}} candles. Keep the original outfit.",
        fields,
        {"Число": "27", "Одежда": "чёрное платье с длинными рукавами"},
    )

    assert "{{Число}}" not in rendered
    assert "27 candles" in rendered
    assert "- Число: 27" in rendered
    assert "- Одежда: чёрное платье с длинными рукавами" in rendered
    assert "значения ниже имеют приоритет" in rendered


@pytest.mark.parametrize("value", ["twenty", "12 years", "++12"])
def test_number_field_rejects_non_numeric_values(value: str) -> None:
    from core.trend_user_fields import TrendUserFieldsError, render_trend_prompt

    fields = [{"key": "Число", "label": "Число", "type": "number", "required": True, "max_length": 160}]
    with pytest.raises(TrendUserFieldsError, match="должно быть числом"):
        render_trend_prompt("Number {{Число}}", fields, {"Число": value})


def test_undeclared_user_value_is_rejected() -> None:
    from core.trend_user_fields import TrendUserFieldsError, render_trend_prompt

    fields = [{"key": "Одежда", "label": "Одежда", "type": "text", "required": True, "max_length": 160}]
    with pytest.raises(TrendUserFieldsError, match="лишние поля"):
        render_trend_prompt("Keep composition", fields, {"Одежда": "костюм", "provider": "other"})


def test_trend_tags_roundtrip_personalization_without_exposing_prompt() -> None:
    tags = build_trend_tags(
        "image",
        {
            "category": "holidays",
            "requires_reference": True,
            "user_fields": [
                {"key": "Число", "label": "Число"},
                {"key": "Одежда", "label": "Одежда"},
            ],
        },
    )
    item = _prompt(prompt_text="SECRET {{Число}}", tags=tags)

    fields = trend_user_fields(item)
    assert [field["key"] for field in fields] == ["Число", "Одежда"]

    public = trend_public_payload(item)
    assert public["user_fields"] == fields
    assert "prompt" not in public
    assert "prompt_text" not in public
    assert "prompt_template" not in public


def test_api_contract_accepts_user_values_and_renders_hidden_prompt_server_side() -> None:
    source = Path("api/trends_routes.py").read_text(encoding="utf-8")
    miniapp = Path("api/miniapp_routes.py").read_text(encoding="utf-8")

    assert "user_values: dict[str, str]" in source
    assert "trend_user_values" in miniapp
    assert "render_trend_prompt" in miniapp


def test_miniapp_trend_runner_exposes_personalization_fields_before_generation() -> None:
    source = Path("webapp/src/features/trend-runner.tsx").read_text(encoding="utf-8")
    types = Path("webapp/src/lib/types.ts").read_text(encoding="utf-8")

    assert "TrendUserField" in types
    assert "user_fields?: TrendUserField[]" in types
    assert "userValues" in source
    assert "trend.user_fields" in source
    assert "Параметры тренда" in source
    assert "user_values: values" in source


def test_admin_trend_form_can_configure_number_and_clothing_fields() -> None:
    source = Path("webapp/src/features/trends-screen.tsx").read_text(encoding="utf-8")

    assert "Поля для пользователя" in source
    assert '"Число"' in source
    assert '"Одежда"' in source
    assert "user_fields" in source
    assert "/admin/trends/${trend.id}/update" in source


def test_explicit_empty_user_fields_disable_legacy_placeholder_inputs() -> None:
    tags = build_trend_tags(
        "image",
        {
            "category": "holidays",
            "requires_reference": True,
            "user_fields": [],
        },
    )
    item = _prompt(prompt_text="Legacy {{Число}} placeholder", tags=tags)

    assert trend_user_fields(item) == []


def test_explicit_user_fields_survive_repository_tag_normalization() -> None:
    from db.prompt_repository import _normalize_tags

    explicit_fields = [
        {"key": "Число", "label": "Число", "type": "number", "required": True, "max_length": 160},
        {"key": "Одежда", "label": "Одежда", "type": "text", "required": True, "max_length": 160},
    ]
    persisted_tags = _normalize_tags(build_trend_tags(
        "image",
        {
            "category": "holidays",
            "requires_reference": True,
            "user_fields": explicit_fields,
        },
    ))
    item = _prompt(
        prompt_text="Keep the scene",
        tags=persisted_tags,
        trend_user_fields=explicit_fields,
    )

    assert [field["key"] for field in trend_user_fields(item)] == ["Число", "Одежда"]

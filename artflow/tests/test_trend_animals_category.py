from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.trends import TREND_TAG, build_trend_tags, trend_category, trend_public_payload
from db.models import PromptStatus

ROOT = Path(__file__).resolve().parents[1]


def _prompt(tags: list[str]):
    return SimpleNamespace(
        id=77,
        author_id=1,
        title="Pet trend",
        description="Upload a pet photo",
        prompt_text="SECRET",
        preview_url="https://cdn.example/pet.jpg",
        model="nano-banana-pro",
        tags=tags,
        likes=0,
        uses_count=0,
        status=PromptStatus.approved,
        is_public=True,
        created_at=None,
    )


def test_animals_category_roundtrips_through_backend_tags() -> None:
    tags = build_trend_tags("image", {"category": "animals", "requires_reference": True})
    assert TREND_TAG in tags
    assert "trend-category:animals" in tags

    item = _prompt(tags)
    assert trend_category(item) == "animals"
    payload = trend_public_payload(item)
    assert payload["category"] == "animals"
    assert payload["category_title"] == "С животными"
    assert payload["category_emoji"] == "🦁"


def test_production_trends_screen_exposes_and_submits_animals_category() -> None:
    source = (ROOT / "webapp" / "src" / "features" / "trends-screen.tsx").read_text(encoding="utf-8")
    assert '{ value: "animals", label: "С животными", emoji: "🦁" }' in source
    assert "setCategory(\"animals\")" in source
    assert "category," in source
    assert 'category === "animals" ? "🦁 Опубликовать в «С животными»"' in source

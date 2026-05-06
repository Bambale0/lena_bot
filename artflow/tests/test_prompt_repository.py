from __future__ import annotations

from db.models import PromptCategory
from db.prompt_repository import derive_description, derive_title, infer_category, infer_tags


def test_infer_tags_detects_cinematic_prompt() -> None:
    assert "cinematic" in infer_tags("cinematic film still with dramatic light")


def test_infer_category_detects_marketing_prompt() -> None:
    assert infer_category("brand marketing advert", []) == PromptCategory.marketing


def test_derive_title_truncates_long_prompt() -> None:
    title = derive_title("x" * 100)
    assert len(title) == 60


def test_derive_description_truncates_long_prompt() -> None:
    description = derive_description("x" * 250)
    assert len(description) == 200

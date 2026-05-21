from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db.models import PromptCategory, PromptStatus
from db.prompt_repository import (
    derive_description,
    derive_title,
    infer_category,
    infer_tags,
    like_prompt,
)


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


@pytest.mark.asyncio
async def test_like_prompt_rejects_pending_prompt_before_insert(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        "db.prompt_repository.get_prompt_by_id",
        AsyncMock(return_value=SimpleNamespace(status=PromptStatus.pending, is_public=True)),
    )

    prompt, status = await like_prompt(session, prompt_id=7, user_id=42)

    assert prompt is None
    assert status == "missing"
    session.execute.assert_not_awaited()

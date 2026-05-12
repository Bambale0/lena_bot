from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.services import assistant_moderator


@pytest.fixture(autouse=True)
def _allow_admin_access(monkeypatch) -> None:
    monkeypatch.setattr(assistant_moderator, "is_admin_tg_id", lambda _tg_id: True)


@pytest.mark.asyncio
async def test_try_handle_admin_request_stats() -> None:
    with patch.object(
        assistant_moderator,
        "repo",
        AsyncMock(
            count_users=AsyncMock(return_value=42),
            count_generations_today=AsyncMock(return_value=17),
            get_revenue_today=AsyncMock(return_value=3210.5),
            get_pending_withdrawal_requests=AsyncMock(return_value=[object(), object()]),
        ),
    ), patch.object(
        assistant_moderator.prompt_repository,
        "get_pending_prompts",
        AsyncMock(return_value=[object(), object(), object()]),
    ):
        outcome = await assistant_moderator.try_handle_admin_request(
            "статистика",
            session=AsyncMock(),
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    assert "42" in outcome.text
    assert "17" in outcome.text
    assert "3210.50₽" in outcome.text
    assert "Промптов на модерации: 3" in outcome.text


@pytest.mark.asyncio
async def test_try_handle_admin_request_bans_user() -> None:
    user = SimpleNamespace(id=7, tg_id=123456, username="tester", full_name="Test User")
    with patch.object(
        assistant_moderator,
        "repo",
        AsyncMock(
            get_user_by_tg_id=AsyncMock(return_value=user),
            ban_user=AsyncMock(return_value=True),
        ),
    ):
        outcome = await assistant_moderator.try_handle_admin_request(
            "забань 123456",
            session=AsyncMock(),
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    assert "забанен" in outcome.text.lower()
    assert "123456" in outcome.text


@pytest.mark.asyncio
async def test_try_handle_admin_request_user_lookup_by_username() -> None:
    user = SimpleNamespace(
        id=9,
        tg_id=777000,
        username="moderated_user",
        full_name="Moderated User",
        credits=155.0,
        referral_balance=19.5,
        is_subscribed=False,
        is_banned=True,
    )
    snapshot = SimpleNamespace(available_to_withdraw=10.0, pending_withdrawals=9.5)
    with patch.object(
        assistant_moderator,
        "repo",
        AsyncMock(
            get_user_by_username=AsyncMock(return_value=user),
            get_user_referral_balance_snapshot=AsyncMock(return_value=snapshot),
        ),
    ):
        outcome = await assistant_moderator.try_handle_admin_request(
            "найди @moderated_user",
            session=AsyncMock(),
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    assert "@moderated_user" in outcome.text
    assert "155" in outcome.text
    assert "Бан: да" in outcome.text


@pytest.mark.asyncio
async def test_try_handle_admin_request_reject_prompt_requires_reason() -> None:
    outcome = await assistant_moderator.try_handle_admin_request(
        "отклони промпт 42",
        session=AsyncMock(),
        bot=AsyncMock(),
        admin_tg_id=1,
    )

    assert outcome is not None
    assert "укажи причину" in outcome.text.lower()


@pytest.mark.asyncio
async def test_try_handle_admin_request_ignores_non_admin() -> None:
    with patch.object(assistant_moderator, "is_admin_tg_id", return_value=False):
        outcome = await assistant_moderator.try_handle_admin_request(
            "проверь промпт 42",
            session=AsyncMock(),
            bot=AsyncMock(),
            admin_tg_id=999,
        )

    assert outcome is None


@pytest.mark.asyncio
async def test_try_handle_admin_request_reviews_prompt() -> None:
    prompt = SimpleNamespace(
        id=42,
        title="Cyber city",
        description="Neon city",
        prompt_text="cinematic cyberpunk city at night",
        tags=["cyberpunk", "cinematic"],
        model="seedream-4.5",
    )
    with patch.object(
        assistant_moderator.prompt_repository,
        "get_prompt_by_id",
        AsyncMock(return_value=prompt),
    ), patch.object(
        assistant_moderator,
        "generate_prompt_moderation_review",
        AsyncMock(return_value="Вердикт: Одобрить"),
    ) as review_mock:
        outcome = await assistant_moderator.try_handle_admin_request(
            "проверь промпт 42",
            session=AsyncMock(),
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    assert "Cyber city" in outcome.text
    assert "Вердикт: Одобрить" in outcome.text
    review_mock.assert_awaited_once()

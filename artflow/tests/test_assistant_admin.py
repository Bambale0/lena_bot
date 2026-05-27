from __future__ import annotations

from datetime import datetime, timezone
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
async def test_try_handle_admin_request_user_summary_by_username() -> None:
    user = SimpleNamespace(
        id=9,
        tg_id=777000,
        username="moderated_user",
        full_name="Moderated User",
    )
    session = AsyncMock()
    with patch.object(
        assistant_moderator,
        "repo",
        AsyncMock(get_user_by_username=AsyncMock(return_value=user)),
    ), patch.object(
        assistant_moderator,
        "_build_user_brief_report",
        AsyncMock(return_value="Сводка по пользователю\nЛюбимая ИИ: nano-banana-pro"),
    ) as report_mock:
        outcome = await assistant_moderator.try_handle_admin_request(
            "пришли сводку @moderated_user",
            session=session,
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    assert "Любимая ИИ" in outcome.text
    report_mock.assert_awaited_once_with(session, user)


@pytest.mark.asyncio
async def test_try_handle_admin_request_user_summary_by_db_id() -> None:
    user = SimpleNamespace(
        id=273,
        tg_id=6006348428,
        username="msBelovaE",
        full_name="Елена Белова",
    )
    session = AsyncMock()
    repo_stub = AsyncMock(get_user_by_id=AsyncMock(return_value=user))
    with patch.object(
        assistant_moderator,
        "repo",
        repo_stub,
    ), patch.object(
        assistant_moderator,
        "_build_user_brief_report",
        AsyncMock(return_value="Сводка по пользователю"),
    ):
        outcome = await assistant_moderator.try_handle_admin_request(
            "отчет db id 273",
            session=session,
            bot=AsyncMock(),
            admin_tg_id=1,
        )

    assert outcome is not None
    repo_stub.get_user_by_id.assert_awaited_once_with(session, 273)


@pytest.mark.asyncio
async def test_try_handle_admin_request_user_summary_requires_identifier() -> None:
    outcome = await assistant_moderator.try_handle_admin_request(
        "пришли сводку",
        session=AsyncMock(),
        bot=AsyncMock(),
        admin_tg_id=1,
    )

    assert outcome is not None
    assert "Укажи пользователя" in outcome.text


def test_format_user_brief_report_contains_payments_referrals_and_favorite_ai() -> None:
    user = SimpleNamespace(
        tg_id=6006348428,
        username="msBelovaE",
        full_name="Елена Белова",
        created_at=datetime(2026, 5, 12, 23, 16, tzinfo=timezone.utc),
        is_banned=False,
        is_subscribed=False,
        credits=37.95,
        referral_balance=0.0,
    )
    paid_transactions = [
        SimpleNamespace(
            id=147,
            amount_rub=150.0,
            credits=15.0,
            provider="tbank",
            created_at=datetime(2026, 5, 17, 19, 36, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=172,
            amount_rub=250.0,
            credits=25.0,
            provider="tbank",
            created_at=datetime(2026, 5, 19, 7, 3, tzinfo=timezone.utc),
        ),
    ]

    text = assistant_moderator._format_user_brief_report(
        user=user,
        paid_transactions=paid_transactions,
        direct_referrals_count=13,
        second_line_referrals_count=1,
        direct_referrals_paid_total=0.0,
        signup_bonus_credits=65.0,
        generations_total=29,
        generations_done=27,
        generations_failed=2,
        credits_spent=87.5,
        favorite_model=("nano-banana-pro", 27, 82.5),
    )

    assert "@msBelovaE" in text
    assert "Всего paid: 400₽" in text
    assert "Прямых: 13" in text
    assert "Любимая ИИ: nano-banana-pro" in text
    assert "LeLu88" not in text
    assert "id 1" not in text.lower()


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

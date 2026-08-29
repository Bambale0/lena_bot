from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from db.models import TransactionStatus
from db.referral_reward_policy import (
    LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE,
    REFERRAL_FIRST_TOPUP_ENTRY_TYPE,
    REFERRAL_FIRST_TOPUP_SOURCE_TYPE,
    award_referral_first_topup,
    install_referral_reward_policy,
)


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _session(*execute_results):
    return SimpleNamespace(
        execute=AsyncMock(side_effect=list(execute_results)),
        add=MagicMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def _policy_repo(**overrides):
    values = {
        "add_credits": AsyncMock(return_value=0.0),
        "bind_user_referrer_once": AsyncMock(return_value=False),
        "get_user_by_id": AsyncMock(return_value=SimpleNamespace(credits=0.0)),
        "confirm_transaction": AsyncMock(return_value=None),
        "confirm_transaction_and_add_credits": AsyncMock(return_value=None),
        "confirm_transaction_by_id": AsyncMock(return_value=None),
        "get_transaction_by_external_id": AsyncMock(return_value=None),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_first_paid_topup_credits_referrer_once(monkeypatch) -> None:
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_FREEZE", False)
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_L1_CREDITS", 3)

    referred = SimpleNamespace(id=22, tg_id=220022, referrer_id=7)
    tx = SimpleNamespace(
        id=101,
        user_id=22,
        status=TransactionStatus.paid,
        amount_rub=500,
        credits=50,
    )
    session = _session(
        _result(referred),
        _result(101),
        _result(None),
        _result(13.0),
    )

    created = await award_referral_first_topup(session, tx)

    assert created is True
    entry = session.add.call_args.args[0]
    assert entry.user_id == 7
    assert entry.delta == 3
    assert entry.balance_after == 13
    assert entry.entry_type == REFERRAL_FIRST_TOPUP_ENTRY_TYPE
    assert entry.source_type == REFERRAL_FIRST_TOPUP_SOURCE_TYPE
    assert entry.source_id == "22"
    assert "transaction_id=101" in entry.note
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_later_paid_topup_cannot_create_first_topup_bonus(monkeypatch) -> None:
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_FREEZE", False)
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_L1_CREDITS", 3)

    referred = SimpleNamespace(id=22, tg_id=220022, referrer_id=7)
    second_tx = SimpleNamespace(
        id=102,
        user_id=22,
        status=TransactionStatus.paid,
        amount_rub=500,
        credits=50,
    )
    session = _session(_result(referred), _result(101))

    created = await award_referral_first_topup(session, second_tx)

    assert created is False
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_signup_reward_blocks_migration_double_bonus(monkeypatch) -> None:
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_FREEZE", False)
    monkeypatch.setattr("db.referral_reward_policy.settings.REFERRAL_L1_CREDITS", 3)

    referred = SimpleNamespace(id=22, tg_id=220022, referrer_id=7)
    tx = SimpleNamespace(
        id=101,
        user_id=22,
        status=TransactionStatus.paid,
        amount_rub=500,
        credits=50,
    )
    session = _session(_result(referred), _result(101), _result(999))

    created = await award_referral_first_topup(session, tx)

    assert created is False
    session.add.assert_not_called()
    session.commit.assert_awaited_once()

    ledger_query = session.execute.await_args_list[2].args[0]
    sql = str(ledger_query.compile(compile_kwargs={"literal_binds": True}))
    assert LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE in sql
    assert "220022" in sql
    assert "22" in sql


@pytest.mark.asyncio
async def test_policy_suppresses_signup_credit_but_preserves_other_credit_writes() -> None:
    original_add = AsyncMock(return_value=99.0)
    repo = _policy_repo(
        add_credits=original_add,
        get_user_by_id=AsyncMock(return_value=SimpleNamespace(credits=12.0)),
    )

    install_referral_reward_policy(
        repo,
        award_func=AsyncMock(return_value=False),
        settle_func=AsyncMock(return_value=False),
    )

    deferred_balance = await repo.add_credits(
        object(),
        7,
        3,
        entry_type=LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE,
        source_type="user",
        source_id="22",
    )
    regular_balance = await repo.add_credits(
        object(),
        7,
        5,
        entry_type="admin_adjustment",
    )

    assert deferred_balance == 12
    assert regular_balance == 99
    assert original_add.await_count == 1
    assert original_add.await_args.kwargs["entry_type"] == "admin_adjustment"


@pytest.mark.asyncio
async def test_payment_retry_recovers_missing_first_topup_reward() -> None:
    paid_tx = SimpleNamespace(
        id=101,
        user_id=22,
        status=TransactionStatus.paid,
        amount_rub=500,
        credits=50,
    )
    award = AsyncMock(return_value=True)
    repo = _policy_repo(
        get_transaction_by_external_id=AsyncMock(return_value=paid_tx),
    )

    install_referral_reward_policy(
        repo,
        award_func=award,
        settle_func=AsyncMock(return_value=False),
    )

    result = await repo.confirm_transaction_and_add_credits(object(), "paid-101")

    assert result is None
    award.assert_awaited_once_with(ANY, paid_tx)


@pytest.mark.asyncio
async def test_late_referral_bind_settles_existing_first_paid_topup() -> None:
    original_bind = AsyncMock(return_value=True)
    settle = AsyncMock(return_value=True)
    repo = _policy_repo(bind_user_referrer_once=original_bind)
    session = object()
    referrer = SimpleNamespace(id=7)

    install_referral_reward_policy(
        repo,
        award_func=AsyncMock(return_value=False),
        settle_func=settle,
    )

    bound = await repo.bind_user_referrer_once(
        session,
        22,
        referrer=referrer,
        referrer_l2=None,
        referrer_l3=None,
    )

    assert bound is True
    original_bind.assert_awaited_once_with(
        session,
        22,
        referrer=referrer,
        referrer_l2=None,
        referrer_l3=None,
    )
    settle.assert_awaited_once_with(session, 22)

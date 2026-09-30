from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import main


@pytest.mark.asyncio
async def test_accrual_records_transaction_level_and_notifies_only_new_entries(monkeypatch) -> None:
    payer = SimpleNamespace(id=77, referrer_id=10, referrer_l2_id=20, referrer_l3_id=30)
    tx = SimpleNamespace(id=900, amount_rub=1900.0, external_id="ext-900", provider="tbank")
    record = AsyncMock(
        side_effect=[
            SimpleNamespace(id=1, amount_rub=760.0),
            SimpleNamespace(id=2, amount_rub=133.0),
            SimpleNamespace(id=3, amount_rub=57.0),
        ]
    )
    get_user = AsyncMock(
        side_effect=[
            SimpleNamespace(tg_id=1010),
            SimpleNamespace(tg_id=2020),
            SimpleNamespace(tg_id=3030),
        ]
    )
    bot = AsyncMock()
    monkeypatch.setattr(main.repo, "record_referral_commission", record)
    monkeypatch.setattr(main.repo, "get_user_by_id", get_user)

    await main._accrue_referral_commissions(object(), payer, tx, bot)

    assert record.await_count == 3
    first = record.await_args_list[0].kwargs
    assert first == {
        "transaction_id": 900,
        "payer_user_id": 77,
        "recipient_user_id": 10,
        "level": 1,
        "rate": 0.40,
        "payment_amount_rub": 1900.0,
        "amount_rub": 760.0,
        "event_type": "accrual",
    }
    assert bot.send_message.await_count == 3


@pytest.mark.asyncio
async def test_duplicate_accrual_does_not_notify_or_change_balance_twice(monkeypatch) -> None:
    payer = SimpleNamespace(id=77, referrer_id=10, referrer_l2_id=None, referrer_l3_id=None)
    tx = SimpleNamespace(id=900, amount_rub=500.0, external_id="ext-900", provider="tbank")
    monkeypatch.setattr(main.repo, "record_referral_commission", AsyncMock(return_value=None))
    get_user = AsyncMock()
    monkeypatch.setattr(main.repo, "get_user_by_id", get_user)
    bot = AsyncMock()

    await main._accrue_referral_commissions(object(), payer, tx, bot)

    get_user.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_records_negative_reversal_against_same_transaction(monkeypatch) -> None:
    payer = SimpleNamespace(id=77, referrer_id=10, referrer_l2_id=20, referrer_l3_id=None)
    tx = SimpleNamespace(id=900, amount_rub=500.0, external_id="ext-900", provider="tbank")
    record = AsyncMock(return_value=SimpleNamespace(id=1))
    monkeypatch.setattr(main.repo, "record_referral_commission", record)
    monkeypatch.setattr(main.repo, "get_referral_commissions_for_transaction", AsyncMock(return_value=[]))

    await main._reverse_referral_commissions(object(), payer, tx)

    assert record.await_count == 2
    first = record.await_args_list[0].kwargs
    assert first["transaction_id"] == 900
    assert first["payer_user_id"] == 77
    assert first["recipient_user_id"] == 10
    assert first["level"] == 1
    assert first["rate"] == 0.40
    assert first["payment_amount_rub"] == 500.0
    assert first["amount_rub"] == -200.0
    assert first["event_type"] == "reversal"


@pytest.mark.asyncio
async def test_refund_mirrors_original_ledger_amount_even_if_current_rate_changed(monkeypatch) -> None:
    session = object()
    payer = SimpleNamespace(id=77, referrer_id=999, referrer_l2_id=None, referrer_l3_id=None)
    tx = SimpleNamespace(id=901, amount_rub=500.0, external_id="ext-901", provider="tbank")
    original = SimpleNamespace(
        level=1,
        recipient_user_id=10,
        rate=0.30,
        payment_amount_rub=500.0,
        amount_rub=150.0,
    )
    monkeypatch.setattr(
        main.repo,
        "get_referral_commissions_for_transaction",
        AsyncMock(return_value=[original]),
    )
    record = AsyncMock(return_value=SimpleNamespace(id=2))
    monkeypatch.setattr(main.repo, "record_referral_commission", record)

    await main._reverse_referral_commissions(session, payer, tx)

    record.assert_awaited_once_with(
        session,
        transaction_id=901,
        payer_user_id=77,
        recipient_user_id=10,
        level=1,
        rate=0.30,
        payment_amount_rub=500.0,
        amount_rub=-150.0,
        event_type="reversal",
    )

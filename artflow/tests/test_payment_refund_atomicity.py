"""Refund HTTP -> real PostgreSQL -> wallet/immutable ledgers.

Use a disposable PostgreSQL DSN; every test owns a unique schema and removes
only that schema. No production configuration or provider requests are used.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import main
from db.models import (
    Base,
    CreditLedgerEntry,
    PaymentProvider,
    ReferralCommissionLedger,
    Transaction,
    TransactionStatus,
    User,
)
from payments.tbank import make_token


@pytest_asyncio.fixture
async def payment_db(monkeypatch):
    url = os.environ.get("APIX_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL; exercised by backend-quality CI")
    schema = "audit_payment_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}},
    )
    names = {"users", "transactions", "credit_ledger", "referral_commission_ledger", "payment_refund_events", "payment_refund_notices"}
    tables = [t for t in Base.metadata.sorted_tables if t.name in names]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "AsyncSessionLocal", factory)
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.settings, "TBANK_PASSWORD", "test-refund-signature")
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "test-refund-signature")
    try:
        yield factory, engine
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed_payment(factory, provider, *, status=TransactionStatus.paid, balance=50.0):
    async with factory() as session:
        payer = User(tg_id=999001, referral_code="test-payer", credits=balance)
        parent = User(tg_id=999002, referral_code="test-parent", credits=0, referral_balance=15)
        session.add_all([payer, parent])
        await session.flush()
        payer.referrer_id = parent.id
        tx = Transaction(
            user_id=payer.id, amount_rub=500, credits=50, provider=provider,
            external_id="digital:78901" if provider == PaymentProvider.tribute else "test-payment-1",
            status=status,
        )
        session.add(tx)
        await session.flush()
        if status == TransactionStatus.paid:
            session.add(CreditLedgerEntry(
                user_id=payer.id, delta=50, balance_after=balance,
                entry_type="payment_credit", source_type="transaction", source_id=str(tx.id),
            ))
            session.add(ReferralCommissionLedger(
                transaction_id=tx.id, payer_user_id=payer.id, recipient_user_id=parent.id,
                level=1, rate=0.03, payment_amount_rub=500, amount_rub=15,
                balance_after_rub=15, event_type="accrual",
            ))
        await session.commit()
        return tx.id, payer.id, parent.id


def signed_refund(kind, *, status="REFUNDED", amount=50000):
    if kind == "tbank":
        payload = {"Success": True, "Status": status, "PaymentId": "test-payment-1", "OrderId": "test-order", "Amount": amount}
        payload["Token"] = make_token(payload, "test-refund-signature")
        return "/webhook/tbank", json.dumps(payload).encode(), {}
    payload = {
        "name": "digital_product_refunded" if kind == "digital" else "shop_order_refunded",
        "payload": {
            "uuid": "digital:78901", "product_id": 152362, "purchase_id": 78901,
            "amount": 200 if kind == "digital" else 50000,
            "currency": "usd" if kind == "digital" else "rub", "status": "refunded",
        },
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test-refund-signature", body, hashlib.sha256).hexdigest()
    return "/webhook/tribute", body, {"trbt-signature": signature}


async def post_refund(kind, **kwargs):
    path, body, headers = signed_refund(kind, **kwargs)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.post(path, content=body, headers={"content-type": "application/json", **headers})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tbank", "shop", "digital"])
async def test_refund_storage_failure_rolls_back_status_and_balance(payment_db, kind):
    factory, engine = payment_db
    provider = PaymentProvider.tbank if kind == "tbank" else PaymentProvider.tribute
    tx_id, payer_id, _ = await seed_payment(factory, provider)

    def fail_ledger_write(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("INSERT INTO CREDIT_LEDGER"):
            raise RuntimeError("injected ledger storage failure")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_ledger_write)
    try:
        with pytest.raises(RuntimeError, match="injected ledger storage failure"):
            await post_refund(kind)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_ledger_write)
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
        assert (await session.get(User, payer_id)).credits == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tbank", "shop", "digital"])
async def test_repeated_refund_changes_wallet_and_referral_once(payment_db, kind):
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(
        factory, PaymentProvider.tbank if kind == "tbank" else PaymentProvider.tribute,
        balance=10,  # Spent funds are accounted for, not silently clamped.
    )
    responses = await asyncio.gather(*[post_refund(kind) for _ in range(5)])
    assert all(r.status_code == 200 for r in responses)
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.refunded
        assert (await session.get(User, payer_id)).credits == -40
        assert (await session.get(User, parent_id)).referral_balance == 0
        refunds = list((await session.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.entry_type == "payment_refund"))).all())
        assert len(refunds) == 1
        assert refunds[0].delta == -50


@pytest.mark.asyncio
async def test_partial_refunds_are_cumulative_stale_safe_and_finish_exactly(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    for remaining, expected_balance, expected_parent in [
        (40000, 40, 12), (25000, 25, 7.5), (40000, 25, 7.5), (25000, 25, 7.5),
    ]:
        response = await post_refund("tbank", status="PARTIAL_REFUNDED", amount=remaining)
        assert response.status_code == 200
        async with factory() as session:
            assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
            assert (await session.get(User, payer_id)).credits == expected_balance
            assert (await session.get(User, parent_id)).referral_balance == expected_parent
    assert (await post_refund("tbank", amount=0)).status_code == 200
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 0
        assert (await session.get(User, parent_id)).referral_balance == 0
        rows = list((await session.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.entry_type == "payment_refund"))).all())
        assert len(rows) == 3
        assert sum(row.delta for row in rows) == -50


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [None, True, -1, 1.5, 50001, "NaN"])
async def test_invalid_partial_amount_never_changes_balance(payment_db, amount):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=amount)).status_code == 503
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
        assert (await session.get(User, payer_id)).credits == 50


@pytest.mark.asyncio
async def test_partial_authorization_reversal_never_refunds_paid_wallet(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank", status="PARTIAL_REVERSED", amount=40000)).status_code == 200
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
        assert (await session.get(User, payer_id)).credits == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["CANCELED", "REJECTED", "AUTH_FAIL"])
async def test_late_failure_cannot_overwrite_paid_transaction(payment_db, status):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank", status=status)).status_code == 200
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
        assert (await session.get(User, payer_id)).credits == 50
    assert (await post_refund("tbank")).status_code == 200
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 0


@pytest.mark.asyncio
async def test_referral_accrual_after_refund_is_not_resurrected(payment_db):
    from db import repository as repo

    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank")).status_code == 200
    async with factory() as session:
        result = await repo.record_referral_commission(
            session, transaction_id=tx_id, payer_user_id=payer_id, recipient_user_id=parent_id,
            level=2, rate=0.03, payment_amount_rub=500, amount_rub=15, event_type="accrual",
        )
        assert result is None
        assert (await session.get(User, parent_id)).referral_balance == 0


@pytest.mark.asyncio
async def test_partial_refund_before_confirmation_requests_retry(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank, status=TransactionStatus.pending, balance=0)
    response = await post_refund("tbank", status="PARTIAL_REFUNDED", amount=40000)
    assert response.status_code == 503
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.pending
        assert (await session.get(User, payer_id)).credits == 0


@pytest.mark.asyncio
async def test_full_refund_before_confirmation_prevents_late_credit(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank, status=TransactionStatus.pending, balance=0)
    assert (await post_refund("tbank")).status_code == 200
    assert (await post_refund("tbank", status="CONFIRMED")).status_code == 200
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.refunded
        assert (await session.get(User, payer_id)).credits == 0


@pytest.mark.asyncio
async def test_late_referral_accrual_after_partial_refund_is_prorated_and_reversible(payment_db):
    from db import repository as repo
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 200
    async with factory() as session:
        entry = await repo.record_referral_commission(
            session, transaction_id=tx_id, payer_user_id=payer_id, recipient_user_id=parent_id,
            level=2, rate=0.02, payment_amount_rub=500, amount_rub=10, event_type="accrual",
        )
        assert entry is not None
        assert (await session.get(User, parent_id)).referral_balance == 12.5
    assert (await post_refund("tbank", amount=0)).status_code == 200
    async with factory() as session:
        assert (await session.get(User, parent_id)).referral_balance == 0


@pytest.mark.asyncio
async def test_concurrent_referral_and_partial_refund_have_one_net_effect(payment_db):
    from db import repository as repo
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    async def accrue():
        async with factory() as session:
            return await repo.record_referral_commission(
                session, transaction_id=tx_id, payer_user_id=payer_id, recipient_user_id=parent_id,
                level=2, rate=0.02, payment_amount_rub=500, amount_rub=10, event_type="accrual",
            )
    await asyncio.gather(accrue(), accrue(), post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000))
    async with factory() as session:
        assert (await session.get(User, parent_id)).referral_balance == 12.5
        assert (await session.get(User, payer_id)).credits == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [PaymentProvider.tbank, PaymentProvider.cryptobot, PaymentProvider.lava])
async def test_status_check_payment_credit_is_atomic(payment_db, monkeypatch, provider):
    from unittest.mock import AsyncMock

    from bot.handlers import payment
    factory, engine = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, provider, status=TransactionStatus.pending, balance=0)
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value={"Status": "CONFIRMED"}))
    monkeypatch.setattr(payment.cryptobot, "get_invoice", AsyncMock(return_value={"status": "paid"}))
    monkeypatch.setattr(payment.lava, "get_invoice", AsyncMock(return_value={"status": "paid"}))
    monkeypatch.setattr(main.settings, "REFERRAL_L1_CREDITS", 0)
    def fail_credit(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("INSERT INTO CREDIT_LEDGER"):
            raise RuntimeError("injected credit failure")
    event.listen(engine.sync_engine, "before_cursor_execute", fail_credit)
    try:
        async with factory() as session:
            tx = await session.get(Transaction, tx_id)
            # Crypto invoice IDs are numeric in the provider contract.
            if provider == PaymentProvider.cryptobot:
                tx.external_id = "12345"
                await session.commit()
            with pytest.raises(RuntimeError, match="injected credit failure"):
                await payment._reconcile_transaction_status(session, tx)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_credit)
    async with factory() as session:
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.pending
        assert (await session.get(User, payer_id)).credits == 0


@pytest.mark.asyncio
async def test_status_check_uses_same_partial_refund_as_webhook(payment_db, monkeypatch):
    from unittest.mock import AsyncMock

    from bot.handlers import payment
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value={"Status": "PARTIAL_REFUNDED", "Amount": 25000}))
    async with factory() as session:
        status, _ = await payment._reconcile_transaction_status(session, await session.get(Transaction, tx_id))
        assert status == TransactionStatus.paid
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 200
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 25
        assert len(list((await session.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.entry_type == "payment_refund"))).all())) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,provider", [("tbank", PaymentProvider.tbank), ("digital", PaymentProvider.tribute)])
async def test_full_refund_before_local_transaction_prevents_late_credit(payment_db, monkeypatch, kind, provider):
    from db import repository as repo
    factory, _ = payment_db
    monkeypatch.setattr(main.settings, "REFERRAL_L1_CREDITS", 0)
    response = await post_refund(kind)
    assert response.status_code == 200
    tx_id, payer_id, _ = await seed_payment(factory, provider, status=TransactionStatus.pending, balance=0)
    async with factory() as session:
        tx = await session.get(Transaction, tx_id)
        result = await repo.confirm_transaction_and_add_credits(session, tx.external_id)
        assert result is None
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 0
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.refunded


@pytest.mark.asyncio
async def test_unknown_shop_refund_is_retained_before_confirmation(payment_db, monkeypatch):
    from db import repository as repo
    factory, _ = payment_db
    monkeypatch.setattr(main.settings, "REFERRAL_L1_CREDITS", 0)
    assert (await post_refund("shop", amount=50000)).status_code == 200
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tribute, status=TransactionStatus.pending, balance=0)
    async with factory() as session:
        tx = await session.get(Transaction, tx_id)
        assert await repo.confirm_transaction_and_add_credits(session, tx.external_id) is None
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 0
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.refunded


@pytest.mark.asyncio
async def test_stale_first_topup_callback_cannot_award_after_refund(payment_db, monkeypatch):
    from db.referral_reward_policy import award_referral_first_topup
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    monkeypatch.setattr(main.settings, "REFERRAL_FREEZE", False)
    monkeypatch.setattr(main.settings, "REFERRAL_L1_CREDITS", 3)
    async with factory() as session:
        stale_tx = await session.get(Transaction, tx_id)
        assert (await post_refund("tbank")).status_code == 200
        assert await award_referral_first_topup(session, stale_tx) is False
    async with factory() as session:
        bonus = list((await session.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.entry_type == "referral_first_topup_bonus"))).all())
        assert bonus == []


@pytest.mark.asyncio
async def test_corrupt_credit_refund_snapshot_never_adds_wallet_credits(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    async with factory() as session:
        tx = await session.get(Transaction, tx_id)
        tx.refunded_credits = 100
        await session.commit()
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 503
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("invoice", [{"eventType": "payment.success"}, {"data": {"event_type": "invoice.paid"}}])
async def test_review_lava_event_only_invoice_is_reconciled_atomically(payment_db, monkeypatch, invoice):
    from unittest.mock import AsyncMock

    from bot.handlers import payment
    factory, _ = payment_db
    tx_id, payer_id, _ = await seed_payment(factory, PaymentProvider.lava, status=TransactionStatus.pending, balance=0)
    monkeypatch.setattr(payment.lava, "get_invoice", AsyncMock(return_value=invoice))
    monkeypatch.setattr(main.settings, "REFERRAL_L1_CREDITS", 0)
    async with factory() as session:
        status, _ = await payment._reconcile_transaction_status(session, await session.get(Transaction, tx_id))
        assert status == TransactionStatus.paid
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 50
        entries = (await session.scalars(select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == payer_id))).all()
        assert len(entries) == 1 and entries[0].delta == 50


@pytest.mark.asyncio
async def test_review_legacy_failed_but_credited_partial_refund_is_settled(payment_db):
    factory, _ = payment_db
    tx_id, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    async with factory() as session:
        tx = await session.get(Transaction, tx_id)
        tx.status = TransactionStatus.failed
        await session.commit()
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 200
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 25
        assert (await session.get(User, parent_id)).referral_balance == 7.5
        assert (await session.get(Transaction, tx_id)).status == TransactionStatus.paid
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 200
    async with factory() as session:
        assert (await session.get(User, payer_id)).credits == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,title", [("ru", "Частичный возврат"), ("en", "Partial refund")])
async def test_review_partial_refund_status_message_never_claims_full_credit(payment_db, monkeypatch, lang, title):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from bot.handlers import payment
    factory, _ = payment_db
    _, payer_id, _ = await seed_payment(factory, PaymentProvider.tbank)
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value={"Status": "PARTIAL_REFUNDED", "Amount": 25000}))
    call = SimpleNamespace(data="pay:check:test-payment-1", answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock()))
    async with factory() as session:
        user = await session.get(User, payer_id)
        user.language = lang
        await session.commit()
        await payment.cb_check_payment_status(call, session, user)
    message = call.message.edit_text.await_args.args[0]
    assert title in message and "25" in message
    assert "+50" not in message and "Зачислено:" not in message and "Added:" not in message


@pytest.mark.asyncio
async def test_review_net_revenue_is_shared_by_bot_web_miniapp_and_referrals(payment_db, monkeypatch):
    from api import miniapp_routes
    from api.web import admin as web_admin
    from db import repository as repo
    factory, engine = payment_db
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    _, payer_id, parent_id = await seed_payment(factory, PaymentProvider.tbank)
    assert (await post_refund("tbank", status="PARTIAL_REFUNDED", amount=25000)).status_code == 200
    monkeypatch.setattr(main.settings, "ADMIN_IDS", [999001])
    async with factory() as session:
        session.add(Transaction(user_id=payer_id, amount_rub=9000, credits=900, provider=PaymentProvider.lava,
            external_id="pending-report-fixture", status=TransactionStatus.pending))
        await session.commit()
        assert await repo.get_revenue_today(session) == 250
        children = await repo.get_referral_children(session, parent_id)
        assert children[0].paid_rub == 250
        web = await web_admin._admin_overview_payload(session)
        assert web["totals"]["revenue_total"] == 250
        assert web["periods"]["revenue_today"] == 250
        assert sum(row["value"] for row in web["series"]["revenue_14d"]) == 250
        mini = await miniapp_routes.admin_overview(days=14, user=await session.get(User, payer_id), session=session)
        assert mini["summary"]["revenue_total"] == 250
        assert sum(row["revenue"] for row in mini["providers"]) == 250

"""Run actual refund/catalog Alembic revisions against disposable PostgreSQL."""
from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def exercise(conn):
    conn.execute(text("CREATE TABLE transactions (id integer PRIMARY KEY, status varchar(16), credits double precision, amount_rub double precision)"))
    conn.execute(text("CREATE TABLE referral_commission_ledger (id integer PRIMARY KEY, transaction_id integer, recipient_user_id integer, level integer, event_type varchar(16), amount_rub double precision, CONSTRAINT uq_referral_commission_tx_recipient_level_event UNIQUE(transaction_id,recipient_user_id,level,event_type))"))
    conn.execute(text("CREATE TABLE price_plans (key varchar(64) PRIMARY KEY, credits double precision, price_rub double precision, is_active boolean)"))
    conn.execute(text("INSERT INTO transactions VALUES (1,'paid',12.5,249.50)"))
    conn.execute(text("INSERT INTO referral_commission_ledger VALUES (1,1,2,1,'accrual',74.85)"))
    conn.execute(text("INSERT INTO price_plans VALUES ('credits_15',17.5,175,true), ('credits_25',25,250,false)"))
    refund = importlib.import_module("db.migrations.versions.045_atomic_payment_refunds")
    catalog = importlib.import_module("db.migrations.versions.046_tribute_catalog")
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        refund.upgrade()
        catalog.upgrade()
    assert conn.execute(text("SELECT status,credits,amount_rub,refunded_amount_minor,refunded_credits FROM transactions")).one() == ('paid',12.5,249.50,0,0)
    assert conn.execute(text("SELECT amount_rub,refund_key FROM referral_commission_ledger")).one() == (74.85,'')
    offers = conn.execute(text("SELECT product_id,credits,amount_rub,amount_minor,enabled FROM tribute_products ORDER BY product_id")).all()
    assert offers == [(152362,17.5,175,200,True),(152363,25,250,300,False)]
    assert conn.execute(text("SELECT count(*) FROM tribute_product_audit WHERE source='migration' AND admin_tg_id IS NULL")).scalar() == 2
    with conn.begin_nested() as tx:
        conn.execute(text("UPDATE tribute_product_audit SET source='web',admin_tg_id=999"))
        with Operations.context(context), pytest.raises(RuntimeError, match="roll forward"):
            catalog.downgrade()
        tx.rollback()
    with Operations.context(context):
        catalog.downgrade()
    with conn.begin_nested() as tx:
        conn.execute(text("INSERT INTO payment_refund_notices(external_id,provider) VALUES('early-test','tbank')"))
        with Operations.context(context), pytest.raises(RuntimeError, match="roll forward"):
            refund.downgrade()
        tx.rollback()
    with conn.begin_nested() as tx:
        conn.execute(text("INSERT INTO payment_refund_events(transaction_id,cumulative_amount_minor,amount_minor,currency,credits_delta) VALUES(1,10,10,'rub',-0.1)"))
        with Operations.context(context), pytest.raises(RuntimeError, match="roll forward"):
            refund.downgrade()
        tx.rollback()
    with Operations.context(context):
        refund.downgrade()
    assert 'refunded_amount_minor' not in {c['name'] for c in inspect(conn).get_columns('transactions')}
    assert conn.execute(text("SELECT status,credits,amount_rub FROM transactions")).one() == ('paid',12.5,249.50)
    with Operations.context(context):
        refund.upgrade()
        catalog.upgrade()
    assert conn.execute(text("SELECT credits FROM tribute_products WHERE product_id=152362")).scalar() == 17.5


@pytest.mark.asyncio
async def test_payment_catalog_upgrade_downgrade_preserves_values_and_audit():
    raw = os.getenv('APIX_TEST_POSTGRES_URL')
    if not raw:
        pytest.skip('Disposable PostgreSQL required; configured in backend CI')
    url = make_url(raw)
    if url.host not in {'localhost','127.0.0.1','::1'} or url.database != 'apix_session_migration_test':
        pytest.fail('Use only the dedicated loopback test database')
    engine = create_async_engine(url)
    schema = 'audit_migration_' + uuid4().hex
    try:
        async with engine.connect() as connection:
            tx = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(exercise)
            finally:
                await tx.rollback()
    finally:
        await engine.dispose()

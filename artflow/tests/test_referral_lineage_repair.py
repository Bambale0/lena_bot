from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from db.models import (
    ReferralCreditRepairRow,
    ReferralFinanceRepairRow,
    ReferralLineageRepairBatch,
    ReferralLineageRepairRow,
)
from scripts.repair_referral_lineage import (
    allocate_credit_corrections,
    build_finance_plan,
    build_lineage_plan,
    find_invalid_credit_bonuses,
)


def _user(user_id: int, created_at: datetime, refs=(None, None, None)):
    return SimpleNamespace(
        id=user_id,
        created_at=created_at,
        referrer_id=refs[0],
        referrer_l2_id=refs[1],
        referrer_l3_id=refs[2],
    )


def test_referral_lineage_migration_is_current_head() -> None:
    config = Config()
    config.set_main_option("script_location", "db/migrations")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["055_referral_credit"]
    assert scripts.get_revision("055_referral_credit").down_revision == "054_referral_lineage"

    source = Path("db/migrations/versions/054_referral_lineage_immutability.py").read_text(
        encoding="utf-8"
    )
    assert "trg_users_referral_lineage_immutable" in source
    assert "referral repair evidence is append-only" in source
    assert "referral repair batch evidence is immutable" in source
    credit_source = Path(
        "db/migrations/versions/055_referral_credit_repair_audit.py"
    ).read_text(encoding="utf-8")
    assert "trg_referral_credit_repair_rows_append_only" in credit_source
    assert "enforce_referral_repair_row_insert" in credit_source
    assert "sum(r.unrecovered_credits)" in credit_source

    assert ReferralLineageRepairBatch.__table__.c.batch_key.type.length == 64
    assert ReferralLineageRepairRow.__table__.c.user_id.nullable is False
    assert ReferralFinanceRepairRow.__table__.c.reversal_ledger_id.nullable is False
    assert ReferralCreditRepairRow.__table__.c.reversal_ledger_id.nullable is False
    assert {
        constraint.name for constraint in ReferralCreditRepairRow.__table__.constraints
    } >= {
        "ck_referral_credit_repair_positive_amount",
        "ck_referral_credit_repair_nonnegative_allocation",
        "ck_referral_credit_repair_allocation_total",
    }

    repair_source = Path("scripts/repair_referral_lineage.py").read_text(encoding="utf-8")
    assert "LOCK TABLE transactions, users, credit_ledger" in repair_source
    assert "referral_commission_ledger IN EXCLUSIVE MODE" in repair_source


def test_lineage_plan_repairs_only_impossible_edge_and_its_propagation() -> None:
    now = datetime.now(timezone.utc)
    users = [
        _user(1, now - timedelta(days=30), (4, None, None)),
        _user(2, now - timedelta(days=20), (1, 4, None)),
        _user(3, now - timedelta(days=10), (2, 1, 4)),
        _user(4, now - timedelta(days=5)),
        _user(5, now - timedelta(days=1), (4, None, None)),
        # Unrelated legacy gap is deliberately outside the repair scope.
        _user(6, now - timedelta(days=1), (5, None, None)),
    ]

    invalid_edges, changes = build_lineage_plan(users)

    assert [(edge.user_id, edge.invalid_referrer_id) for edge in invalid_edges] == [(1, 4)]
    assert [(change.user_id, change.old_refs, change.new_refs) for change in changes] == [
        (1, (4, None, None), (None, None, None)),
        (2, (1, 4, None), (1, None, None)),
        (3, (2, 1, 4), (2, 1, None)),
    ]


def test_finance_plan_reverses_only_commission_at_removed_level() -> None:
    lineage_changes = [
        SimpleNamespace(user_id=1, old_refs=(4, None, None), new_refs=(None, None, None)),
        SimpleNamespace(user_id=2, old_refs=(1, 4, None), new_refs=(1, None, None)),
    ]
    ledger = [
        SimpleNamespace(
            transaction_id=10,
            payer_user_id=1,
            recipient_user_id=4,
            level=1,
            rate=0.10,
            payment_amount_rub=1000.0,
            amount_rub=100.0,
        ),
        SimpleNamespace(
            transaction_id=10,
            payer_user_id=1,
            recipient_user_id=4,
            level=1,
            rate=0.10,
            payment_amount_rub=1000.0,
            amount_rub=-20.0,
        ),
        SimpleNamespace(
            transaction_id=11,
            payer_user_id=2,
            recipient_user_id=1,
            level=1,
            rate=0.10,
            payment_amount_rub=500.0,
            amount_rub=50.0,
        ),
        SimpleNamespace(
            transaction_id=11,
            payer_user_id=2,
            recipient_user_id=4,
            level=2,
            rate=0.05,
            payment_amount_rub=500.0,
            amount_rub=25.0,
        ),
    ]

    corrections = build_finance_plan(lineage_changes, ledger)

    assert [
        (
            item.transaction_id,
            item.payer_user_id,
            item.recipient_user_id,
            item.level,
            item.amount_rub,
        )
        for item in corrections
    ] == [
        (10, 1, 4, 1, 80.0),
        (11, 2, 4, 2, 25.0),
    ]


def test_finance_plan_fails_closed_for_non_null_recipient_transfer() -> None:
    lineage_changes = [
        SimpleNamespace(user_id=1, old_refs=(4, None, None), new_refs=(5, None, None))
    ]

    with pytest.raises(RuntimeError, match="cannot transfer commission"):
        build_finance_plan(lineage_changes, [])


def test_invalid_late_bind_credit_bonus_is_selected_for_audited_reversal() -> None:
    users = [
        SimpleNamespace(id=1, tg_id=111),
        SimpleNamespace(id=4, tg_id=444),
    ]
    invalid_edges = [SimpleNamespace(user_id=1, invalid_referrer_id=4)]
    entries = [
        SimpleNamespace(
            id=7,
            user_id=4,
            delta=3.0,
            entry_type="referral_first_topup_bonus",
            source_id="1",
        ),
        SimpleNamespace(
            id=8,
            user_id=4,
            delta=3.0,
            entry_type="referral_signup_bonus",
            source_id="111",
        ),
        SimpleNamespace(
            id=9,
            user_id=4,
            delta=3.0,
            entry_type="referral_first_topup_bonus",
            source_id="999",
        ),
    ]

    assert [
        entry.id for entry in find_invalid_credit_bonuses(invalid_edges, users, entries)
    ] == [7, 8]


def test_credit_reversal_debits_available_balance_and_records_spent_remainder() -> None:
    entries = [
        SimpleNamespace(id=7, user_id=4, delta=5.0),
        SimpleNamespace(id=8, user_id=4, delta=5.0),
        SimpleNamespace(id=9, user_id=5, delta=3.0),
    ]

    allocations = allocate_credit_corrections(entries, {4: 3.0, 5: 10.0})

    assert [
        (
            item.original_ledger_id,
            item.balance_debit_credits,
            item.unrecovered_credits,
            item.balance_after_credits,
        )
        for item in allocations
    ] == [
        (7, 3.0, 2.0, 0.0),
        (8, 0.0, 5.0, 0.0),
        (9, 3.0, 0.0, 7.0),
    ]


def _expect_db_error(connection, statement: str) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(sa.exc.DBAPIError):
            connection.execute(sa.text(statement))
    finally:
        savepoint.rollback()


def _exercise_postgres_triggers(connection) -> None:
    connection.execute(
        sa.text(
            "CREATE TABLE users ("
            "id integer PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), "
            "referrer_id integer, referrer_l2_id integer, referrer_l3_id integer, "
            "referral_balance double precision NOT NULL DEFAULT 0, "
            "credits double precision NOT NULL DEFAULT 0)"
        )
    )
    connection.execute(
        sa.text("CREATE TABLE transactions (id integer PRIMARY KEY, user_id integer NOT NULL)")
    )
    connection.execute(sa.text("CREATE TABLE referral_commission_ledger (id integer PRIMARY KEY)"))
    connection.execute(
        sa.text(
            "CREATE TABLE credit_ledger ("
            "id integer PRIMARY KEY, user_id integer NOT NULL REFERENCES users(id), "
            "delta double precision NOT NULL, balance_after double precision NOT NULL, "
            "entry_type varchar(64) NOT NULL, source_type varchar(64), source_id varchar(128))"
        )
    )
    migration = importlib.import_module("db.migrations.versions.054_referral_lineage_immutability")
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    credit_migration = importlib.import_module(
        "db.migrations.versions.055_referral_credit_repair_audit"
    )
    with Operations.context(MigrationContext.configure(connection)):
        credit_migration.upgrade()

    connection.execute(
        sa.text(
            "INSERT INTO users (id,created_at,referrer_id) VALUES "
            "(2, now(), NULL), (1, now() - interval '1 day', 2)"
        )
    )
    _expect_db_error(connection, "UPDATE users SET referrer_id=NULL WHERE id=1")

    connection.execute(
        sa.text(
            "INSERT INTO referral_lineage_repair_batches "
            "(batch_key,operator,reason,status,invalid_credit_credits) "
            "VALUES ('trigger-test','pytest','test','applying',5)"
        )
    )
    connection.execute(
        sa.text("SELECT set_config('apix.referral_repair_batch','trigger-test',true)")
    )
    _expect_db_error(connection, "UPDATE users SET referrer_id=NULL WHERE id=1")
    connection.execute(
        sa.text(
            "INSERT INTO referral_lineage_repair_rows "
            "(batch_key,user_id,old_referrer_id,new_referrer_id,reason) "
            "VALUES ('trigger-test',1,2,NULL,'impossible_direct_referrer')"
        )
    )
    connection.execute(sa.text("UPDATE users SET referrer_id=NULL WHERE id=1"))

    _expect_db_error(
        connection,
        "UPDATE referral_lineage_repair_rows SET reason='changed' WHERE user_id=1",
    )
    _expect_db_error(
        connection,
        "DELETE FROM referral_lineage_repair_rows WHERE user_id=1",
    )
    connection.execute(sa.text("INSERT INTO transactions (id,user_id) VALUES (10,1)"))
    connection.execute(sa.text("INSERT INTO referral_commission_ledger (id) VALUES (20)"))
    connection.execute(
        sa.text(
            "INSERT INTO referral_finance_repair_rows "
            "(batch_key,transaction_id,payer_user_id,recipient_user_id,level,amount_rub,"
            "balance_debit_rub,unrecovered_rub,reversal_ledger_id) "
            "VALUES ('trigger-test',10,1,2,1,10,10,0,20)"
        )
    )
    _expect_db_error(
        connection,
        "UPDATE referral_finance_repair_rows SET amount_rub=9 WHERE id=1",
    )
    _expect_db_error(
        connection,
        "DELETE FROM referral_finance_repair_rows WHERE id=1",
    )
    connection.execute(
        sa.text(
            "INSERT INTO credit_ledger "
            "(id,user_id,delta,balance_after,entry_type,source_type,source_id) VALUES "
            "(30,2,5,8,'referral_signup_bonus','user','1'),"
            "(31,2,-3,5,'referral_bonus_reversal','referral_lineage_repair',"
            "'trigger-test:30')"
        )
    )
    connection.execute(sa.text("UPDATE users SET credits=5 WHERE id=2"))
    connection.execute(
        sa.text(
            "INSERT INTO referral_credit_repair_rows "
            "(batch_key,original_ledger_id,user_id,entry_type,amount_credits,"
            "balance_debit_credits,unrecovered_credits,reversal_ledger_id) "
            "VALUES ('trigger-test',30,2,'referral_signup_bonus',5,3,2,31)"
        )
    )
    _expect_db_error(
        connection,
        "UPDATE referral_credit_repair_rows SET amount_credits=4 WHERE id=1",
    )
    _expect_db_error(connection, "DELETE FROM referral_credit_repair_rows WHERE id=1")
    connection.execute(
        sa.text(
            "INSERT INTO credit_ledger "
            "(id,user_id,delta,balance_after,entry_type,source_type,source_id) VALUES "
            "(32,2,1,5,'referral_signup_bonus','user','1'),"
            "(33,2,-1,4,'referral_bonus_reversal','referral_lineage_repair',"
            "'trigger-test:32')"
        )
    )
    _expect_db_error(
        connection,
        "INSERT INTO referral_credit_repair_rows "
        "(batch_key,original_ledger_id,user_id,entry_type,amount_credits,"
        "balance_debit_credits,unrecovered_credits,reversal_ledger_id) "
        "VALUES ('trigger-test',32,2,'referral_signup_bonus',1,-1,2,33)",
    )
    connection.execute(sa.text("UPDATE credit_ledger SET balance_after=1000 WHERE id=31"))
    _expect_db_error(
        connection,
        "UPDATE referral_lineage_repair_batches SET status='applied', "
        "balance_debit_credits=3, unrecovered_credits=2, "
        "summary_json='{}', applied_at=now() WHERE batch_key='trigger-test'",
    )
    connection.execute(sa.text("UPDATE credit_ledger SET balance_after=5 WHERE id=31"))
    connection.execute(
        sa.text(
            "UPDATE referral_lineage_repair_batches SET status='applied', "
            "balance_debit_credits=3, unrecovered_credits=2, "
            "summary_json='{}', applied_at=now() WHERE batch_key='trigger-test'"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO credit_ledger "
            "(id,user_id,delta,balance_after,entry_type,source_type,source_id) VALUES "
            "(34,2,1,4,'referral_signup_bonus','user','1'),"
            "(35,2,-1,3,'referral_bonus_reversal','referral_lineage_repair',"
            "'trigger-test:34')"
        )
    )
    _expect_db_error(
        connection,
        "INSERT INTO referral_credit_repair_rows "
        "(batch_key,original_ledger_id,user_id,entry_type,amount_credits,"
        "balance_debit_credits,unrecovered_credits,reversal_ledger_id) "
        "VALUES ('trigger-test',34,2,'referral_signup_bonus',1,1,0,35)",
    )
    _expect_db_error(connection, "UPDATE credit_ledger SET delta=0 WHERE id=31")
    _expect_db_error(
        connection,
        "UPDATE referral_lineage_repair_batches SET reason='changed' "
        "WHERE batch_key='trigger-test'",
    )
    _expect_db_error(connection, "UPDATE users SET referrer_id=2 WHERE id=1")


@pytest.mark.asyncio
async def test_referral_lineage_triggers_enforce_postgres_contract() -> None:
    raw_url = os.getenv("APIX_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Dedicated loopback PostgreSQL test service is not configured")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "apix_session_migration_test"
        or url.query
    ):
        pytest.fail("APIX_TEST_POSTGRES_URL must target the dedicated loopback test database")
    engine = create_async_engine(url)
    schema = f"referral_lineage_test_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(_exercise_postgres_triggers)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

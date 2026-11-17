"""Read-only payment integrity reporting without external provider calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.report_payment_integrity import (
    INTEGRITY_FIELDS,
    ORPHAN_PAYMENT_LEDGER_SQL,
    PROVIDER_REPORT_SQL,
    collect_payment_integrity,
    make_report,
)


def provider_row(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "provider": "tbank",
        "transactions": 5,
        "paid": 3,
        "pending": 2,
        "failed": 0,
        "paid_without_ledger": 0,
        "paid_duplicate_ledger": 0,
        "paid_credit_mismatch": 0,
        "ledger_owner_mismatch": 0,
        "nonpaid_with_payment_ledger": 0,
        "pending_last_24h": 1,
        "pending_older_7d": 1,
        "pending_older_30d": 1,
        "pending_older_90d": 0,
        "pending_missing_external_id": 0,
    }
    result.update(overrides)
    return result


def test_healthy_report_counts_only_aggregates() -> None:
    data = make_report([
        provider_row(user_id=987654321, external_id="secret-payment-reference"),
        provider_row(provider="lava", transactions=2, paid=2, pending=0,
                     pending_last_24h=0, pending_older_7d=0),
    ], orphan_count=0)
    assert data["integrity_ok"] is True
    assert data["summary"]["paid"] == 5
    assert data["summary"]["pending"] == 2
    assert data["summary"]["failed"] == 0
    assert data["summary"]["pending_last_24h"] == 1
    assert data["summary"]["pending_older_30d"] == 1
    assert data["summary"]["pending_missing_external_id"] == 0
    assert data["summary"]["paid_without_ledger"] == 0
    as_json = json.dumps(data)
    assert "secret-payment-reference" not in as_json
    assert "987654321" not in as_json
    assert "created_utc" not in as_json


@pytest.mark.parametrize("field", INTEGRITY_FIELDS)
def test_any_ledger_violation_marks_report_unhealthy(field: str) -> None:
    result = make_report([provider_row(**{field: 1})], 0)
    assert result["integrity_ok"] is False
    assert result["summary"][field] == 1


def test_orphan_payment_credit_is_reported() -> None:
    result = make_report([provider_row()], orphan_count=2)
    assert result["integrity_ok"] is False
    assert result["summary"]["orphan_payment_ledger"] == 2


def test_pending_age_never_causes_financial_integrity_failure() -> None:
    result = make_report([
        provider_row(pending_older_7d=1800, pending_older_30d=850, pending_older_90d=300)
    ], 0)
    assert result["integrity_ok"] is True
    assert result["summary"]["pending_older_7d"] == 1800
    assert result["summary"]["pending_older_30d"] == 850
    assert result["summary"]["pending_older_90d"] == 300
    assert "not necessarily paid externally" in result["interpretation"]


def test_aggregate_summary_sums_pending_aging_and_missing_ids_without_leaking_identity() -> None:
    report = make_report([
        provider_row(provider="tbank", pending_last_24h=1, pending_older_7d=1,
                     pending_older_30d=1, pending_older_90d=0,
                     pending_missing_external_id=1, external_id="private-tbank-id"),
        provider_row(provider="cryptobot", pending_last_24h=2, pending_older_7d=4,
                     pending_older_30d=3, pending_older_90d=2,
                     pending_missing_external_id=0, external_id="private-crypto-id"),
    ], 0)
    assert report["summary"]["pending_last_24h"] == 3
    assert report["summary"]["pending_older_7d"] == 5
    assert report["summary"]["pending_older_30d"] == 4
    assert report["summary"]["pending_older_90d"] == 2
    assert report["summary"]["pending_missing_external_id"] == 1
    assert report["integrity_ok"] is True
    serialized = json.dumps(report)
    assert "private-tbank-id" not in serialized
    assert "private-crypto-id" not in serialized


def test_sql_uses_30_day_pending_age_filter_without_provider_calls() -> None:
    assert "created_at < now() - interval '30 days'" in PROVIDER_REPORT_SQL
    assert "AS pending_older_30d" in PROVIDER_REPORT_SQL


class FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None, scalar: int | None = None):
        self.rows = rows
        self.scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.scalar


class FakeSession:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, sql):
        statement = str(sql)
        self.statements.append(statement)
        if statement == PROVIDER_REPORT_SQL:
            return FakeResult(rows=[provider_row()])
        if statement == ORPHAN_PAYMENT_LEDGER_SQL:
            return FakeResult(scalar=0)
        return FakeResult()


@pytest.mark.asyncio
async def test_consistent_read_only_transaction_before_any_select() -> None:
    session = FakeSession()
    result = await collect_payment_integrity(session)
    assert result["integrity_ok"] is True
    assert len(session.statements) == 4
    assert session.statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    assert session.statements[1] == "SET LOCAL statement_timeout = '15000ms'"
    assert session.statements[2] == PROVIDER_REPORT_SQL
    assert session.statements[3] == ORPHAN_PAYMENT_LEDGER_SQL
    assert all(s.lstrip().startswith(("SET", "WITH", "SELECT")) for s in session.statements)


def test_report_source_has_no_payment_provider_or_write_paths() -> None:
    script = (Path(__file__).parents[1] / "scripts/report_payment_integrity.py").read_text()
    assert "from payments." not in script
    assert "confirm_transaction_and_add_credits" not in script
    assert "set_transaction_status" not in script
    assert "session.add(" not in script
    assert "session.commit(" not in script
    assert "session.rollback()" in script

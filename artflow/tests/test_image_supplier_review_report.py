"""Read-only supplier review report: identifiers never leave the DB."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.report_image_supplier_reviews import (
    REVIEW_SQL,
    collect_supplier_reviews,
    make_report,
)


def sample_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "model": "nano-banana-2.1",
        "provider": "neironych",
        "review_state": "pending",
        "task_identity_kind": "neironych_request_id",
        "review_count": 28,
        "older_7d": 24,
        "older_30d": 17,
    }
    row.update(overrides)
    return row


def test_aggregates_separate_unpollable_pending_reviews() -> None:
    report = make_report([
        sample_row(provider_task_id="private-provider-id", user_id=123456789),
        sample_row(
            model="nano-banana-pro",
            task_identity_kind="missing",
            review_count=3,
            older_7d=3,
            older_30d=0,
            prompt="private-image-prompt",
        ),
        sample_row(
            model="seedream/5-pro-text-to-image",
            review_state="remote_failed",
            review_count=25,
            older_7d=17,
            older_30d=5,
        ),
    ])
    summary = report["summary"]
    assert summary["review_count"] == 56
    assert summary["pending"] == 31
    assert summary["pending_missing_task_identity"] == 3
    assert summary["pending_not_covered_by_neironych_task_poller"] == 3
    assert summary["pending_older_7d"] == 27
    assert summary["pending_older_30d"] == 17
    assert summary["remote_failed"] == 25
    serialized = json.dumps(report)
    assert "private-provider-id" not in serialized
    assert "private-image-prompt" not in serialized
    assert "123456789" not in serialized




def test_nexus_missing_identity_is_not_misclassified_as_neironych() -> None:
    data = make_report([
        sample_row(
            provider="nexus",
            model="nano-banana-pro",
            task_identity_kind="missing",
            review_count=3,
            older_7d=3,
            older_30d=0,
        ),
    ])
    assert data["summary"]["pending_missing_task_identity"] == 3
    assert data["summary"]["pending_not_covered_by_neironych_task_poller"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "personal@example.com"),
        ("model", "image/../../secret"),
        ("review_state", "customer-private-value"),
        ("task_identity_kind", "private-reference-id"),
    ],
)
def test_unknown_labels_are_redacted(field: str, value: str) -> None:
    report = make_report([sample_row(**{field: value})])
    assert value not in json.dumps(report)


@pytest.mark.parametrize(
    ("count", "older7", "older30"),
    [(2, 3, 0), (2, 2, 3), (-1, 0, 0)],
)
def test_invalid_age_aggregates_fail_closed(
    count: int, older7: int, older30: int
) -> None:
    with pytest.raises(ValueError):
        make_report([
            sample_row(review_count=count, older_7d=older7, older_30d=older30)
        ])


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [sample_row()]


class FakeSession:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, sql):
        self.statements.append(str(sql))
        return FakeResult()


@pytest.mark.asyncio
async def test_read_only_transaction_precedes_query() -> None:
    session = FakeSession()
    report = await collect_supplier_reviews(session)
    assert report["summary"]["pending"] == 28
    assert session.statements == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "SET LOCAL statement_timeout = '15000ms'",
        REVIEW_SQL,
    ]
    assert all(x.lstrip().startswith(("SET", "WITH")) for x in session.statements)


def test_script_does_not_contain_provider_calls_or_financial_writes() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts/report_image_supplier_reviews.py"
    ).read_text(encoding="utf-8")
    assert "session.commit(" not in source
    assert "session.add(" not in source
    assert "fail_generation_and_refund" not in source
    assert "record_late_image_provider_outcome" not in source
    assert "httpx." not in source
    assert "await session.rollback()" in source

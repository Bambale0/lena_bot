"""Exercise the real PostgreSQL regex dialect used by admission, not Python re."""
from __future__ import annotations

import os

import asyncpg
import pytest

from api import miniapp_routes  # noqa: F401 - legacy application import order
from core import seedance_reconciliation as circuit
from db import session as db_session

CASES = [
    ('{"neironych_video_reconciliation":{"required":true}}', True),
    ('{"neironych_video_reconciliation": {"required": true, "reason": "unknown"}}', True),
    ('{"neironych_video_reconciliation": {"required": true  }}', True),
    ('{"neironych_video_reconciliation":{"required":false}}', False),
    ('{"neironych_video_reconciliation":{"required":"true"}}', False),
    ('{"neironych_video_reconciliation":{"required":truex}}', False),
    ('{"neironych_video_reconciliation":{"required":true123}}', False),
    ('{"unrelated":{"required":true}}', False),
    ('{}', False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", CASES)
async def test_admission_marker_uses_postgresql_regex_semantics(monkeypatch, raw, expected):
    dsn = os.environ.get("TEST_RECONCILIATION_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Requires ephemeral PostgreSQL; mandatory in backend-quality CI")
    connection = await asyncpg.connect(dsn, timeout=5)

    class PredicateSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def scalar(self, statement):
            # Capture the actual production predicate. Only table access is
            # replaced; PostgreSQL evaluates the same bound regex via SELECT.
            predicates = [
                value for value in statement.compile().params.values()
                if isinstance(value, str) and "neironych_video_reconciliation" in value
            ]
            assert len(predicates) == 1
            return await connection.fetchval(
                "SELECT $1::text ~ $2::text", raw, predicates[0], timeout=5,
            )

    monkeypatch.setattr(db_session, "AsyncSessionLocal", PredicateSession)
    try:
        assert await circuit._db_has_unresolved_seedance("bytedance/seedance-2-5") is expected
    finally:
        await connection.close()

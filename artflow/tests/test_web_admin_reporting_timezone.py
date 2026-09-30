from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from api.web import admin as web_admin
from db.models import Transaction


class _Rows:
    def all(self):
        return []


@pytest.mark.asyncio
async def test_daily_series_groups_and_bounds_by_moscow_day(monkeypatch) -> None:
    start = datetime(2026, 9, 29, 21, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        web_admin,
        "moscow_day_bounds_utc",
        lambda _now: (datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc), end),
    )
    session = AsyncMock()
    session.execute.return_value = _Rows()

    await web_admin._daily_series(
        session,
        Transaction.created_at,
        Transaction,
        days=2,
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement).lower()
    params = statement.compile().params

    assert "timezone" in sql
    assert "created_at >=" in sql
    assert "created_at <" in sql
    assert start in params.values()
    assert end in params.values()

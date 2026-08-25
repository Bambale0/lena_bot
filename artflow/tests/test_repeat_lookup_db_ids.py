from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db.repeat_lookup import get_repeat_task_by_any_id


class FakeResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_namespaced_database_id_resolves_before_provider_task_lookup() -> None:
    expected = SimpleNamespace(id=42, task_id="provider-for-42")
    session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult(expected)))

    result = await get_repeat_task_by_any_id(session, "db_42")

    assert result is expected
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_namespaced_database_id_does_not_fall_through_to_provider_collision() -> None:
    session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult(None)))

    result = await get_repeat_task_by_any_id(session, "db_42")

    assert result is None
    session.execute.assert_awaited_once()

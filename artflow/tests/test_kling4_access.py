from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.config import settings
from core.kling4_access import kling4_visible, require_kling4_access, set_kling4_access


@pytest.mark.asyncio
async def test_missing_policy_is_admin_only(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    session = SimpleNamespace(get=AsyncMock(return_value=None))
    assert not await kling4_visible(session, None)
    assert not await kling4_visible(session, SimpleNamespace(tg_id=555))
    assert await kling4_visible(session, SimpleNamespace(tg_id=123))
    with pytest.raises(HTTPException) as error:
        await require_kling4_access(session, SimpleNamespace(tg_id=555))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_public_and_disabled_policies(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(audience="public")))
    assert await kling4_visible(session, SimpleNamespace(tg_id=555))
    session.get.return_value.audience = "disabled"
    assert not await kling4_visible(session, SimpleNamespace(tg_id=123))


@pytest.mark.asyncio
async def test_policy_mutation_enforces_admin_before_db(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    with pytest.raises(HTTPException):
        await set_kling4_access(SimpleNamespace(), "public", admin_tg_id=555, source="bot")


@pytest.mark.asyncio
async def test_policy_mutation_accepts_trusted_ops_source(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])
    policy = SimpleNamespace(audience="admin", updated_by_admin_tg_id=123)
    scalars = SimpleNamespace(scalar_one=lambda: policy)
    added = []
    session = SimpleNamespace(
        execute=AsyncMock(return_value=scalars),
        add=added.append,
        commit=AsyncMock(),
    )

    assert await set_kling4_access(
        session,
        "public",
        source="ops",
        operator_identity="root@release-container",
    ) == "public"
    assert policy.audience == "public"
    assert policy.updated_by_admin_tg_id is None
    assert len(added) == 1
    assert added[0].previous_audience == "admin"
    assert added[0].new_audience == "public"
    assert added[0].changed_by_admin_tg_id is None
    assert added[0].changed_by_operator == "root@release-container"
    assert added[0].source == "ops"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_mutation_rejects_unknown_source_before_db(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])

    with pytest.raises(ValueError):
        await set_kling4_access(
            SimpleNamespace(),
            "public",
            source="manual-sql",
        )


@pytest.mark.asyncio
async def test_ops_source_rejects_telegram_admin_attribution(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", [123])

    with pytest.raises(ValueError, match="ops identity"):
        await set_kling4_access(
            SimpleNamespace(),
            "public",
            admin_tg_id=123,
            source="ops",
            operator_identity="root@release-container",
        )

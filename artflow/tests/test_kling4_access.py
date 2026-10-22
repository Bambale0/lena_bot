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

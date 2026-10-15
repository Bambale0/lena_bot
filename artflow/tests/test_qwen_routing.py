from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.web import admin as web_admin
from core.qwen_routing import get_qwen_route, set_qwen_route, validate_route


class _Session:
    def __init__(self, record):
        self.record = record
        self.added = []
        self.commit = AsyncMock()

    async def get(self, _model, _mode):
        return self.record

    async def execute(self, statement):
        if getattr(statement, "is_insert", False):
            return None
        return SimpleNamespace(scalar_one=lambda: self.record)

    def add(self, item):
        self.added.append(item)


def test_video_route_rejects_unverified_neironych_media() -> None:
    with pytest.raises(ValueError, match="visual contract"):
        validate_route("video", "neironych", "kie")
    with pytest.raises(ValueError, match="visual contract"):
        validate_route("video", "kie", "neironych")


@pytest.mark.asyncio
async def test_default_routes_and_initial_override_are_audited() -> None:
    session = _Session(None)
    route = await get_qwen_route("image", session)
    assert (route.primary_provider, route.backup_provider, route.source) == ("neironych", "kie", "default")

    record = SimpleNamespace(primary_provider="neironych", backup_provider="kie", updated_by_admin_tg_id=None)
    session.record = record
    saved = await set_qwen_route(session, "image", "neironych", "kie", admin_tg_id=123, source="web")
    assert saved.source == "database"
    assert record.updated_by_admin_tg_id == 123
    assert len(session.added) == 1
    assert session.added[0].changed_by_admin_tg_id == 123
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_admin_rejects_unauthenticated_route_change(monkeypatch) -> None:
    setter = AsyncMock(side_effect=AssertionError("unauthorized write"))
    monkeypatch.setattr(web_admin, "set_qwen_route", setter)
    response = await web_admin.admin_set_qwen_route(
        "text", web_admin.QwenProviderRoutingUpdate(primary_provider="kie"),
        session=SimpleNamespace(), user=None,
    )
    assert response.status_code in {401, 403}
    setter.assert_not_awaited()

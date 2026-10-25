from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from api import llm_provider_service as llm
from api import photo_prompt_service
from api.web import admin as web_admin
from core.qwen_routing import (
    KieResponseRejected,
    check_kie_response_code,
    get_qwen_route,
    is_definitive_provider_rejection,
    set_qwen_route,
    validate_route,
)


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


def test_only_definitive_kie_rejection_allows_reverse_fallback() -> None:
    request = httpx.Request("POST", "https://kie.test/chat")
    for status, expected in ((422, True), (400, True), (429, False), (503, False)):
        response = httpx.Response(status, request=request)
        assert is_definitive_provider_rejection(httpx.HTTPStatusError("rejected", request=request, response=response)) is expected
    assert is_definitive_provider_rejection(httpx.ReadTimeout("timeout")) is False
    for code in (400, 401, 403, 404, 415, 422, "401"):
        with pytest.raises(KieResponseRejected) as caught:
            check_kie_response_code({"code": code, "msg": "private provider response"})
        assert is_definitive_provider_rejection(caught.value)
        assert "private provider response" not in str(caught.value)
    with pytest.raises(RuntimeError) as caught:
        check_kie_response_code({"code": 429, "msg": "uncertain"})
    assert not is_definitive_provider_rejection(caught.value)


def test_kie_http_200_rejection_envelope_survives_assistant_extractor() -> None:
    route = llm.LLMRoute(llm.LLMProvider.KIE_RESPONSES, "gpt-5-4")
    with pytest.raises(KieResponseRejected) as caught:
        llm._extract_responses_result({"code": 401, "msg": "private detail"}, route)
    assert caught.value.code == 401
    assert "private detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_kie_http_200_rejection_envelope_survives_photo_call(monkeypatch) -> None:
    monkeypatch.setattr(photo_prompt_service, "_post_json", AsyncMock(return_value={
        "code": 422, "msg": "private detail",
    }))
    with pytest.raises(KieResponseRejected) as caught:
        await photo_prompt_service._call_kie_chat("gpt-5-2", "data:image/png;base64,YQ==")
    assert caught.value.code == 422


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
async def test_qwen_route_accepts_trusted_ops_actor_without_telegram_impersonation() -> None:
    record = SimpleNamespace(
        primary_provider="neironych",
        backup_provider="kie",
        updated_by_admin_tg_id=123,
    )
    session = _Session(record)

    saved = await set_qwen_route(
        session,
        "image",
        "kie",
        "neironych",
        source="ops",
        operator_identity="codex-for-Bambale0-20261025",
    )

    assert (saved.primary_provider, saved.backup_provider) == ("kie", "neironych")
    assert record.updated_by_admin_tg_id is None
    assert len(session.added) == 1
    audit = session.added[0]
    assert audit.changed_by_admin_tg_id is None
    assert audit.changed_by_operator == "codex-for-Bambale0-20261025"
    assert audit.source == "ops"


@pytest.mark.asyncio
async def test_qwen_route_rejects_invalid_ops_actor_before_database_access() -> None:
    session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("database touched")))

    with pytest.raises(ValueError, match="ops identity"):
        await set_qwen_route(
            session,
            "image",
            "kie",
            "neironych",
            admin_tg_id=123,
            source="ops",
            operator_identity="root@release-container",
        )

    session.execute.assert_not_awaited()


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

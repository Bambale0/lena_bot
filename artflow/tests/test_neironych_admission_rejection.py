"""No second paid POST without a versioned receipt matching this invocation."""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest

from api.neironych_qwen38_service import NeironychQwen38Service, Qwen38ProviderError
from api.neironych_seedance import NeironychSeedanceClient, NeironychSubmissionUnknown
from api.seedance_provider_routing import submit_seedance
from core.config import settings

RID = "d3252064-e54b-4590-a56f-ae162ef7b9ec"
IDEM = "apix-video-admission-test"


def rejection(request, change=None):
    headers = {
        "X-Submission-State": "not-accepted-v1",
        "X-Client-Request-Id": request.headers["X-Client-Request-Id"],
        "X-Idempotency-Key-Sha256": hashlib.sha256(request.headers["Idempotency-Key"].encode()).hexdigest(),
    }
    if change in headers:
        headers[change] = "mismatch"
    if change == "missing_receipt":
        headers = {}
    body = {"detail": "provider_temporarily_unavailable"}
    if change == "unexpected_body":
        body = {"request_id": "accepted-task", "error": {"type": "provider_temporarily_unavailable"}}
    return httpx.Response(503, json=body, headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["seedance-2.0", "seedance-2.5"])
async def test_correlated_capital_rejection_uses_existing_fallback_once(monkeypatch, model):
    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    calls = []
    def handle(request):
        calls.append(request)
        return rejection(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="https://provider.test") as http:
        client = NeironychSeedanceClient("test-key", "https://provider.test", client=http)
        async def primary():
            return await client.create_video(model=model, payload={"prompt": "animate", "duration": 5, "resolution": "720p"},
                idempotency_key=IDEM, client_request_id=RID)
        backup = AsyncMock(return_value="kie-task")
        assert await submit_seedance("bytedance/seedance-2-5", kie=backup, neironych=primary) == "kie-task"
        assert len(calls) == 1
        assert calls[0].headers.get("X-Submission-Receipt") == "v1"
        backup.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing_receipt", "X-Submission-State", "X-Client-Request-Id", "X-Idempotency-Key-Sha256", "unexpected_body"])
async def test_incomplete_or_mismatched_receipt_never_allows_second_post(monkeypatch, change):
    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: rejection(req, change)), base_url="https://provider.test") as http:
        client = NeironychSeedanceClient("test-key", "https://provider.test", client=http)
        async def primary():
            return await client.create_video(model="seedance-2.5", payload={"prompt": "animate", "duration": 5, "resolution": "720p"},
                idempotency_key=IDEM, client_request_id=RID)
        backup = AsyncMock()
        with pytest.raises(NeironychSubmissionUnknown):
            await submit_seedance("bytedance/seedance-2-5", kie=backup, neironych=primary)
        backup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change,ambiguous", [(None, False), ("missing_receipt", True), ("X-Client-Request-Id", True), ("X-Idempotency-Key-Sha256", True), ("unexpected_body", True)])
async def test_qwen_uses_the_same_correlated_rejection_contract(change, ambiguous):
    service = NeironychQwen38Service(api_key="test-key", base_url="https://provider.test", model="qwen3.8-max",
        transport=httpx.MockTransport(lambda req: rejection(req, change)))
    with pytest.raises(Qwen38ProviderError) as error:
        await service.analyze_text(user_instruction="test")
    assert error.value.ambiguous is ambiguous
    if not ambiguous:
        assert error.value.kind == "admission_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["bytedance/seedance-2", "bytedance/seedance-2-5"])
async def test_real_product_fallback_persists_kie_intent_before_post(monkeypatch, model):
    from api import neironych_seedance_runtime, video_service
    from api.neironych_seedance_runtime import SubmissionContext

    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    events = []
    async def before_neiro(key, digest):
        events.append("neiro_intent")
    async def before_kie():
        events.append("kie_intent")
    def reject(request):
        events.append("neiro_post_rejected")
        return rejection(request)
    async def create_task(payload, callback_url=None):
        assert events == ["neiro_intent", "neiro_post_rejected", "kie_intent"]
        events.append("kie_post")
        assert payload["model"] == model
        assert payload["input"]["prompt"] == "animate original scene"
        assert str(payload["input"]["duration"]) == "5"
        return {"code": 200, "data": {"taskId": "kie-accepted"}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(reject), base_url="https://provider.test") as http:
        client = NeironychSeedanceClient("test-key", "https://provider.test", client=http)
        monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
        monkeypatch.setattr(video_service.kieai_client, "create_task", create_task)
        context = SubmissionContext(client_request_id=RID, before_submit=before_neiro, before_kie_submit=before_kie)
        result = await video_service.generate_video(video_service.VideoModel(model), "animate original scene",
            duration=5, resolution="720p", aspect_ratio="16:9", idempotency_key=IDEM, neironych_submission=context)
        assert result.provider == "kieai" and result.task_id == "kie-accepted"
        assert events == ["neiro_intent", "neiro_post_rejected", "kie_intent", "kie_post"]


from tests import test_kie_seedance_callback as kie_fixtures

LocalAsyncSession = kie_fixtures.LocalAsyncSession
kie_transaction_db = kie_fixtures.kie_transaction_db


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["miniapp", "web", "telegram"])
@pytest.mark.parametrize("model", ["bytedance/seedance-2", "bytedance/seedance-2-5"])
async def test_receipt_to_durable_kie_binding_never_recharges_or_reposts(kie_transaction_db, monkeypatch, surface, model):
    import json

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from api import neironych_seedance_runtime, video_service
    from core.seedance_reconciliation import make_submission_context, persist_submission_result
    from db import repository as repo
    from db.models import CreditLedgerEntry, Generation, User

    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    count = 0
    async def submit_kie(payload, callback_url=None):
        nonlocal count
        count += 1
        # Independent connection proves the intent committed BEFORE paid POST.
        with Session(kie_transaction_db) as observer:
            row = observer.get(Generation, 73)
            assert row.task_id == ("web:" if surface == "web" else "") + "kie-submit:73"
            saved = json.loads(row.input_params)
            assert saved["neironych_submission"]["state"] == "definite_rejected_fallback_kie"
            assert saved["kie_video_submission"]["state"] == "submitting"
        return {"code": 200, "data": {"taskId": "accepted-once"}}

    with Session(kie_transaction_db, expire_on_commit=False) as sync:
        row = sync.get(Generation, 73)
        row.task_id = None
        row.model = model
        sync.commit()
        db = LocalAsyncSession(sync)
        assert await repo.register_kie_video_callback(db, 73, surface=surface)
        context = make_submission_context(db, 73, model, surface=surface)
        async with httpx.AsyncClient(transport=httpx.MockTransport(rejection), base_url="https://provider.test") as http:
            client = NeironychSeedanceClient("test-key", "https://provider.test", client=http)
            monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
            monkeypatch.setattr(video_service.kieai_client, "create_task", submit_kie)
            async def launch():
                return await video_service.generate_video(video_service.VideoModel(model), "animate scene",
                    duration=5, resolution="720p", aspect_ratio="16:9", idempotency_key=IDEM, neironych_submission=context)
            result = await launch()
            assert await persist_submission_result(db, 73, context, result.task_id, surface=surface)
            assert row.task_id == ("web:" if surface == "web" else "") + "accepted-once"
            with pytest.raises(NeironychSubmissionUnknown):
                await launch()
        assert count == 1
        assert sync.get(User, 42).credits == 100
        assert list(sync.scalars(select(CreditLedgerEntry))) == []


@pytest.mark.asyncio
async def test_photo_prompt_receipt_uses_configured_backup_once(monkeypatch):
    import io
    from types import SimpleNamespace

    from PIL import Image

    from api import photo_prompt_service

    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, "PNG")
    service = NeironychQwen38Service(api_key="test-key", base_url="https://provider.test", model="qwen3.8-max",
        transport=httpx.MockTransport(rejection))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: service)
    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(return_value=SimpleNamespace(
        primary_provider="neironych", backup_provider="kie")))
    monkeypatch.setattr(settings, "KIE_PHOTO_PROMPT_MODEL", "gpt-5-2")
    backup = AsyncMock(return_value=photo_prompt_service.PhotoPromptResult(
        "An isolated synthetic test photo description.", "kie", "gpt-5-2"))
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", backup)
    result = await photo_prompt_service.generate_prompt_from_photo_result(image.getvalue(), "image/png")
    assert result.provider == "kie" and "synthetic" in result.text
    backup.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_intent_failure_after_receipt_refunds_once_without_any_kie_post(kie_transaction_db, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from api import neironych_seedance_runtime, video_service
    from api.neironych_seedance import NeironychPreSubmitFailure
    from core.seedance_reconciliation import handle_submission_not_sent, make_submission_context
    from db import repository as repo
    from db.models import CreditLedgerEntry, Generation, User

    monkeypatch.setattr(settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych")
    failed_journal = AsyncMock(side_effect=RuntimeError("synthetic intent storage failure"))
    kie_post = AsyncMock()
    monkeypatch.setattr(repo, "begin_kie_video_submission", failed_journal)
    monkeypatch.setattr(video_service.kieai_client, "create_task", kie_post)
    with Session(kie_transaction_db, expire_on_commit=False) as sync:
        row = sync.get(Generation, 73)
        row.task_id = None
        sync.commit()
        db = LocalAsyncSession(sync)
        assert await repo.register_kie_video_callback(db, 73, surface="telegram_bot")
        context = make_submission_context(db, 73, row.model, surface="telegram_bot")
        async with httpx.AsyncClient(transport=httpx.MockTransport(rejection), base_url="https://provider.test") as http:
            client = NeironychSeedanceClient("test-key", "https://provider.test", client=http)
            monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
            with pytest.raises(NeironychPreSubmitFailure):
                await video_service.generate_video(video_service.VideoModel(row.model), "animate scene",
                    duration=5, resolution="720p", idempotency_key=IDEM, neironych_submission=context)
        kie_post.assert_not_awaited()
        assert await handle_submission_not_sent(db, 73, context)
        assert sync.get(User, 42).credits == 140
        assert sync.get(Generation, 73).status.value == "failed"
        assert not await handle_submission_not_sent(db, 73, context)
        ledger = list(sync.scalars(select(CreditLedgerEntry)))
        assert len(ledger) == 1 and ledger[0].delta == 40


@pytest.mark.asyncio
@pytest.mark.parametrize("bound_task", ["kie-submit:73", "accepted-kie-task"])
async def test_rejection_cannot_refund_a_different_or_durable_kie_identity(kie_transaction_db, bound_task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from api.neironych_seedance_runtime import SubmissionContext
    from core.seedance_reconciliation import handle_submission_not_sent
    from db.models import CreditLedgerEntry, Generation, User

    with Session(kie_transaction_db, expire_on_commit=False) as sync:
        row = sync.get(Generation, 73)
        row.task_id = bound_task
        sync.commit()
        context = SubmissionContext(client_request_id=RID, before_submit=AsyncMock(),
            started=True, neironych_rejected=True)
        assert not await handle_submission_not_sent(LocalAsyncSession(sync), 73, context)
        assert row.task_id == bound_task and row.status.value == "processing"
        assert sync.get(User, 42).credits == 100
        assert list(sync.scalars(select(CreditLedgerEntry))) == []

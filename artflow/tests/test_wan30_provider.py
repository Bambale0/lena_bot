"""Wan3 service single provider submission; no real network or money."""
from unittest.mock import AsyncMock

import pytest

from api import wan30_provider
from api.neironych_seedance import NeironychSeedanceClient
from api.neironych_seedance_runtime import SubmissionContext
from api.wan30_contract import Wan30Request


@pytest.mark.asyncio
async def test_provider_uses_kie_if_neironych_catalog_does_not_offer_wan(monkeypatch):
    model="wan/3-0-video-prime"
    monkeypatch.setattr(wan30_provider.settings,"WAN30_PRIME_NEIRONYCH_MODEL_ID","",raising=False)
    lookup=AsyncMock(side_effect=AssertionError("No primary mapping: no GET required"))
    monkeypatch.setattr(NeironychSeedanceClient,"list_models",lookup)
    kie=AsyncMock(return_value={"code":200,"data":{"taskId":"kie_one"}})
    monkeypatch.setattr(wan30_provider.kieai_client,"create_task",kie)
    out=await wan30_provider.submit_wan30_provider(
        Wan30Request(model=model,prompt="One cat on a balcony"),
        idempotency_key="wan-prime-case-1",
        callback_url="https://example.test/task-callback",
    )
    assert out.provider=="kieai"
    assert out.task_id=="kie_one"
    assert kie.await_args.args[0]["model"]==model
    assert kie.await_args.kwargs["callback_url"]=="https://example.test/task-callback"
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_not_advertised_skips_neironych_paid_post(monkeypatch):
    monkeypatch.setattr(wan30_provider.settings,"WAN30_NEIRONYCH_MODEL_ID","wan-unapproved",raising=False)
    monkeypatch.setattr(NeironychSeedanceClient,"list_models",AsyncMock(return_value=["seedance-2.5"]))
    neironych=AsyncMock(side_effect=AssertionError("No paid post allowed"))
    monkeypatch.setattr(wan30_provider,"post_wan30_neironych",neironych)
    kie=AsyncMock(return_value={"code":200,"data":{"taskId":"kie_backup"}})
    monkeypatch.setattr(wan30_provider.kieai_client,"create_task",kie)
    out=await wan30_provider.submit_wan30_provider(
        Wan30Request(model="wan/3-0-video",prompt="Small sailboat"),
        idempotency_key="wan-std-case-1",
    )
    assert out.provider=="kieai"
    assert out.task_id=="kie_backup"
    neironych.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_requires_durable_journal_even_when_model_is_available(monkeypatch):
    monkeypatch.setattr(wan30_provider.settings,"WAN30_NEIRONYCH_MODEL_ID","wan-verified",raising=False)
    monkeypatch.setattr(NeironychSeedanceClient,"list_models",AsyncMock(return_value=["wan-verified"]))
    kie=AsyncMock()
    monkeypatch.setattr(wan30_provider.kieai_client,"create_task",kie)
    with pytest.raises(RuntimeError, match="durable"):
        await wan30_provider.submit_wan30_provider(
            Wan30Request(model="wan/3-0-video",prompt="Small sailboat"),
            idempotency_key="wan-std-case-2",
        )
    kie.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_with_journal_sends_neironych_then_keeps_provider_tag(monkeypatch):
    monkeypatch.setattr(wan30_provider.settings,"WAN30_NEIRONYCH_MODEL_ID","wan-verified",raising=False)
    monkeypatch.setattr(NeironychSeedanceClient,"list_models",AsyncMock(return_value=["wan-verified"]))
    neironych=AsyncMock(return_value="nrun_3")
    monkeypatch.setattr(wan30_provider,"post_wan30_neironych",neironych)
    kie=AsyncMock()
    monkeypatch.setattr(wan30_provider.kieai_client,"create_task",kie)
    async def before(idem, digest):pass
    ctx=SubmissionContext(
        client_request_id="d4496f2e-37d8-4b87-bba2-330374892b49",
        before_submit=before,
    )
    out=await wan30_provider.submit_wan30_provider(
        Wan30Request(model="wan/3-0-video",prompt="Small sailboat"),
        idempotency_key="wan-std-case-3",submission_context=ctx,
    )
    assert out.provider=="neironych"
    assert out.task_id=="neironych:nrun_3"
    kie.assert_not_awaited()
    assert neironych.await_args.kwargs["payload"]["model"]=="wan-verified"


@pytest.mark.asyncio
async def test_definite_primary_rejection_commits_kie_journal_before_paid_fallback(monkeypatch):
    from api.neironych_seedance import NeironychSeedanceError

    seen = []
    async def before_neironych(_idem, _hash):
        seen.append("neironych_journal")
    async def before_kie():
        seen.append("kie_journal")

    context = SubmissionContext(
        client_request_id="d4496f2e-37d8-4b87-bba2-330374892b49",
        before_submit=before_neironych,
        before_kie_submit=before_kie,
    )
    monkeypatch.setattr(wan30_provider.settings, "WAN30_NEIRONYCH_MODEL_ID", "real-wan", raising=False)
    monkeypatch.setattr(NeironychSeedanceClient, "list_models", AsyncMock(return_value=["real-wan"]))
    monkeypatch.setattr(
        wan30_provider, "post_wan30_neironych",
        AsyncMock(side_effect=NeironychSeedanceError(
            "rejected before admission", status_code=402,
            payload={"detail": "insufficient_balance"},
        )),
    )
    async def paid_kie(*args, **kwargs):
        seen.append("kie_paid_post")
        return {"data": {"taskId": "kie_fallback_persisted"}}
    monkeypatch.setattr(wan30_provider.kieai_client, "create_task", paid_kie)

    result = await wan30_provider.submit_wan30_provider(
        Wan30Request(model="wan/3-0-video", prompt="A steam train"),
        idempotency_key="wan-neironych-kie-fallback-3",
        submission_context=context,
    )
    assert result.provider == "kieai"
    assert result.task_id == "kie_fallback_persisted"
    assert seen.index("kie_journal") < seen.index("kie_paid_post")


@pytest.mark.asyncio
async def test_kie_journal_commit_failure_stops_before_paid_post(monkeypatch):
    async def before_neironych(_idem, _hash):
        pass
    async def before_kie():
        raise RuntimeError("database did not commit")

    context = SubmissionContext(
        client_request_id="d4496f2e-37d8-4b87-bba2-330374892b49",
        before_submit=before_neironych,
        before_kie_submit=before_kie,
    )
    monkeypatch.setattr(wan30_provider.settings, "WAN30_NEIRONYCH_MODEL_ID", "", raising=False)
    kie = AsyncMock()
    monkeypatch.setattr(wan30_provider.kieai_client, "create_task", kie)
    with pytest.raises(Exception):
        await wan30_provider.submit_wan30_provider(
            Wan30Request(model="wan/3-0-video", prompt="One toy robot"),
            idempotency_key="wan-neironych-kie-fallback-4",
            submission_context=context,
        )
    kie.assert_not_awaited()

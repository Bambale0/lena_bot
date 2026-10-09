from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes, neironych_seedance_runtime, seedance_provider_routing
from db import repository as repo
from db.models import GenerationStatus, GenerationType
from tests.test_neironych_video_notice_outbox import FakeSession


def generation():
    return SimpleNamespace(
        id=731,
        user_id=25,
        model="bytedance/seedance-2-5",
        gen_type=GenerationType.video,
        status=GenerationStatus.processing,
        task_id="neironych:provider-id",
        input_params="{}",
        credits_spent=70,
        result_url=None,
        result_urls=None,
        is_public_feed=False,
        is_prompt_library=False,
        prompt="scene",
        source_feed_gen_id=None,
        image_session_id=None,
        created_at=datetime.now(timezone.utc),
        finished_at=None,
        error_msg=None,
    )


@pytest.mark.asyncio
async def test_pending_unknown_submission_is_not_ordinary_processing(monkeypatch):
    client = SimpleNamespace(
        get_video=AsyncMock(
            return_value=SimpleNamespace(
                failed=False,
                done=False,
                status="pending",
                error="submission_outcome_unknown",
            )
        ),
        aclose=AsyncMock(),
        download_content_to=AsyncMock(),
    )
    monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
    with pytest.raises(RuntimeError, match="requires reconciliation"):
        await neironych_seedance_runtime.poll_product_video("neironych:provider-id")
    client.download_content_to.assert_not_awaited()
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_paused_neironych_route_uses_kie_before_any_neironych_post(monkeypatch):
    monkeypatch.setattr(
        seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych"
    )
    gate = AsyncMock(return_value=True)
    monkeypatch.setattr(seedance_provider_routing, "neironych_route_paused", gate, raising=False)
    kie = AsyncMock(return_value="kie-ok")
    neiro = AsyncMock(return_value="wrong-paid-post")
    result = await seedance_provider_routing.submit_seedance(
        "bytedance/seedance-2-5",
        kie=kie,
        neironych=neiro,
    )
    assert result == "kie-ok"
    kie.assert_awaited_once()
    neiro.assert_not_awaited()


@pytest.mark.asyncio
async def test_paused_route_never_falls_back_to_uncertain_provider(monkeypatch):
    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "kieai")
    monkeypatch.setattr(
        seedance_provider_routing,
        "neironych_route_paused",
        AsyncMock(return_value=True),
        raising=False,
    )
    kie = AsyncMock(side_effect=RuntimeError("KIE down"))
    neiro = AsyncMock(return_value="duplicate-risk")
    with pytest.raises(RuntimeError):
        await seedance_provider_routing.submit_seedance(
            "bytedance/seedance-2-5", kie=kie, neironych=neiro
        )
    neiro.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_notice_is_claimed_once_without_changing_money():
    gen = generation()
    gen.input_params = json.dumps(
        {"neironych_video_notice": {"kind": "reconciliation", "state": "pending", "attempts": 0}}
    )
    db = FakeSession(gen)
    claim = await repo.claim_neironych_video_notice(db, gen.id)
    assert claim is not None and claim.kind == "reconciliation"
    assert gen.status == GenerationStatus.processing and gen.credits_spent == 70
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    assert await repo.complete_neironych_video_notice(db, gen.id, claim.token, delivered=True)
    assert await repo.claim_neironych_video_notice(db, gen.id) is None


def test_history_exposes_review_instead_of_normal_processing():
    gen = generation()
    gen.input_params = json.dumps({"neironych_video_reconciliation": {"required": True}})
    assert miniapp_routes._gen_out(gen).status == "reconciliation_required"


def test_finished_generation_never_shows_stale_review_flag():
    gen = generation()
    gen.status = GenerationStatus.failed
    gen.input_params = json.dumps({"neironych_video_reconciliation": {"required": True}})
    assert miniapp_routes._gen_out(gen).status == "failed"


@pytest.mark.asyncio
async def test_review_marker_and_notice_are_idempotent_and_keep_balance(monkeypatch):
    gen = generation()
    db = FakeSession(gen)
    publish = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", publish)
    assert await repo.mark_neironych_video_reconciliation(db, gen.id, expected_task_id=gen.task_id)
    first = json.loads(gen.input_params)
    assert first["neironych_video_reconciliation"]["required"] is True
    assert first["neironych_video_notice"]["kind"] == "reconciliation"
    claim = await repo.claim_neironych_video_notice(db, gen.id)
    assert claim
    await repo.complete_neironych_video_notice(db, gen.id, claim.token, delivered=True)
    assert not await repo.mark_neironych_video_reconciliation(
        db, gen.id, expected_task_id=gen.task_id
    )
    after = json.loads(gen.input_params)
    assert after["neironych_video_notice"]["state"] == "sent"
    assert after["neironych_video_notice"]["attempts"] == 1
    assert gen.credits_spent == 70 and gen.status == GenerationStatus.processing
    assert "refund_applied" not in after
    publish.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal,wrong_id", [(True, False), (False, True)])
async def test_review_marker_cannot_override_final_or_different_task(
    monkeypatch, terminal, wrong_id
):
    gen = generation()
    if terminal:
        gen.status = GenerationStatus.done
    db = FakeSession(gen)
    publish = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", publish)
    assert not await repo.mark_neironych_video_reconciliation(
        db,
        gen.id,
        expected_task_id="neironych:other" if wrong_id else gen.task_id,
    )
    assert gen.input_params == "{}"
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_review_never_queues_telegram_notice(monkeypatch):
    gen = generation()
    gen.task_id = "web:" + gen.task_id
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    assert await repo.mark_neironych_video_reconciliation(
        FakeSession(gen), gen.id, expected_task_id=gen.task_id
    )
    assert "neironych_video_notice" not in json.loads(gen.input_params)


@pytest.mark.asyncio
async def test_review_path_marks_and_pauses_but_never_refunds_or_resubmits(monkeypatch):
    gen = generation()

    @asynccontextmanager
    async def gate(_task):
        yield True

    monkeypatch.setattr(miniapp_routes, "neironych_video_poll_guard", gate)
    poll = AsyncMock(
        side_effect=neironych_seedance_runtime.NeironychVideoReconciliationRequired("provider-id")
    )
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda _: poll)
    mark = AsyncMock(return_value=True)
    pause = AsyncMock()
    notify = AsyncMock()
    refund = AsyncMock()
    finish = AsyncMock()
    monkeypatch.setattr(repo, "mark_neironych_video_reconciliation", mark)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(repo, "finish_generation", finish)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(miniapp_routes, "pause_neironych_route", pause)
    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", notify)
    db = object()
    assert await miniapp_routes._reconcile_generation_status(db, gen) is gen
    mark.assert_awaited_once_with(db, gen.id, expected_task_id=gen.task_id)
    pause.assert_awaited_once_with(gen.model, "provider-id")
    notify.assert_awaited_once_with(db, gen.id)
    refund.assert_not_awaited()
    finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_inaccessible_admission_coordinator_blocks_all_paid_posts(monkeypatch):
    monkeypatch.setattr(
        seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych"
    )
    monkeypatch.setattr(
        seedance_provider_routing,
        "neironych_route_paused",
        AsyncMock(side_effect=ConnectionError("Redis unavailable")),
    )
    kie = AsyncMock()
    neiro = AsyncMock()
    with pytest.raises(ConnectionError):
        await seedance_provider_routing.submit_seedance(
            "bytedance/seedance-2-5", kie=kie, neironych=neiro
        )
    kie.assert_not_awaited()
    neiro.assert_not_awaited()


@pytest.mark.asyncio
async def test_circuit_is_model_scoped_and_bounded(monkeypatch):
    from core import seedance_reconciliation as circuit
    from core.config import settings

    entries = {}
    ttl = {}

    class Redis:
        async def exists(self, key):
            return key in entries

        async def set(self, key, value, *, ex):
            entries[key] = value
            ttl[key] = ex
            return True

        async def aclose(self):
            pass

    monkeypatch.setattr(circuit, "_redis_client", Redis)
    model = "bytedance/seedance-2-5"
    assert not await circuit.neironych_route_paused(model)
    await circuit.pause_neironych_route(model, "provider-id")
    assert await circuit.neironych_route_paused(model)
    assert not await circuit.neironych_route_paused("bytedance/seedance-2")
    assert list(ttl.values()) == [settings.SEEDANCE_UNCERTAIN_ROUTE_COOLDOWN_SECONDS]
    assert list(entries.values())[0].count("provider-id") == 1


def test_realtime_matches_history_review_status():
    from api.realtime import generation_event_payload

    gen = generation()
    gen.input_params = json.dumps({"neironych_video_reconciliation": {"required": True}})
    assert (
        generation_event_payload(gen)["status"]
        == miniapp_routes._gen_out(gen).status
        == "reconciliation_required"
    )


def test_review_ui_remains_nonterminal_and_is_not_success():
    from pathlib import Path

    utils = Path("webapp/src/lib/utils.ts").read_text()
    assert 'if (status === "reconciliation_required")' in utils
    assert '"running", "reconciliation_required"' in utils
    detail = Path("webapp/src/components/task-detail-sheet.tsx").read_text()
    assert 'task.status === "reconciliation_required"' in detail
    assert 'status === "reconciliation_required"' in Path("webapp/src/main.jsx").read_text()
    assert 'status === "reconciliation_required"' in Path("webapp/src/apix/AppV4.jsx").read_text()


@pytest.mark.asyncio
async def test_terminal_notice_replaces_review_and_stale_ack_cannot_erase_it():
    gen = generation()
    gen.input_params = json.dumps(
        {"neironych_video_notice": repo._new_neironych_video_notice("reconciliation")}
    )
    db = FakeSession(gen)
    old = await repo.claim_neironych_video_notice(db, gen.id)
    assert old
    gen.status = GenerationStatus.done
    params = json.loads(gen.input_params)
    params["neironych_video_notice"] = repo._new_neironych_video_notice("done")
    gen.input_params = json.dumps(params)
    assert not await repo.complete_neironych_video_notice(db, gen.id, old.token, delivered=True)
    new = await repo.claim_neironych_video_notice(db, gen.id)
    assert new and new.kind == "done" and new.token != old.token


@pytest.mark.asyncio
async def test_review_notice_text_does_not_claim_refund_or_provider_failure(monkeypatch):
    gen = generation()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=812)),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda **_: bot)
    assert await miniapp_routes._notify_neironych_video_reconciliation_in_bot(
        user=SimpleNamespace(tg_id=125), gen=gen
    )
    text = bot.send_message.await_args.kwargs["text"]
    assert "не подтвердил" in text and "удержаны" in text and "provider-id" in text
    assert "возвращено" not in text and "подтвердил ошибку" not in text
    bot.session.close.assert_awaited_once()

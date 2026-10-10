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
from tests import test_feed_remix_prompt_security as launch_fixtures
from tests.test_neironych_video_notice_outbox import FakeSession

api_launch = launch_fixtures.api_launch
video_launch = launch_fixtures.video_launch


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
async def test_unrelated_uncertain_job_does_not_reroute_new_neironych_job(monkeypatch):
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
    assert result == "wrong-paid-post"
    neiro.assert_awaited_once()
    kie.assert_not_awaited()
    gate.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_users_review_does_not_block_legitimate_primary_kie_fallback(monkeypatch):
    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "kieai")
    monkeypatch.setattr(
        seedance_provider_routing,
        "neironych_route_paused",
        AsyncMock(return_value=True),
        raising=False,
    )
    from api.kieai_client import KieDefiniteRejection
    kie = AsyncMock(side_effect=KieDefiniteRejection("KIE rejected before acceptance"))
    neiro = AsyncMock(return_value="neironych-ok")
    result = await seedance_provider_routing.submit_seedance(
        "bytedance/seedance-2-5", kie=kie, neironych=neiro
    )
    assert result == "neironych-ok"
    kie.assert_awaited_once()
    neiro.assert_awaited_once()


@pytest.mark.asyncio
async def test_kie_response_loss_never_starts_a_second_paid_neironych_job(monkeypatch):
    from api.kieai_client import KieSubmissionOutcomeUnknown

    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "kieai")
    kie = AsyncMock(side_effect=KieSubmissionOutcomeUnknown("response lost"))
    neironych = AsyncMock(return_value="should-never-submit")
    with pytest.raises(KieSubmissionOutcomeUnknown):
        await seedance_provider_routing.submit_seedance(
            "bytedance/seedance-2-5", kie=kie, neironych=neironych,
        )
    kie.assert_awaited_once()
    neironych.assert_not_awaited()


@pytest.mark.asyncio
async def test_kie_generic_failure_does_not_authorize_second_provider_post(monkeypatch):
    monkeypatch.setattr(seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "kieai")
    kie = AsyncMock(side_effect=RuntimeError("unknown KIE acceptance"))
    neironych = AsyncMock(return_value="second-charge")
    with pytest.raises(RuntimeError, match="unknown KIE acceptance"):
        await seedance_provider_routing.submit_seedance(
            "bytedance/seedance-2-5", kie=kie, neironych=neironych,
        )
    neironych.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_review_notice_is_suppressed_without_changing_money():
    gen = generation()
    gen.input_params = json.dumps(
        {"neironych_video_notice": {"kind": "reconciliation", "state": "pending", "attempts": 0}}
    )
    db = FakeSession(gen)
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    assert gen.status == GenerationStatus.processing and gen.credits_spent == 70
    assert json.loads(gen.input_params)["neironych_video_notice"]["state"] == "suppressed"
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
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    assert not await repo.mark_neironych_video_reconciliation(
        db, gen.id, expected_task_id=gen.task_id
    )
    after = json.loads(gen.input_params)
    assert after["neironych_video_notice"]["state"] == "suppressed"
    assert after["neironych_video_notice"]["attempts"] == 0
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
async def test_unrelated_admission_coordinator_outage_does_not_reroute_new_job(monkeypatch):
    monkeypatch.setattr(
        seedance_provider_routing.settings, "SEEDANCE_PRIMARY_PROVIDER", "neironych"
    )
    monkeypatch.setattr(
        seedance_provider_routing,
        "neironych_route_paused",
        AsyncMock(side_effect=ConnectionError("Redis unavailable")),
        raising=False,
    )
    kie = AsyncMock(return_value="kie-ok")
    neiro = AsyncMock(return_value="neironych-ok")
    result = await seedance_provider_routing.submit_seedance(
        "bytedance/seedance-2-5", kie=kie, neironych=neiro
    )
    assert result == "neironych-ok"
    kie.assert_not_awaited()
    neiro.assert_awaited_once()


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
    monkeypatch.setattr(circuit, "_db_has_unresolved_seedance", AsyncMock(return_value=False))
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
    # An old-version worker claimed this review before the silent policy.
    gen.input_params = json.dumps({"neironych_video_notice": {
        "kind": "reconciliation", "state": "sending", "token": "legacy-token", "attempts": 1,
    }})
    db = FakeSession(gen)
    gen.status = GenerationStatus.done
    params = json.loads(gen.input_params)
    params["neironych_video_notice"] = repo._new_neironych_video_notice("done")
    gen.input_params = json.dumps(params)
    assert not await repo.complete_neironych_video_notice(db, gen.id, "legacy-token", delivered=True)
    assert not await repo.suppress_claimed_neironych_review_notice(db, gen.id, "legacy-token")
    new = await repo.claim_neironych_video_notice(db, gen.id)
    assert new and new.kind == "done" and new.token != "legacy-token"


@pytest.mark.asyncio
async def test_intermediate_review_does_not_send_user_message(monkeypatch):
    gen = generation()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=812)),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda **_: bot)
    assert not await miniapp_routes._notify_neironych_video_reconciliation_in_bot(
        user=SimpleNamespace(tg_id=125), gen=gen
    )
    bot.send_message.assert_not_awaited()
    bot.session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_redis_pause_still_honors_durable_review_marker(monkeypatch):
    from core import seedance_reconciliation as circuit

    redis = SimpleNamespace(exists=AsyncMock(return_value=False), aclose=AsyncMock())
    persisted = AsyncMock(return_value=True)
    monkeypatch.setattr(circuit, "_redis_client", lambda: redis)
    monkeypatch.setattr(circuit, "_db_has_unresolved_seedance", persisted, raising=False)
    assert await circuit.neironych_route_paused("bytedance/seedance-2-5")
    persisted.assert_awaited_once_with("bytedance/seedance-2-5")


@pytest.mark.asyncio
async def test_stale_review_claim_never_sends_after_terminal_completion(monkeypatch):
    gen = generation()
    claimed = SimpleNamespace(generation=gen, kind="reconciliation", token="old-token", attempt=1)
    monkeypatch.setattr(repo, "claim_neironych_video_notice", AsyncMock(return_value=claimed))
    monkeypatch.setattr(repo, "complete_neironych_video_notice", AsyncMock(return_value=False))

    async def load_user(_session, _id):
        gen.status = GenerationStatus.done
        gen.input_params = json.dumps(
            {"neironych_video_notice": {"kind": "done", "state": "pending"}}
        )
        return SimpleNamespace(tg_id=25)

    monkeypatch.setattr(repo, "get_user_by_id", load_user)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(miniapp_routes, "_notify_neironych_video_reconciliation_in_bot", send)
    assert not await miniapp_routes._deliver_pending_neironych_video_notice(
        FakeSession(gen), gen.id
    )
    send.assert_not_awaited()


def test_standalone_web_card_projects_durable_review_state():
    from api.web.schemas import GenerationCard

    gen = generation()
    gen.input_params = json.dumps({"neironych_video_reconciliation": {"required": True}})
    assert GenerationCard.from_generation(gen).status == "reconciliation_required"


def test_v4_active_set_keeps_review_refreshable_until_terminal():
    import re
    import subprocess
    from pathlib import Path

    source = Path("webapp/src/apix/AppV4.jsx").read_text()
    declaration = re.search(r"const ACTIVE_STATUSES = new Set\([^;]+;", source).group(0)
    code = (
        declaration
        + "\nif (!ACTIVE_STATUSES.has('reconciliation_required') || ACTIVE_STATUSES.has('done') || ACTIVE_STATUSES.has('failed')) process.exit(1);"
    )
    result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


def test_standalone_site_understands_nonterminal_review_state():
    from pathlib import Path

    text = Path("landing/js/prototype-premium.js").read_text()
    assert 'if (source === "reconciliation_required")' in text
    assert 'if (value === "reconciliation_required")' in text
    assert '"uploading", "reconciliation_required"' in text


@pytest.mark.asyncio
async def test_durable_admission_query_requires_active_matching_provider_and_model(monkeypatch):
    from core import seedance_reconciliation as circuit
    from db import session as db_session

    queries = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def scalar(self, query):
            queries.append(query)
            return True

    monkeypatch.setattr(db_session, "AsyncSessionLocal", Session)
    assert await circuit._db_has_unresolved_seedance("bytedance/seedance-2-5")
    compiled = queries[0].compile()
    assert "EXISTS" in str(compiled)
    assert "generations.status IN" in str(compiled)
    assert "generations.input_params ~" in str(compiled)
    values = list(compiled.params.values())
    assert "bytedance/seedance-2-5" in values
    assert "neironych:%" in values and "web:neironych:%" in values
    assert [GenerationStatus.pending, GenerationStatus.processing] in values


@pytest.mark.asyncio
async def test_db_failure_after_lost_redis_key_is_fail_closed(monkeypatch):
    from core import seedance_reconciliation as circuit

    client = SimpleNamespace(exists=AsyncMock(return_value=False), aclose=AsyncMock())
    monkeypatch.setattr(circuit, "_redis_client", lambda: client)
    monkeypatch.setattr(
        circuit,
        "_db_has_unresolved_seedance",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        await circuit.neironych_route_paused("bytedance/seedance-2-5")
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_claim_revalidation_accepts_only_own_active_token():
    gen = generation()
    gen.input_params = json.dumps(
        {"neironych_video_notice": {"kind": "reconciliation", "state": "sending", "token": "valid"}}
    )
    db = FakeSession(gen)
    assert (
        await repo.current_neironych_review_notice(
            db, gen.id, "valid", expected_task_id=gen.task_id
        )
        is gen
    )
    assert (
        await repo.current_neironych_review_notice(
            db, gen.id, "stale", expected_task_id=gen.task_id
        )
        is None
    )
    assert (
        await repo.current_neironych_review_notice(
            db, gen.id, "valid", expected_task_id="neironych:other"
        )
        is None
    )
    gen.status = GenerationStatus.failed
    assert (
        await repo.current_neironych_review_notice(
            db, gen.id, "valid", expected_task_id=gen.task_id
        )
        is None
    )


def test_standalone_site_review_to_terminal_polling_predicate():
    import re
    import subprocess
    from pathlib import Path

    script = Path("landing/js/prototype-premium.js").read_text()
    functions = []
    for name in ("generationIsActive", "generationStatusCopy", "statusLabel"):
        functions.append(
            re.search(r"function " + name + r"\([^\n]*\) \{.*?\n\}", script, re.S).group(0)
        )
    checks = """
    if (!generationIsActive('reconciliation_required')) process.exit(1);
    if (generationIsActive('done') || generationIsActive('failed')) process.exit(2);
    const copy = generationStatusCopy('reconciliation_required');
    if (!copy.includes('Задача принята')) process.exit(3);
    if (statusLabel('reconciliation_required') !== statusLabel('processing')) process.exit(4);
    if (!copy.includes('Результат появится здесь автоматически')) process.exit(5);
    if (/поставщик|провайдер|уточняем|удержан|поддержк|ручн|возвращено/i.test(copy)) process.exit(8);
    """
    result = subprocess.run(
        ["node", "-e", "\n".join(functions) + checks], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr

@pytest.mark.asyncio
async def test_durable_submission_is_single_use_and_late_results_cannot_clobber(monkeypatch):
    gen = generation()
    gen.task_id = None
    session = FakeSession(gen)
    monkeypatch.setattr(repo, '_has_pending_refunded_seedance_review', AsyncMock(return_value=False))
    monkeypatch.setattr(repo, '_publish_generation_update', AsyncMock())
    request_id = 'e150cc69-0350-43aa-a4fc-a6b17388ec10'
    assert await repo.begin_seedance_submission(session, gen.id, request_id, 'idem', 'a' * 64, product_model=gen.model)
    assert gen.task_id == 'neironych-submit:' + request_id
    assert not await repo.begin_seedance_submission(session, gen.id, request_id, 'idem', 'a' * 64, product_model=gen.model)
    assert await repo.mark_seedance_submission_unknown(session, gen.id, request_id)
    assert gen.credits_spent == 70
    assert await repo.bind_seedance_submission_task(session, gen.id, request_id, 'neironych:found')
    assert not await repo.mark_seedance_submission_unknown(session, gen.id, request_id)
    assert not await repo.bind_seedance_submission_task(session, gen.id, request_id, 'neironych:late-other')
    assert gen.task_id == 'neironych:found'

@pytest.mark.asyncio
async def test_terminal_submission_marker_is_never_overwritten(monkeypatch):
    gen = generation()
    gen.task_id = None
    session = FakeSession(gen)
    monkeypatch.setattr(repo, '_has_pending_refunded_seedance_review', AsyncMock(return_value=False))
    monkeypatch.setattr(repo, '_publish_generation_update', AsyncMock())
    request_id = 'e150cc69-0350-43aa-a4fc-a6b17388ec10'
    assert await repo.begin_seedance_submission(session, gen.id, request_id, 'idem', 'a' * 64, product_model=gen.model)
    gen.status = GenerationStatus.done
    original = gen.input_params
    assert not await repo.mark_seedance_submission_unknown(session, gen.id, request_id)
    assert not await repo.bind_seedance_submission_task(session, gen.id, request_id, 'neironych:late')
    assert gen.input_params == original


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "remix"])
@pytest.mark.parametrize("surface", ["miniapp", "web"])
@pytest.mark.parametrize("not_sent", [False, True])
async def test_new_seedance_api_submission_outcome_handling(api_launch, monkeypatch, operation, surface, not_sent):
    from fastapi import HTTPException

    from api.neironych_seedance import NeironychPreSubmitFailure, NeironychSubmissionUnknown
    from core.seedance_reconciliation import RECONCILIATION_KEY

    route = api_launch.routes
    model = "bytedance/seedance-2"
    gen = api_launch.save.return_value
    gen.model, gen.gen_type, gen.task_id = model, GenerationType.video, "neironych-submit:synthetic"
    gen.input_params = "{}"
    api_launch.source.gen_type = GenerationType.image
    api_launch.source.model = model
    context = SimpleNamespace(client_request_id="synthetic", started=True)
    monkeypatch.setattr(route, "make_submission_context", lambda *_a, **_k: context)
    # The fake session contains no PostgreSQL rows; exercise persistence in
    # repository-specific tests and keep this API test about exception routing.
    register_callback = AsyncMock(return_value=True)
    monkeypatch.setattr(route.repo, "register_kie_video_callback", register_callback)

    async def hold(*_args):
        gen.input_params = json.dumps({RECONCILIATION_KEY: {"required": True}})
        return True

    held = AsyncMock(side_effect=hold)
    monkeypatch.setattr(route, "handle_submission_unknown", held)
    fail, refund = AsyncMock(), AsyncMock()
    monkeypatch.setattr(route.repo, "fail_generation", fail)
    monkeypatch.setattr(route.repo, "add_credits", refund)
    no_post = AsyncMock(return_value=True)
    monkeypatch.setattr(route, "handle_submission_not_sent", no_post)
    error = NeironychPreSubmitFailure if not_sent else NeironychSubmissionUnknown
    api_launch.generate.side_effect = error("synthetic", "apix-video-99")
    if operation == "launch":
        body = route.VideoGenRequest(model=model, prompt="synthetic scene", duration=5)
        call = route.create_video_generation(body, api_launch.session, api_launch.user, surface)
    else:
        body = route.FeedRemixRequest(model=model, change_request="make the coat blue", duration=5)
        call = route.remix_feed_post(77, body, api_launch.session, api_launch.user, surface)
    if not_sent:
        with pytest.raises(HTTPException) as raised:
            await call
        assert raised.value.status_code == 503
        no_post.assert_awaited_once()
        held.assert_not_awaited()
    else:
        result = await call
        assert result.status == "reconciliation_required"
        held.assert_awaited_once()
        no_post.assert_not_awaited()
    assert api_launch.generate.await_args.kwargs["neironych_submission"] is context
    fail.assert_not_awaited()
    refund.assert_not_awaited()
    route.repo.update_generation_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["launch", "repeat"])
@pytest.mark.parametrize("not_sent", [False, True])
async def test_new_seedance_bot_submission_outcome_handling(video_launch, monkeypatch, operation, not_sent):
    from api.neironych_seedance import NeironychPreSubmitFailure, NeironychSubmissionUnknown
    from bot.handlers import video_gen

    model = "bytedance/seedance-2"
    fixture = video_launch
    fixture.data.update(model_key=model, mode="text", image_url=None)
    fixture.kwargs.update(source_feed_gen_id=None, hidden_feed_prompt=False, prompt="synthetic scene")
    context = SimpleNamespace(client_request_id="synthetic", started=True)
    monkeypatch.setattr(video_gen, "make_submission_context", lambda *_a, **_k: context)
    held, shown = AsyncMock(return_value=True), AsyncMock()
    monkeypatch.setattr(video_gen, "handle_submission_unknown", held)
    monkeypatch.setattr(video_gen, "_show_video_submission_review", shown)
    fixture.repo.fail_generation_and_refund = AsyncMock()
    fixture.repo.register_kie_video_callback = AsyncMock(return_value=True)
    no_post = AsyncMock(return_value=True)
    monkeypatch.setattr(video_gen, "handle_submission_not_sent", no_post)
    error = NeironychPreSubmitFailure if not_sent else NeironychSubmissionUnknown
    fixture.service.generate_video.side_effect = error("synthetic", "apix-video-99")
    if operation == "launch":
        assert await video_gen._launch_video_generation_from_state(**fixture.kwargs) is (not not_sent)
    else:
        previous = SimpleNamespace(id=88, user_id=42, prompt="synthetic scene", model=model,
                                   source_feed_gen_id=None, input_params={})
        fixture.repo.get_generation_by_id.return_value = previous
        monkeypatch.setattr("bot.handlers.genjutsu_replace.restore_result", AsyncMock(return_value=False))
        monkeypatch.setattr(video_gen, "_video_repeat_params_for_generation", AsyncMock(return_value=fixture.data))
        call = SimpleNamespace(data="regen:video:88", answer=AsyncMock(), message=AsyncMock())
        await video_gen.cb_regen_video(call, fixture.kwargs["session"], fixture.kwargs["state"],
                                      fixture.kwargs["db_user"], fixture.kwargs["bot"])
    assert fixture.service.generate_video.await_args.kwargs["neironych_submission"] is context
    if not_sent:
        no_post.assert_awaited_once()
        held.assert_not_awaited()
        shown.assert_not_awaited()
    else:
        no_post.assert_not_awaited()
        held.assert_awaited_once()
        shown.assert_awaited_once()
    fixture.repo.fail_generation_and_refund.assert_not_awaited()
    fixture.repo.update_generation_task.assert_not_awaited()

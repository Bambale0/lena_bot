"""Release regressions: recovery must never repeat an ambiguously paid POST.

Nexus's documented 24-hour cache does not serialize requests or cache 5xx.
A signed callback binds the saved immutable submission instead of an unsafe
replay reconstructed from mutable ImageSession settings.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from PIL import Image

import main
from api import miniapp_routes, neironych_image_adapter, nexus_image_adapter
from api.miniapp_auth import get_miniapp_user
from api.nexusapi_client import NexusApiClient, NexusApiError
from core import neironych_image_reconcile_scheduler as scheduler
from core.provider_routing import ProviderRoute
from db import repository as repo
from db.models import GenerationStatus, GenerationType
from db.session import get_session

RID = "d9307625-cff7-4341-8280-5a778154ccef"
SECRET = "callback-test-secret"
DURABLE = "https://example.test/static/generated/result.png"
TEMPORARY = "https://provider.test/temporary.png"


def generation(**overrides):
    values = dict(
        id=91, user_id=7, task_id=f"nexus-submit:{RID}", model="nano-banana-2.1",
        gen_type=GenerationType.image, status=GenerationStatus.processing,
        image_session_id=None, prompt="private prompt", input_params=None,
        created_at=datetime.now(timezone.utc), finished_at=None, credits_spent=2,
        result_url=None, result_urls=None, source_feed_gen_id=None,
        is_public_feed=False, is_prompt_library=False, action_type=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def scalar(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


@pytest.mark.asyncio
async def test_submission_snapshot_commits_once_and_preserves_private_metadata(monkeypatch):
    gen = generation(input_params=json.dumps({"hidden_prompt": True, "prompt_id": 3}))
    session = SimpleNamespace(execute=AsyncMock(return_value=scalar(gen)), commit=AsyncMock())
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    snapshot = {"request_id": RID, "params": {"prompt": "original", "image_size": "4K"}}
    assert await repo.persist_nexus_image_submission(session, gen.id, gen.task_id, snapshot)
    original = gen.input_params
    assert not await repo.persist_nexus_image_submission(
        session, gen.id, gen.task_id, {"request_id": RID, "params": {"prompt": "mutated"}}
    )
    assert gen.input_params == original
    assert json.loads(original)["hidden_prompt"] is True
    assert json.loads(original)["nexus_submission"] == snapshot
    assert "FOR UPDATE" in str(session.execute.await_args.args[0])
    for terminal in (GenerationStatus.done, GenerationStatus.failed):
        gen.status = terminal
        assert not await repo.persist_nexus_image_submission(session, gen.id, gen.task_id, snapshot)
        assert gen.status == terminal


@pytest.mark.asyncio
async def test_update_task_cannot_reopen_terminal_generation(monkeypatch):
    session = SimpleNamespace(execute=AsyncMock(return_value=scalar(None)), commit=AsyncMock())
    publish = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", publish)
    assert not await repo.update_generation_task(session, 91, "nexus:task", expected_task_id="old")
    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "generations.status IN ('pending', 'processing')" in sql
    assert "generations.task_id = 'old'" in sql
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_original_provider_payload_is_frozen_before_the_only_post(monkeypatch):
    events = []
    snapshots = []
    original_refs = ["https://example.test/original.png"]

    async def before(request_id, snapshot):
        assert request_id == RID
        snapshots.append(snapshot)
        original_refs[0] = "https://example.test/later.png"
        events.append("committed")

    async def handle(request):
        events.append("post")
        body = json.loads(request.content)
        assert snapshots[0]["params"] == {
            "model_name": "nano-banana-2.1", "prompt": "original", "image_size": "4K",
            "aspect_ratio": "4:3", "image_urls": ["https://example.test/original.png"],
        }
        assert body["params"]["image_urls"] == ["https://example.test/original.png"]
        assert request.headers["Idempotency-Key"] == RID
        webhook = httpx.URL(body["params"]["webhook_url"])
        assert webhook.params["nexus_request_id"] == RID
        assert webhook.params["nexus_signature"] == nexus_image_adapter.submission_signature(RID, SECRET)
        assert webhook.params["provider"] == "nexus"
        serialized = json.dumps(snapshots[0])
        assert SECRET not in serialized and "test-provider-key" not in serialized
        return httpx.Response(202, json={"task_id": "accepted"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="https://nexusapi.dev") as http:
        client = NexusApiClient(api_key="test-provider-key", client=http)
        monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
        result = await nexus_image_adapter.create_nexus_image_task(
            model_key="nano-banana-2.1", prompt="original", image_urls=original_refs,
            aspect_ratio="4:3", quality="4K", idempotency_key=RID,
            callback_url=f"https://example.test/webhook/kie?secret={SECRET}", before_submit=before,
        )
    assert result == "nexus:accepted"
    assert events == ["committed", "post"]


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [0, 23, 25, 48])
async def test_unknown_submission_never_replays_or_refunds_even_after_cache_ttl(monkeypatch, hours):
    gen = generation(created_at=datetime.now(timezone.utc) - timedelta(hours=hours))
    create = AsyncMock(side_effect=AssertionError("paid duplicate"))
    poll = AsyncMock(side_effect=AssertionError("not a task id"))
    refund = AsyncMock(side_effect=AssertionError("not definitive failure"))
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", create)
    monkeypatch.setattr(miniapp_routes.image_service, "poll_image_result_urls", poll)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    create.assert_not_awaited()
    poll.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, NexusApiError("network"), NexusApiError("no url", payload={"status": "completed"})])
async def test_nexus_pending_or_unrecoverable_success_never_gets_timeout_refund(monkeypatch, failure):
    gen = generation(task_id="nexus:accepted", created_at=datetime.now(timezone.utc) - timedelta(days=2))
    poll = AsyncMock(side_effect=failure, return_value=None)
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.image_service, "poll_image_result_urls", poll)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_nexus_strict_mirror_decodes_and_uses_true_image_mime(monkeypatch):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="PNG")
    download = AsyncMock(return_value=(buffer.getvalue(), "text/html"))
    save = Mock(return_value=DURABLE)
    monkeypatch.setattr(neironych_image_adapter, "download_public_url", download)
    monkeypatch.setattr(neironych_image_adapter, "save_public_file", save)
    assert await nexus_image_adapter.mirror_verified_nano_banana21_result(TEMPORARY) == DURABLE
    assert save.call_args.args[1] == "image/png"
    download.return_value = (b"<html>not a raster</html>", "image/png")
    save.reset_mock()
    with pytest.raises((ValueError, OSError)):
        await nexus_image_adapter.mirror_verified_nano_banana21_result(TEMPORARY)
    save.assert_not_called()


@pytest.fixture
def webhook_state(monkeypatch):
    gen = generation(input_params=json.dumps({"nexus_submission": {"request_id": RID, "has_webhook": True}}))
    session = SimpleNamespace(get=AsyncMock(return_value=None))

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    async def lookup(_session, task_id):
        return gen if gen.task_id == task_id else None

    async def bind(_session, gen_id, task_id, *, expected_task_id=None):
        if gen.status in {GenerationStatus.done, GenerationStatus.failed}:
            return False
        if expected_task_id and gen.task_id != expected_task_id:
            return False
        gen.task_id = task_id
        return True

    async def finish(_session, gen_id, url, *, result_urls, expected_task_id=None):
        if gen.status in {GenerationStatus.done, GenerationStatus.failed}:
            return None
        gen.status = GenerationStatus.done
        gen.result_url = url
        gen.result_urls = json.dumps(result_urls)
        return gen

    canonical = AsyncMock(return_value={"task_id": "accepted", "status": "completed", "result": {"image_url": TEMPORARY}})
    mirror = AsyncMock(return_value=DURABLE)
    finish_mock = AsyncMock(side_effect=finish)
    update_session = AsyncMock()
    refund = AsyncMock()
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(main, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(repo, "get_generation_by_task_id", AsyncMock(side_effect=lookup))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=77)))
    monkeypatch.setattr(repo, "update_generation_task", AsyncMock(side_effect=bind))
    monkeypatch.setattr(repo, "finish_generation", finish_mock)
    monkeypatch.setattr(repo, "update_image_session_last_result", update_session)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(nexus_image_adapter, "get_nexus_task_payload", canonical)
    monkeypatch.setattr(nexus_image_adapter, "mirror_verified_nano_banana21_result", mirror)
    return SimpleNamespace(gen=gen, canonical=canonical, mirror=mirror, finish=finish_mock,
                           update_session=update_session, refund=refund, session=session)


def callback_url():
    return nexus_image_adapter.nexus_webhook_url(nexus_image_adapter.correlated_webhook_url(
        f"http://test/webhook/kie?secret={SECRET}", RID
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["", "web:"])
async def test_lost_response_callback_binds_and_finishes_once(webhook_state, surface):
    state = webhook_state
    state.gen.task_id = surface + state.gen.task_id
    state.gen.image_session_id = 12
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        first = await client.post(callback_url(), json={"task_id": "accepted"})
        second = await client.post(callback_url(), json={"task_id": "accepted"})
    assert first.status_code == second.status_code == 200
    assert state.gen.task_id == surface + "nexus:accepted"
    state.finish.assert_awaited_once_with(
        state.session, 91, DURABLE, result_urls=[DURABLE], expected_task_id=surface + "nexus:accepted"
    )
    state.update_session.assert_awaited_once_with(state.session, 12, DURABLE, 91)
    state.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_corrupt_result_binds_task_for_poll_recovery_without_refund(webhook_state):
    state = webhook_state
    state.mirror.side_effect = ValueError("corrupt raster")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(callback_url(), json={"task_id": "accepted"})
    assert response.status_code == 503
    assert state.gen.task_id == "nexus:accepted"
    assert state.gen.status == GenerationStatus.processing
    state.finish.assert_not_awaited()
    state.refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["signature", "canonical_task", "submission"])
async def test_callback_rejects_mismatched_identity(webhook_state, fault):
    state = webhook_state
    url = callback_url()
    if fault == "signature":
        url = str(httpx.URL(url).copy_set_param("nexus_signature", "wrong"))
    elif fault == "canonical_task":
        state.canonical.return_value["task_id"] = "other-task"
    else:
        state.gen.input_params = json.dumps({"nexus_submission": {"request_id": "other", "has_webhook": True}})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(url, json={"task_id": "accepted"})
    assert response.status_code in {403, 409, 503}
    assert state.gen.task_id == f"nexus-submit:{RID}"
    state.finish.assert_not_awaited()
    state.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_loser_has_no_session_or_delivery_side_effects(webhook_state, monkeypatch):
    state = webhook_state
    state.gen.task_id = "nexus:accepted"
    state.gen.image_session_id = 12
    state.finish.side_effect = None
    state.finish.return_value = None
    bot = AsyncMock()
    monkeypatch.setattr(main, "bot", bot)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(callback_url(), json={"task_id": "accepted"})
    assert response.status_code == 200
    state.update_session.assert_not_awaited()
    bot.send_message.assert_not_awaited()
    bot.send_photo.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 2, 5])
async def test_scheduler_revisits_every_old_row_with_unending_forward_load(monkeypatch, batch_size):
    rows = [generation(id=i, task_id=f"nexus:{i}") for i in range(1, 8)]
    seen = []

    async def execute(stmt):
        params = stmt.compile().params
        lower = params["id_1"]
        upper = params.get("id_2", float("inf"))
        selected = [row for row in rows if lower < row.id <= upper][:params["param_1"]]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: selected))

    session = SimpleNamespace(execute=execute, rollback=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    async def reconcile(_session, gen):
        seen.append(gen.id)

    for key, value in [("_last_reconciled_id", 7), ("_revisit_id", 0), ("_revisit_ceiling", 0), ("_single_revisit_next", False)]:
        monkeypatch.setattr(scheduler, key, value)
    monkeypatch.setattr(scheduler.settings, "NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE", batch_size)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", reconcile)
    for _ in range(18):
        next_id = rows[-1].id + 1
        rows.extend(generation(id=i, task_id=f"nexus:{i}") for i in range(next_id, next_id + 8))
        assert await scheduler.reconcile_neironych_images_once() <= batch_size
    assert set(range(1, 8)) <= set(seen)
    assert len([row_id for row_id in seen if row_id > 7]) >= 7


@pytest.mark.asyncio
async def test_mounted_launch_persists_snapshot_before_ambiguous_post_and_hides_it(monkeypatch):
    gen = generation(status=GenerationStatus.pending, task_id=None, input_params='{"hidden_prompt": true}')
    session = SimpleNamespace(execute=AsyncMock(return_value=scalar(gen)), commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "get_nano21_route", AsyncMock(return_value=ProviderRoute("nano-banana-2.1", "nexus", "database")))
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2)))
    monkeypatch.setattr(repo, "count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr(repo, "charge_image_generation", AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=2)))
    monkeypatch.setattr(repo, "create_image_session", AsyncMock(return_value=SimpleNamespace(id=12)))
    monkeypatch.setattr(repo, "create_generation", AsyncMock(return_value=gen))
    monkeypatch.setattr(repo, "update_generation_task", AsyncMock())
    refund = AsyncMock()
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    posted = []

    async def handle(request):
        posted.append(request)
        snapshot = json.loads(gen.input_params)["nexus_submission"]
        assert snapshot["request_id"] == request.headers["Idempotency-Key"]
        assert snapshot["params"]["image_size"] == "4K"
        assert snapshot["params"]["image_urls"] == ["https://example.test/ref.png"]
        assert gen.task_id == nexus_image_adapter.encode_submission_id(snapshot["request_id"])
        raise httpx.ReadTimeout("lost create response", request=request)

    async def stub_session():
        yield session

    async def stub_user():
        return SimpleNamespace(id=7, tg_id=77, credits=100)

    main.app.dependency_overrides[get_session] = stub_session
    main.app.dependency_overrides[get_miniapp_user] = stub_user
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="https://nexusapi.dev") as provider:
            nexus = NexusApiClient(api_key="test-key", client=provider)
            monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: nexus)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                response = await client.post("/api/v1/generate/image", json={
                    "model": "nano-banana-2.1", "prompt": "private prompt", "quality": "4K",
                    "reference_urls": ["https://example.test/ref.png"],
                })
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "processing"
    assert response.json()["prompt"] == ""
    assert "nexus_submission" not in response.text and "private prompt" not in response.text
    assert len(posted) == 1
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_installed_repeat_wrapper_preserves_snapshot_and_returns_cas_result(monkeypatch):
    gen = generation(task_id="nexus:accepted", input_params=json.dumps({
        "public_task_id": "img_public", "nexus_submission": {"request_id": RID},
        "hidden_prompt": True,
    }))
    session = SimpleNamespace(execute=AsyncMock(return_value=scalar(gen)), commit=AsyncMock())
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    assert await repo.update_generation_task(session, 91, "nexus:accepted", expected_task_id=f"nexus-submit:{RID}")
    assert json.loads(gen.input_params)["nexus_submission"] == {"request_id": RID}
    assert "nexus:accepted" in json.loads(gen.input_params)["task_id_aliases"]
    assert session.execute.await_count == 2
    assert "FOR UPDATE" in str(session.execute.await_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["failed", "completed"])
async def test_stale_neironych_poll_cannot_settle_new_nexus_attempt(monkeypatch, state):
    stale = generation(task_id=f"neironych-image:{RID}")
    current = generation(task_id=f"nexus-submit:{RID}")
    published = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", published)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=current))
    monkeypatch.setattr(neironych_image_adapter, "fetch_nano_banana21_status", AsyncMock(return_value={
        "status": state, "result_url": TEMPORARY if state == "completed" else None,
    }))
    monkeypatch.setattr(neironych_image_adapter, "mirror_verified_nano_banana21_result", AsyncMock(return_value=DURABLE))
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    # The SELECT FOR UPDATE returns the current Nexus attempt; guarded UPDATE
    # returns no row because the persisted provider identity no longer matches.
    session = SimpleNamespace(
        execute=AsyncMock(return_value=scalar(current if state == "failed" else None)),
        commit=AsyncMock(), flush=AsyncMock(), add=Mock(),
    )
    assert await miniapp_routes._reconcile_neironych_image_generation(session, stale, RID) is current
    assert current.status == GenerationStatus.processing
    assert current.task_id == f"nexus-submit:{RID}"
    session.flush.assert_not_awaited()
    session.add.assert_not_called()
    published.assert_not_awaited()
    if state == "completed":
        statement = session.execute.await_args.args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert f"generations.task_id = 'neironych-image:{RID}'" in sql


@pytest.mark.asyncio
async def test_default_callback_is_authenticated_before_persisted_submit(monkeypatch):
    snapshots = []
    create = AsyncMock(return_value=SimpleNamespace(task_id="accepted"))
    client = SimpleNamespace(create_params=create, base_url="https://nexusapi.dev", api_key="test-key")
    monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
    monkeypatch.setattr(nexus_image_adapter.settings, "KIE_WEBHOOK_SECRET", SECRET)

    async def before(_request_id, snapshot):
        snapshots.append(snapshot)

    await nexus_image_adapter.create_nexus_image_task(
        model_key="nano-banana-2.1", prompt="photo", idempotency_key=RID, before_submit=before
    )
    assert snapshots[0]["has_webhook"] is True
    callback = httpx.URL(create.await_args.args[0]["webhook_url"])
    assert callback.params["nexus_request_id"] == RID
    assert callback.params["secret"] == SECRET
    create.reset_mock()
    monkeypatch.setattr(nexus_image_adapter.settings, "KIE_WEBHOOK_SECRET", "")
    with pytest.raises(ValueError, match="authenticated webhook"):
        await nexus_image_adapter.create_nexus_image_task(
            model_key="nano-banana-2.1", prompt="photo", idempotency_key=RID, before_submit=before
        )
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [200, 401, 503])
@pytest.mark.parametrize("response_task", ["accepted", "wrong"])
async def test_only_canonical_successful_get_can_authorize_failure_refund(monkeypatch, http_status, response_task):
    gen = generation(task_id="nexus:accepted")
    refund = AsyncMock(return_value=(True, 2))
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=gen))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(http_status, json={
            "task_id": response_task, "status": "failed", "error": "test failure",
        })), base_url="https://nexusapi.dev",
    ) as http:
        nexus = NexusApiClient(api_key="test-key", client=http)
        monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: nexus)
        await miniapp_routes._reconcile_generation_status(object(), gen)
    if http_status == 200 and response_task == "accepted":
        refund.assert_awaited_once()
        assert refund.await_args.kwargs["expected_task_id"] == "nexus:accepted"
    else:
        refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["api_key", "base_url"])
async def test_changed_nexus_namespace_blocks_poll_and_refund(monkeypatch, change):
    original = NexusApiClient(api_key="original-key", base_url="https://nexusapi.dev")
    snapshot = nexus_image_adapter.submission_snapshot({"model_name": "nano-banana-2.1", "prompt": "photo"}, RID, original)
    gen = generation(task_id="nexus:accepted", input_params=json.dumps({"nexus_submission": snapshot}))
    changed = NexusApiClient(api_key="different-key" if change == "api_key" else "original-key",
                             base_url="https://elsewhere.test" if change == "base_url" else "https://nexusapi.dev")
    monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: changed)
    poll = AsyncMock()
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.image_service, "poll_image_result_urls", poll)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    poll.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_nexus_namespace_blocks_callback_binding(webhook_state):
    state = webhook_state
    state.gen.input_params = json.dumps({"nexus_submission": {
        "request_id": RID, "has_webhook": True, "provider_scope_sha256": "wrong-namespace",
    }})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post(callback_url(), json={"task_id": "accepted"})
    assert response.status_code == 503
    assert state.gen.task_id == f"nexus-submit:{RID}"
    state.finish.assert_not_awaited()
    state.refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_orm_transition_preserves_terminal_state_and_immutable_snapshot(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from db.models import Generation

    engine = create_engine(f"sqlite:///{tmp_path / 'generation-state.db'}")
    Generation.__table__.create(engine)

    class AsyncSessionFacade:
        def __init__(self):
            self.sync = Session(engine, expire_on_commit=False)

        async def execute(self, statement):
            return self.sync.execute(statement)

        async def commit(self):
            self.sync.commit()

        async def refresh(self, row):
            self.sync.refresh(row)

    first, concurrent = AsyncSessionFacade(), AsyncSessionFacade()
    gen = Generation(id=91, user_id=7, model="nano-banana-2.1", gen_type=GenerationType.image,
                     prompt="original", credits_spent=2, status=GenerationStatus.processing,
                     task_id=f"nexus-submit:{RID}", input_params='{"hidden_prompt": true}')
    first.sync.add(gen)
    await first.commit()
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    try:
        # A different worker commits a snapshot after this Session loaded gen.
        snapshot = {"request_id": RID, "params": {"prompt": "original"}}
        assert await repo.persist_nexus_image_submission(concurrent, gen.id, gen.task_id, snapshot)
        assert await repo.update_generation_task(first, gen.id, "nexus:accepted", expected_task_id=gen.task_id)
        assert json.loads(gen.input_params)["nexus_submission"] == snapshot
        assert await repo.finish_generation(first, gen.id, DURABLE, expected_task_id="nexus:accepted")
        assert not await repo.update_generation_task(concurrent, gen.id, "nexus:late-result")
        await first.refresh(gen)
        assert gen.status == GenerationStatus.done
        assert gen.task_id == "nexus:accepted"
        assert gen.result_url == DURABLE
        assert json.loads(gen.input_params)["nexus_submission"] == snapshot
        assert first.sync.execute(select(Generation.status)).scalar_one() == GenerationStatus.done
    finally:
        first.sync.close()
        concurrent.sync.close()
        engine.dispose()

from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from api import image_service, miniapp_routes, nexus_image_adapter
from api import neironych_image_adapter as transport
from api import neironych_nano_pro_runtime as nano_pro
from api.image_service import ImageModel
from api.web import admin as web_admin
from bot.handlers import admin as bot_admin
from core import provider_routing
from db import repository as repo
from db.models import GenerationStatus, GenerationType

RID = "d9307625-cff7-4341-8280-5a778154ccef"
URL = "https://apix.test/result.png"


@pytest.mark.parametrize("quality", ["2K", "4K"])
@pytest.mark.parametrize("refs", [[], ["https://example.test/ref.png"]])
async def test_native_http_contract_and_snapshot_before_post(monkeypatch, quality, refs):
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(image, format="PNG")
    events, saved = [], []
    async def freeze(rid, value):
        assert rid == RID
        events.append("commit")
        saved.append(value)
    def respond(request):
        events.append("post")
        assert request.url.path == ("/v1/images/edits" if refs else "/v1/images/generations")
        assert request.headers["Idempotency-Key"] == request.headers["X-Client-Request-Id"] == RID
        assert request.extensions["timeout"]["read"] <= 110
        body = json.loads(request.content)
        assert body == {
            "model": "nano-banana-pro", "prompt": "A cup", "n": 1,
            "resolution": quality.lower(), "aspect_ratio": "16:9", "response_format": "b64_json",
            **({"images": [{"image_url": refs[0]}]} if refs else {}),
        }
        assert json.loads(saved[0]["body_json"]) == body
        assert "test-key" not in json.dumps(saved[0])
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(transport.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(transport.settings, "NEIRONYCH_API_KEY", "test-key")
    monkeypatch.setattr(transport, "save_public_file", MagicMock(return_value=URL))
    assert await nano_pro.generate(prompt="A cup", image_urls=refs, quality=quality, aspect_ratio="16:9", request_id=RID, before_submit=freeze) == URL
    assert events == ["commit", "post"]


async def test_primary_success_and_ambiguous_outcomes_never_pay_nexus(monkeypatch):
    primary = AsyncMock(return_value=URL)
    fallback = AsyncMock(side_effect=AssertionError("duplicate paid generation"))
    monkeypatch.setattr(nano_pro, "generate", primary)
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    kwargs = dict(primary_provider="neironych", quality="4K", aspect_ratio="1:1", request_id=RID)
    result = await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "A cup", **kwargs)
    assert result.provider == "neironych" and result.url == URL
    assert result.task_id == transport.encode_task_id(RID)
    for error in [transport.NeironychImageError("timeout"), transport.NeironychImageError("server", status_code=503)]:
        primary.side_effect = error
        with pytest.raises(transport.NeironychImageError):
            await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "A cup", **kwargs)
    fallback.assert_not_awaited()


@pytest.mark.parametrize("status", [401, 402, 403, 404, 429])
async def test_definitive_rejection_preserves_original_nexus_contract(monkeypatch, status):
    monkeypatch.setattr(nano_pro, "generate", AsyncMock(side_effect=transport.NeironychImageRejected("rejected", status_code=status)))
    fallback = AsyncMock(return_value="nexus:task")
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    handoff = AsyncMock()
    refs = ["https://example.test/ref.png"]
    result = await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "A cup", primary_provider="neironych", request_id=RID,
        image_url=refs, aspect_ratio="4:3", quality="4K", before_nexus_submit=handoff)
    assert result.provider == "nexus"
    assert fallback.call_args.kwargs["image_urls"] == refs
    assert fallback.call_args.kwargs["quality"] == "4K"
    assert fallback.call_args.kwargs["idempotency_key"] == RID
    assert fallback.call_args.kwargs["before_submit"] is handoff


@pytest.mark.parametrize("ratio,refs,primary", [
    ("1:1", [], "nexus"), ("auto", [], "nexus"),
])
async def test_unsupported_capabilities_bypass_primary_without_remapping(monkeypatch, ratio, refs, primary):
    native = AsyncMock(side_effect=AssertionError("unsupported contract"))
    fallback = AsyncMock(return_value="nexus:task")
    monkeypatch.setattr(nano_pro, "generate", native)
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "A cup", image_url=refs, aspect_ratio=ratio,
        quality="4K", primary_provider=primary, request_id=RID)
    native.assert_not_awaited()
    assert fallback.call_args.kwargs["aspect_ratio"] == ratio
    assert fallback.call_args.kwargs["image_urls"] == refs


@pytest.mark.parametrize("model", [ImageModel.NANO_BANANA_PRO, ImageModel.NANO_BANANA_PRO_VIP])
async def test_neironych_pro_explicit_auto_never_uses_paid_nexus(monkeypatch, model):
    primary, fallback = AsyncMock(), AsyncMock()
    monkeypatch.setattr(nano_pro, "generate", primary)
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    with pytest.raises(ValueError, match="Nano Banana Pro"):
        await image_service.generate_image(model, "A cup", primary_provider="neironych",
            aspect_ratio="auto", quality="2K", request_id=RID)
    primary.assert_not_awaited()
    fallback.assert_not_awaited()


async def test_missing_neironych_pro_ratio_uses_native_square_default(monkeypatch):
    primary, fallback = AsyncMock(return_value=URL), AsyncMock()
    monkeypatch.setattr(nano_pro, "generate", primary)
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_PRO, "A cup", primary_provider="neironych",
        aspect_ratio=None, quality="2K", request_id=RID,
    )
    assert result.provider == "neironych"
    assert primary.call_args.kwargs["aspect_ratio"] == "1:1"
    fallback.assert_not_awaited()


async def test_snapshot_admission_is_single_use_and_preserves_private_metadata(monkeypatch):
    gen = SimpleNamespace(model="nano-banana-pro", gen_type=GenerationType.image, status=GenerationStatus.processing,
        input_params=json.dumps({"hidden_prompt": True}), task_id=transport.encode_task_id(RID))
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: gen)), commit=AsyncMock())
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    saved = nano_pro.snapshot(nano_pro.build_payload(prompt="Original", image_urls=[], aspect_ratio="1:1", quality="4K"), RID)
    assert await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, saved)
    original = gen.input_params
    assert not await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, saved)
    assert gen.input_params == original
    assert json.loads(original)["hidden_prompt"] is True
    assert "FOR UPDATE" in str(db.execute.call_args.args[0])
    for status in [GenerationStatus.done, GenerationStatus.failed]:
        gen.status = status
        assert not await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, saved)


async def test_lost_admission_cannot_issue_a_paid_post(monkeypatch):
    post = AsyncMock(side_effect=AssertionError("paid duplicate"))
    monkeypatch.setattr(transport, "_generate_image", post)
    async def reject(*args):
        raise transport.NeironychImageError("already admitted", request_id=RID)
    with pytest.raises(transport.NeironychImageError):
        await nano_pro.generate(prompt="Cup", image_urls=[], aspect_ratio="1:1", quality="2K", request_id=RID, before_submit=reject)
    post.assert_not_awaited()


async def test_completed_replay_uses_exact_original_body_and_key(monkeypatch):
    payload = nano_pro.build_payload(prompt="Original", image_urls=["https://example.test/original.png"], aspect_ratio="4:3", quality="4K")
    saved = nano_pro.snapshot(payload, RID)
    post = AsyncMock(return_value=URL)
    monkeypatch.setattr(transport, "_generate_image", post)
    assert await nano_pro.recover_completed(saved, RID) == URL
    post.assert_awaited_once_with(payload, request_id=RID, subdir=nano_pro.MODEL, timeout_seconds=nano_pro.settings.NANO_BANANA_PRO_IMAGE_TIMEOUT_SECONDS)


@pytest.mark.parametrize("mutation", ["body", "scope", "key", "model", "endpoint", "contract", "missing"])
async def test_invalid_snapshot_never_replays(monkeypatch, mutation):
    payload = nano_pro.build_payload(prompt="Original", image_urls=[], aspect_ratio="1:1", quality="2K")
    saved = nano_pro.snapshot(payload, RID)
    if mutation == "body":
        saved["body_json"] += " "
    elif mutation == "scope":
        saved["credential_scope"] = "other"
    elif mutation == "key":
        saved["request_id"] = "other"
    elif mutation == "model":
        saved["model_key"] = "nano-banana-pro.1"
    elif mutation == "endpoint":
        saved["endpoint"] = "edits"
    elif mutation == "contract":
        payload["unsupported"] = True
        saved["body_json"] = json.dumps(payload)
        saved["body_sha256"] = hashlib.sha256(saved["body_json"].encode()).hexdigest()
    else:
        saved = None
    post = AsyncMock()
    monkeypatch.setattr(transport, "_generate_image", post)
    with pytest.raises(ValueError):
        await nano_pro.recover_completed(saved, RID)
    post.assert_not_awaited()


@pytest.mark.parametrize("state", ["processing", "queued", "not_found", "reconciliation_required", "failed"])
async def test_only_authenticated_completed_status_can_read_cached_response(monkeypatch, state):
    gen = SimpleNamespace(id=12, model="nano-banana-pro", task_id=transport.encode_task_id(RID),
        created_at=datetime.now(timezone.utc), status=GenerationStatus.processing)
    status = AsyncMock(return_value={"status": state})
    replay, refund = AsyncMock(), AsyncMock()
    monkeypatch.setattr(transport, "fetch_nano_banana21_status", status)
    monkeypatch.setattr(nano_pro, "recover_completed", replay)
    monkeypatch.setattr(miniapp_routes, "get_image_recovery_policy", AsyncMock(return_value=SimpleNamespace(auto_refund_seconds=3600)))
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=gen))
    await miniapp_routes._reconcile_neironych_image_generation(object(), gen, RID)
    status.assert_awaited_once_with(RID, expected_model="nano-banana-pro")
    replay.assert_not_awaited()
    assert refund.await_count == (1 if state == "failed" else 0)


@pytest.mark.parametrize("won", [True, False])
async def test_completed_b64_recovery_finishes_with_task_guard_and_single_delivery(monkeypatch, won):
    saved = {"original": True}
    gen = SimpleNamespace(id=12, user_id=7, model="nano-banana-pro", task_id=transport.encode_task_id(RID),
        image_session_id=3, created_at=datetime.now(timezone.utc), status=GenerationStatus.processing,
        input_params=json.dumps({nano_pro.SNAPSHOT_KEY: saved}), result_url=URL, result_urls=json.dumps([URL]))
    replay = AsyncMock(return_value=URL)
    finish = AsyncMock(return_value=gen if won else None)
    deliver, update_session = AsyncMock(), AsyncMock()
    monkeypatch.setattr(transport, "fetch_nano_banana21_status", AsyncMock(return_value={"status": "completed", "result_url": None}))
    monkeypatch.setattr(nano_pro, "recover_completed", replay)
    monkeypatch.setattr(repo, "finish_generation", finish)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7)))
    monkeypatch.setattr(repo, "update_image_session_last_result", update_session)
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", deliver)
    db = object()
    await miniapp_routes._reconcile_neironych_image_generation(db, gen, RID)
    replay.assert_awaited_once_with(saved, RID)
    finish.assert_awaited_once_with(db, 12, URL, result_urls=[URL], expected_task_id=gen.task_id)
    assert deliver.await_count == update_session.await_count == int(won)


async def test_route_bootstrap_override_audit_and_noop(monkeypatch):
    monkeypatch.setattr(provider_routing.settings, "NANO_BANANA_PRO_PRIMARY_PROVIDER", "neironych")
    db = SimpleNamespace(get=AsyncMock(return_value=None))
    assert (await provider_routing.get_nano_pro_route(db)).primary_provider == "neironych"
    row = SimpleNamespace(primary_provider="nexus", updated_by_admin_tg_id=42)
    db.get.return_value = row
    assert (await provider_routing.get_nano_pro_route(db)).primary_provider == "nexus"
    db = SimpleNamespace(execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]), add=MagicMock(), commit=AsyncMock())
    await provider_routing.set_nano_pro_route(db, "neironych", admin_tg_id=42, source="web")
    audit = db.add.call_args.args[0]
    assert (audit.model_key, audit.previous_provider, audit.new_provider) == ("nano-banana-pro", "nexus", "neironych")
    db.add.reset_mock()
    db.execute.side_effect = [None, SimpleNamespace(scalar_one=lambda: row)]
    await provider_routing.set_nano_pro_route(db, "neironych", admin_tg_id=42, source="telegram")
    db.add.assert_not_called()
    with pytest.raises(ValueError):
        await provider_routing.set_nano_pro_route(db, "kie", admin_tg_id=42, source="web")


async def test_admin_controls_are_authenticated_and_model_specific(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    body = web_admin.Nano21ProviderRoutingUpdate(primary_provider="neironych")
    assert (await web_admin.admin_get_nano_pro_provider(session=object(), user=None)).status_code == 401
    assert (await web_admin.admin_set_nano_pro_provider(body=body, session=object(), user=SimpleNamespace(tg_id=7))).status_code == 403
    write = AsyncMock(return_value=provider_routing.ProviderRoute("nano-banana-pro", "neironych", "database", 42))
    monkeypatch.setattr(web_admin, "set_nano_pro_route", write)
    assert (await web_admin.admin_set_nano_pro_provider(body=body, session=object(), user=SimpleNamespace(tg_id=42)))["data"]["model_key"] == "nano-banana-pro"
    assert write.call_args.kwargs == {"admin_tg_id": 42, "source": "web"}
    assert "adm:nano_pro_route" in {b.callback_data for row in bot_admin.admin_menu_kb().inline_keyboard for b in row}
    assert {b.callback_data for row in bot_admin._nano_pro_provider_kb("neironych").inline_keyboard for b in row} >= {"adm:nano_pro_primary:nexus", "adm:nano_pro_primary:neironych"}


async def test_operation_executor_preserves_route_and_both_handoffs():
    from dataclasses import replace

    from api.provider_operation_registry import execute_operation, get_operation_spec
    execute = AsyncMock()
    spec = replace(get_operation_spec("image.nano.pro"), executor=execute)
    native, fallback = AsyncMock(), AsyncMock()
    await execute_operation(spec, {"prompt": "Cup", "aspect_ratio": "1:1", "quality": "4K"}, request_id=RID,
        primary_provider="neironych", before_neironych_submit=native, before_nexus_submit=fallback)
    assert execute.call_args.kwargs["request_id"] == RID
    assert execute.call_args.kwargs["primary_provider"] == "neironych"
    assert execute.call_args.kwargs["before_neironych_submit"] is native
    assert execute.call_args.kwargs["before_nexus_submit"] is fallback


def test_scheduler_includes_nano_pro_and_timeout_stays_below_ingress():
    from core.config import Settings
    from core.neironych_image_reconcile_scheduler import _eligible_query
    sql = str(_eligible_query().compile(compile_kwargs={"literal_binds": True}))
    assert "'nano-banana-pro'" in sql
    with pytest.raises(ValidationError):
        Settings(BOT_TOKEN="123456:test", COMET_API_KEY="test", NANO_BANANA_PRO_IMAGE_TIMEOUT_SECONDS=120)


@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-pro-vip", "gpt-image-2-vip"])
async def test_dedicated_hmac_authenticates_nexus_without_legacy_shared_secret(monkeypatch, model):
    import main
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_HMAC_KEY", "dedicated-callback-key")
    create = AsyncMock(return_value=SimpleNamespace(task_id="accepted"))
    client = SimpleNamespace(create_params=create, base_url="https://nexus.test", api_key="provider-key")
    monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
    saved = []
    async def freeze(rid, snapshot):
        saved.append(snapshot)
    await nexus_image_adapter.create_nexus_image_task(model_key=model, prompt="Cup", idempotency_key=RID, before_submit=freeze)
    url = httpx.URL(create.call_args.args[0]["webhook_url"])
    assert url.params["nexus_signature"] == nexus_image_adapter.submission_signature(RID, "dedicated-callback-key")
    assert "dedicated-callback-key" not in str(url)
    assert "dedicated-callback-key" not in json.dumps(saved)
    # A valid signature reaches canonical provider GET; forged ones fail first.
    fetch = AsyncMock(side_effect=RuntimeError("sentinel canonical GET reached"))
    monkeypatch.setattr(nexus_image_adapter, "get_nexus_task_payload", fetch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as http:
        response = await http.post(str(url), json={"task_id": "accepted"})
        assert response.status_code == 503
        fetch.assert_awaited_once_with("accepted")
        fetch.reset_mock()
        bad = url.copy_set_param("nexus_signature", "f" * 64)
        assert (await http.post(str(bad), json={"task_id": "accepted"})).status_code == 403
        fetch.assert_not_awaited()
        # Unsigned/unrelated callbacks retain production's outer verifier.
        unsigned = str(url.copy_remove_param("nexus_request_id").copy_remove_param("nexus_signature"))
        assert (await http.post(unsigned, json={"task_id": "accepted"})).status_code == 503
        unrelated = str(url.copy_set_param("provider", "kie"))
        assert (await http.post(unrelated, json={"task_id": "accepted"})).status_code == 503
        fetch.assert_not_awaited()


async def test_unregistered_legacy_provider_gateway_cannot_bypass_durable_launch(monkeypatch):
    from fastapi.routing import APIRoute

    import main
    assert not any(isinstance(route, APIRoute) and "/provider-operations" in route.path for route in main.app.routes)
    paid = AsyncMock(side_effect=AssertionError("unregistered gateway must not submit"))
    monkeypatch.setattr(image_service, "generate_image", paid)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as http:
        response = await http.post("/api/web/provider-operations/image.nano.pro", json={"params": {"prompt": "Cup"}})
    # The root static mount rejects POST with405; no API handler is mounted.
    assert response.status_code == 405
    paid.assert_not_awaited()


@pytest.mark.parametrize("entry", ["web", "miniapp", "web_feed", "miniapp_feed", "bot"])
async def test_every_launch_surface_commits_native_snapshot_before_paid_post(monkeypatch, entry):
    from test_nano_banana_pro_reference_transport import local_launch

    from bot.handlers import image_gen
    from db.models import ImageGenerationAction

    launch = local_launch.__wrapped__(monkeypatch)
    gen = launch.generation
    gen.model, gen.task_id, gen.input_params = "nano-banana-pro", None, None
    route = AsyncMock(return_value=provider_routing.ProviderRoute(nano_pro.MODEL, "neironych", "database"))
    monkeypatch.setattr(miniapp_routes, "get_nano_pro_route", route)
    monkeypatch.setattr(image_gen, "get_nano_pro_route", route)
    events = []
    async def task(db, gid, marker, **kw):
        gen.task_id = marker
        return True
    async def freeze(db, gid, marker, saved):
        assert gen.task_id == marker
        assert saved["request_id"] == transport.decode_task_id(marker)
        gen.input_params = json.dumps({nano_pro.SNAPSHOT_KEY: saved})
        events.append("commit_snapshot")
        return True
    async def post(payload, **kw):
        events.append("paid_post")
        assert json.loads(gen.input_params)[nano_pro.SNAPSHOT_KEY]["request_id"] == kw["request_id"]
        assert payload["model"] == nano_pro.MODEL
        assert payload["resolution"] == "4k"
        return URL
    async def finish(db, gid, url, **kw):
        assert kw["expected_task_id"] == gen.task_id
        gen.status = GenerationStatus.done
        gen.result_url, gen.result_urls = URL, json.dumps([URL])
        return gen
    monkeypatch.setattr(repo, "update_generation_task", task)
    monkeypatch.setattr(repo, "persist_neironych_nano_pro_submission", freeze)
    monkeypatch.setattr(repo, "finish_generation", finish)
    monkeypatch.setattr(repo, "update_image_session_last_result", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", AsyncMock())
    monkeypatch.setattr(transport, "_generate_image", post)
    if entry.endswith("_feed"):
        await miniapp_routes.remix_feed_post(77, miniapp_routes.FeedRemixRequest(
            model=nano_pro.MODEL, image_url="https://example.test/ref.png", mode="image", quality="4K", aspect_ratio="16:9"),
            session=launch.session, user=launch.user, surface=entry.removesuffix("_feed"))
    elif entry == "bot":
        current = await repo.create_image_session(launch.session, launch.user.id, nano_pro.MODEL, "text", "16:9", "4K", 1, "Cup")
        started = await image_gen._launch_session_generation(source_message=AsyncMock(), state=AsyncMock(), session=launch.session,
            db_user=launch.user, image_session=current, prompt="Cup", action_type=ImageGenerationAction.initial,
            reference_url=None, parent_generation_id=None, launching_text="Starting", queued_text="Queued")
        assert started
    else:
        await miniapp_routes.create_image_generation(miniapp_routes.ImageGenRequest(
            model=nano_pro.MODEL, prompt="Cup", quality="4K", aspect_ratio="16:9"),
            session=launch.session, user=launch.user, surface=entry)
    assert events == ["commit_snapshot", "paid_post"]
    repo.charge_image_generation.assert_awaited_once()

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from api import image_service
from api import neironych_image_adapter as adapter
from api.image_service import ImageModel
from api.web import admin as web_admin
from bot.handlers import admin as bot_admin
from core import provider_routing

MODELS = [ImageModel.SEEDREAM_5_PRO_T2I, ImageModel.SEEDREAM_5_PRO_I2I]


@pytest.mark.parametrize("quality,resolution", [("basic", "1k"), ("high", "2k")])
@pytest.mark.parametrize("refs", [[], ["https://example.test/ref.png"]])
async def test_images_http_contract(monkeypatch, quality, resolution, refs):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, format="PNG")
    rid = "d9307625-cff7-4341-8280-5a778154ccef"
    def respond(request):
        assert request.url.path == ("/v1/images/edits" if refs else "/v1/images/generations")
        assert request.headers["Idempotency-Key"] == rid
        assert request.headers["X-Client-Request-Id"] == rid
        body = json.loads(request.content)
        assert body == {
            "model": "seedream-5.0-pro", "prompt": "A cup", "n": 1,
            "resolution": resolution, "aspect_ratio": "16:9", "response_format": "b64_json",
            **({"images": [{"image_url": refs[0]}]} if refs else {}),
        }
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    save = MagicMock(return_value="https://apix.test/result.png")
    monkeypatch.setattr(adapter, "save_public_file", save)
    result = await adapter.generate_seedream5_image(
        prompt="A cup", image_urls=refs, quality=quality, aspect_ratio="16:9", request_id=rid,
    )
    assert result == "https://apix.test/result.png"
    assert save.call_args.kwargs["subdir"] == "generated/seedream-5-pro"


@pytest.mark.parametrize("model", MODELS)
async def test_primary_success_does_not_submit_kie(monkeypatch, model):
    primary = AsyncMock(return_value="https://apix.test/result.png")
    kie = AsyncMock(side_effect=AssertionError("second paid request"))
    monkeypatch.setattr(adapter, "generate_seedream5_image", primary)
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie)
    result = await image_service.generate_image(
        model, "A cup", image_url=["https://example.test/ref.png"], primary_provider="neironych",
        request_id="d9307625-cff7-4341-8280-5a778154ccef", quality="high",
    )
    assert result.provider == "neironych" and result.url == "https://apix.test/result.png"
    assert result.task_id.startswith("neironych-image:")
    kie.assert_not_awaited()


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("error", [adapter.NeironychImageError("timeout"), adapter.NeironychImageError("server", status_code=503)])
async def test_ambiguous_outcome_never_falls_back(monkeypatch, model, error):
    monkeypatch.setattr(adapter, "generate_seedream5_image", AsyncMock(side_effect=error))
    kie = AsyncMock()
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie)
    with pytest.raises(adapter.NeironychImageError):
        await image_service.generate_image(model, "A cup", image_url=["https://example.test/ref.png"], primary_provider="neironych")
    kie.assert_not_awaited()


async def test_definite_rejection_uses_original_kie_contract(monkeypatch):
    monkeypatch.setattr(adapter, "generate_seedream5_image", AsyncMock(side_effect=adapter.NeironychImageRejected("balance", status_code=402)))
    kie = AsyncMock(return_value={"data": {"taskId": "kie-task"}})
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie)
    result = await image_service.generate_image(MODELS[0], "A cup", primary_provider="neironych", quality="high")
    assert result.task_id == "kie-task"
    assert kie.call_args.args[0]["input"]["quality"] == "high"


async def test_kie_override_and_ten_refs_preserve_capabilities(monkeypatch):
    primary = AsyncMock(side_effect=AssertionError("must use KIE"))
    monkeypatch.setattr(adapter, "generate_seedream5_image", primary)
    monkeypatch.setattr(image_service, "_prepare_reference_urls_for_model", AsyncMock(side_effect=lambda model, refs: refs))
    kie = AsyncMock(return_value={"data": {"taskId": "kie-task"}})
    monkeypatch.setattr(image_service.kieai_client, "create_task", kie)
    for provider, refs in [("kie", []), ("neironych", [f"https://example.test/{i}.png" for i in range(10)])]:
        result = await image_service.generate_image(MODELS[0], "A cup", image_url=refs, primary_provider=provider)
        assert result.task_id == "kie-task"
    primary.assert_not_awaited()


async def test_route_bootstrap_db_override_and_audit(monkeypatch):
    monkeypatch.setattr(provider_routing.settings, "SEEDREAM_5_PRIMARY_PROVIDER", "neironych")
    assert (await provider_routing.get_seedream5_route(SimpleNamespace(get=AsyncMock(return_value=None)))).primary_provider == "neironych"
    row = SimpleNamespace(primary_provider="kie", updated_by_admin_tg_id=42)
    assert (await provider_routing.get_seedream5_route(SimpleNamespace(get=AsyncMock(return_value=row)))).primary_provider == "kie"
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]),
        add=MagicMock(), commit=AsyncMock(),
    )
    route = await provider_routing.set_seedream5_route(session, "neironych", admin_tg_id=42, source="web")
    assert route.primary_provider == "neironych"
    audit = session.add.call_args.args[0]
    assert audit.model_key == "seedream-5.0-pro"
    assert (audit.previous_provider, audit.new_provider, audit.changed_by_admin_tg_id) == ("kie", "neironych", 42)
    session.commit.assert_awaited_once()


async def test_admin_control_auth_and_validation(monkeypatch):
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    body = web_admin.Seedream5ProviderRoutingUpdate(primary_provider="neironych")
    assert (await web_admin.admin_get_seedream5_provider(session=object(), user=None)).status_code == 401
    assert (await web_admin.admin_set_seedream5_provider(body=body, session=object(), user=SimpleNamespace(tg_id=7))).status_code == 403
    with pytest.raises(ValidationError):
        web_admin.Seedream5ProviderRoutingUpdate(primary_provider="nexus")
    with pytest.raises(ValueError):
        await provider_routing.set_seedream5_route(object(), "nexus", admin_tg_id=42, source="web")
    write = AsyncMock(return_value=provider_routing.ProviderRoute("seedream-5.0-pro", "neironych", "database", 42))
    monkeypatch.setattr(web_admin, "set_seedream5_route", write)
    response = await web_admin.admin_set_seedream5_provider(body=body, session=object(), user=SimpleNamespace(tg_id=42))
    assert response["data"]["primary_provider"] == "neironych"
    assert write.call_args.kwargs == {"admin_tg_id": 42, "source": "web"}
    callbacks = {b.callback_data for row in bot_admin.admin_menu_kb().inline_keyboard for b in row}
    assert "adm:seedream5_route" in callbacks
    assert {b.callback_data for row in bot_admin._seedream5_provider_kb("neironych").inline_keyboard for b in row} >= {"adm:seedream5_primary:kie", "adm:seedream5_primary:neironych"}


async def test_seedream_reconciliation_validates_model(monkeypatch):
    real_client = httpx.AsyncClient
    def respond(request):
        return httpx.Response(200, json={"model_slug": "seedream-5.0-pro", "status": "completed", "result_url": "https://example.test/result.png"})
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(adapter.settings, "NEIRONYCH_API_KEY", "test-key")
    rid = "d9307625-cff7-4341-8280-5a778154ccef"
    result = await adapter.fetch_nano_banana21_status(rid, expected_model="seedream-5.0-pro")
    assert result["status"] == "completed"
    with pytest.raises(adapter.NeironychImageError):
        await adapter.fetch_nano_banana21_status(rid, expected_model="nano-banana-2.1")



@pytest.mark.parametrize("model", MODELS)
async def test_real_operation_executor_forwards_routing_and_identity(monkeypatch, model):
    from api.provider_operation_registry import execute_operation, get_operation_spec
    contract = "image.seedream5.i2i" if model == MODELS[1] else "image.seedream5.t2i"
    spec = get_operation_spec(contract)
    execute = AsyncMock(return_value=image_service.ImageResult(is_async=False, url="https://example.test/result.png", provider="neironych"))
    from dataclasses import replace
    spec = replace(spec, executor=execute)
    handoff = AsyncMock()
    rid = "d9307625-cff7-4341-8280-5a778154ccef"
    params = {"prompt": "A cup", "quality": "basic"}
    if model == MODELS[1]:
        params["image_url"] = "https://example.test/ref.png"
    await execute_operation(spec, params, request_id=rid, primary_provider="kie", before_kie_submit=handoff)
    assert execute.call_args.kwargs["primary_provider"] == "kie"
    assert execute.call_args.kwargs["request_id"] == rid
    assert execute.call_args.kwargs["before_kie_submit"] is handoff


def test_scheduler_includes_seedream_unknown_and_kie_handoff():
    from sqlalchemy.dialects import postgresql

    from core.neironych_image_reconcile_scheduler import _eligible_query
    sql = str(_eligible_query().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "seedream/5-pro-text-to-image" in sql
    assert "seedream/5-pro-image-to-image" in sql
    assert "kie-submit" in sql


async def test_kie_handoff_occurs_before_paid_post_and_can_fail_closed(monkeypatch):
    events = []
    async def handoff():
        events.append("durable_handoff")
    async def post(*args, **kwargs):
        events.append("kie_post")
        return {"data": {"taskId": "kie-task"}}
    monkeypatch.setattr(adapter, "generate_seedream5_image", AsyncMock(side_effect=adapter.NeironychImageRejected("balance", status_code=402)))
    monkeypatch.setattr(image_service.kieai_client, "create_task", post)
    await image_service.generate_image(MODELS[0], "A cup", primary_provider="neironych", before_kie_submit=handoff)
    assert events == ["durable_handoff", "kie_post"]
    events.clear()
    async def lost_ownership():
        raise RuntimeError("generation finalized")
    with pytest.raises(RuntimeError, match="finalized"):
        await image_service.generate_image(MODELS[0], "A cup", primary_provider="neironych", before_kie_submit=lost_ownership)
    assert events == []



@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("outcome", ["timeout", "503", "invalid"])
async def test_kie_paid_submission_is_one_shot(monkeypatch, model, outcome):
    from api import kieai_client
    requests = []
    monkeypatch.setattr(image_service, "_prepare_reference_urls_for_model", AsyncMock(side_effect=lambda model, refs: refs))
    def respond(request):
        requests.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout("lost response", request=request)
        if outcome == "503":
            return httpx.Response(503, json={"error": "unknown acceptance"})
        return httpx.Response(200, json={"code": 200, "data": {}})
    monkeypatch.setattr(kieai_client, "_maybe_alert_credit_issue", AsyncMock())
    async with httpx.AsyncClient(base_url="https://kie.test", transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(kieai_client, "get_client", lambda: client)
        with pytest.raises(kieai_client.KieSubmissionOutcomeUnknown):
            await image_service.generate_image(
                model, "A cup", image_url="https://example.test/ref.png" if model == MODELS[1] else None,
                primary_provider="kie",
            )
    assert len(requests) == 1


@pytest.mark.parametrize("surface", ["miniapp", "web"])
async def test_signed_kie_callback_binds_only_exact_seedream_handoff(surface, monkeypatch):
    from core.seedream5_recovery import bind_kie_callback
    monkeypatch.setattr("core.seedream5_recovery.canonical_kie_status", AsyncMock(return_value={}))
    from db.models import GenerationStatus, GenerationType
    rid = adapter.client_request_id_for_generation(87)
    prefix = "web:" if surface == "web" else ""
    gen = SimpleNamespace(
        id=87, model=MODELS[1].value, gen_type=GenerationType.image,
        status=GenerationStatus.processing, task_id=prefix + adapter.encode_kie_handoff_id(rid),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: gen)),
        commit=AsyncMock(), rollback=AsyncMock(),
    )
    assert await bind_kie_callback(db, 87, "kie-recovered") is gen
    assert gen.task_id == prefix + "kie-recovered"
    assert await bind_kie_callback(db, 87, "kie-other") is None
    assert gen.task_id == prefix + "kie-recovered"


def test_seedream_budget_cannot_exceed_proxy_deadline():
    from core.config import Settings
    with pytest.raises(ValidationError):
        Settings(BOT_TOKEN="123456:test", COMET_API_KEY="test", SEEDREAM_5_IMAGE_TIMEOUT_SECONDS=120)
    assert adapter.settings.SEEDREAM_5_IMAGE_TIMEOUT_SECONDS <= 110

from unittest.mock import AsyncMock

from api import image_service, neironych_image_adapter, nexus_image_adapter


async def test_gpt2_neironych_primary(monkeypatch):
    monkeypatch.setattr(neironych_image_adapter, '_generate_image', AsyncMock(return_value='https://example.test/result.png'))
    monkeypatch.setattr(nexus_image_adapter, 'create_nexus_image_task', AsyncMock(return_value='nexus:reserve'))
    result=await image_service.generate_image(image_service.ImageModel.GPT_IMAGE_2_T2I, 'Cup',
        aspect_ratio='1:1', quality='2K', primary_provider='neironych',
        request_id='d9307625-cff7-4341-8280-5a778154ccef')
    assert result.provider=='neironych'


def test_gpt25_is_a_separate_image_model():
    assert image_service.ImageModel('gpt-image-2.5-sunburst').name == 'GPT_IMAGE_25'

import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image

from api import neironych_gpt_image as native
from bot.handlers import image_gen
from bot.keyboards.models import IMAGE_CAPS
from db import repository as repo
from db.models import GenerationStatus, GenerationType
from db.seed import derive_gpt25_prices

RID = "d9307625-cff7-4341-8280-5a778154ccef"
URL = "https://example.test/result.png"


@pytest.mark.parametrize("model", list(native.MODELS))
@pytest.mark.parametrize("refs", [[], ["https://example.test/ref.png"]])
@pytest.mark.parametrize("quality,size", [("2K", "2048x1152"), ("4K", "3840x2160")])
async def test_native_http_payload_and_commit_before_post(monkeypatch, model, refs, quality, size):
    if model.endswith("image-to-image") and not refs:
        return
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(image, format="PNG")
    events = []
    saved = []
    async def freeze(rid, snapshot):
        assert rid == RID
        saved.append(snapshot)
        events.append("commit")
    def respond(request):
        events.append("post")
        assert request.url.path == ("/v1/images/edits" if refs else "/v1/images/generations")
        assert request.headers["Idempotency-Key"] == request.headers["X-Client-Request-Id"] == RID
        payload = json.loads(request.content)
        assert payload["model"] == native.MODELS[model]
        assert payload["size"] == size
        assert payload["quality"] == ("high" if quality == "4K" else "medium")
        assert payload.get("images", []) == [{"image_url": ref} for ref in refs]
        assert json.loads(saved[0]["body_json"]) == payload
        assert saved[0]["model_key"] == model
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image.getvalue()).decode()}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(neironych_image_adapter.settings, "NEIRONYCH_API_KEY", "synthetic-key")
    monkeypatch.setattr(neironych_image_adapter.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(neironych_image_adapter, "save_public_file", MagicMock(return_value=URL))
    assert await native.generate(model_key=model, prompt="Cup", image_urls=refs, aspect_ratio="16:9",
                                 quality=quality, request_id=RID, before_submit=freeze) == URL
    assert events == ["commit", "post"]


@pytest.mark.parametrize("model", list(native.MODELS))
async def test_unknown_provider_outcome_never_falls_back(monkeypatch, model):
    fallback = AsyncMock(side_effect=AssertionError("duplicate paid request"))
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    monkeypatch.setattr(native, "generate", AsyncMock(side_effect=neironych_image_adapter.NeironychImageError("timeout")))
    with pytest.raises(neironych_image_adapter.NeironychImageError):
        await image_service.generate_image(image_service.ImageModel(model), "Cup", image_url=["https://example.test/ref.png"],
            aspect_ratio="1:1", quality="2K", primary_provider="neironych", request_id=RID)
    fallback.assert_not_awaited()


@pytest.mark.parametrize("model", list(native.MODELS))
async def test_definite_rejection_uses_only_same_model_reserve(monkeypatch, model):
    monkeypatch.setattr(native, "generate", AsyncMock(side_effect=neironych_image_adapter.NeironychImageRejected("no balance", status_code=402)))
    fallback = AsyncMock(return_value="nexus:accepted")
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    action = image_service.generate_image(image_service.ImageModel(model), "Cup", image_url=["https://example.test/ref.png"],
        aspect_ratio="1:1", quality="2K", primary_provider="neironych", request_id=RID)
    if model == "gpt-image-2.5-sunburst":
        with pytest.raises(neironych_image_adapter.NeironychImageRejected):
            await action
        fallback.assert_not_awaited()
    else:
        assert (await action).provider == "nexus"
        assert fallback.await_args.kwargs["model_key"] == model
        assert fallback.await_args.kwargs["idempotency_key"] == RID


@pytest.mark.parametrize("model", list(native.MODELS))
@pytest.mark.parametrize("entry", ["web", "miniapp", "web_feed", "miniapp_feed", "bot"])
async def test_all_surfaces_freeze_gpt_request_before_paid_post(monkeypatch, model, entry):
    from api import miniapp_routes
    from db.models import ImageGenerationAction
    from tests.test_nano_banana_pro_reference_transport import local_launch

    launch = local_launch.__wrapped__(monkeypatch)
    gen = launch.generation
    gen.model, gen.task_id, gen.input_params = model, None, None
    route = AsyncMock(return_value=SimpleNamespace(primary_provider="neironych"))
    for module in (miniapp_routes, image_gen):
        monkeypatch.setattr(module, "get_gpt2_route", route)
        monkeypatch.setattr(module, "get_gpt25_route", route)
    events = []
    async def mark(db, gid, task_id, **kwargs):
        gen.task_id = task_id
        return True
    async def freeze(db, gid, task_id, saved):
        assert gen.task_id == task_id
        assert saved["model_key"] == model
        gen.input_params = json.dumps({native.SNAPSHOT_KEY: saved})
        events.append("commit")
        return True
    async def post(payload, **kwargs):
        assert payload["model"] == native.MODELS[model]
        saved = json.loads(gen.input_params)[native.SNAPSHOT_KEY]
        assert saved["request_id"] == kwargs["request_id"]
        events.append("post")
        return URL
    async def finish(db, gid, url, **kwargs):
        assert kwargs["expected_task_id"] == gen.task_id
        gen.status, gen.result_url, gen.result_urls = GenerationStatus.done, URL, json.dumps([URL])
        return gen
    monkeypatch.setattr(repo, "update_generation_task", mark)
    monkeypatch.setattr(repo, "persist_neironych_gpt_submission", freeze)
    monkeypatch.setattr(repo, "finish_generation", finish)
    monkeypatch.setattr(repo, "update_image_session_last_result", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", AsyncMock())
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    refs = ["https://example.test/ref.png"]
    if entry.endswith("_feed"):
        await miniapp_routes.remix_feed_post(77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=refs[0], mode="image", aspect_ratio="16:9", quality="4K"),
            session=launch.session, user=launch.user, surface=entry.removesuffix("_feed"))
    elif entry == "bot":
        current = await repo.create_image_session(launch.session, launch.user.id, model, "image", "16:9", "4K", 1, "Cup")
        assert await image_gen._launch_session_generation(source_message=AsyncMock(), state=AsyncMock(),
            session=launch.session, db_user=launch.user, image_session=current, prompt="Cup",
            action_type=ImageGenerationAction.initial, reference_url=refs, parent_generation_id=None,
            launching_text="Starting", queued_text="Queued")
    else:
        await miniapp_routes.create_image_generation(miniapp_routes.ImageGenRequest(
            model=model, prompt="Cup", reference_urls=refs, aspect_ratio="16:9", quality="4K"),
            session=launch.session, user=launch.user, surface=entry)
    assert events == ["commit", "post"]
    repo.charge_image_generation.assert_awaited_once()


def test_gpt25_prices_copy_current_gpt2_without_overwriting_existing():
    source = SimpleNamespace(model_key="gpt-image-2-text-to-image", display_name="GPT Image 2",
                             gen_type=GenerationType.image, credits=7.25, is_active=True)
    high = SimpleNamespace(model_key=source.model_key+"__quality=4K", display_name="GPT Image 2 4K",
                           gen_type=source.gen_type, credits=12.75, is_active=False)
    rows = derive_gpt25_prices([source, high])
    assert [(r["model_key"], r["credits"], r["is_active"]) for r in rows] == [
        ("gpt-image-2.5-sunburst", 7.25, True), ("gpt-image-2.5-sunburst__quality=4K", 12.75, False)]
    existing = SimpleNamespace(model_key="gpt-image-2.5-sunburst", credits=18)
    assert len(derive_gpt25_prices([source, high, existing])) == 1


@pytest.mark.parametrize("model", list(native.MODELS))
async def test_gpt_submission_admission_is_single_use(monkeypatch, model):
    gen = SimpleNamespace(model=model, gen_type=GenerationType.image, status=GenerationStatus.processing,
        task_id=neironych_image_adapter.encode_task_id(RID), input_params=json.dumps({"hidden_prompt": True}))
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: gen)), commit=AsyncMock())
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    payload = native.build_payload(model_key=model, prompt="Cup", image_urls=["https://example.test/ref.png"], aspect_ratio="1:1", quality="2K")
    saved = native.snapshot(payload, RID, model_key=model)
    assert await repo.persist_neironych_gpt_submission(db, 1, gen.task_id, saved)
    assert not await repo.persist_neironych_gpt_submission(db, 1, gen.task_id, saved)
    assert json.loads(gen.input_params)["hidden_prompt"] is True


@pytest.mark.parametrize("mutation", ["body", "scope", "model", "key", "endpoint"])
async def test_gpt_recovery_rejects_changed_original_submission(monkeypatch, mutation):
    model = "gpt-image-2.5-sunburst"
    payload = native.build_payload(model_key=model, prompt="Cup", image_urls=[], aspect_ratio="16:9", quality="4K")
    saved = native.snapshot(payload, RID, model_key=model)
    saved[{"body":"body_json", "scope":"credential_scope", "model":"model_key", "key":"request_id", "endpoint":"endpoint"}[mutation]] = "changed"
    post = AsyncMock()
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    with pytest.raises(ValueError):
        await native.recover_completed(saved, RID, model_key=model)
    post.assert_not_awaited()


def test_gpt25_public_capabilities_and_label():
    from bot.ui.model_labels import model_display_name
    caps = IMAGE_CAPS[image_service.ImageModel.GPT_IMAGE_25]
    assert caps["modes"] == ["text", "image"]
    assert caps["max_refs"] == 4
    assert caps["has_quality"]
    assert "GPT Image 2.5" in model_display_name("gpt-image-2.5-sunburst")
    assert "neironych" not in model_display_name("gpt-image-2.5-sunburst").lower()


@pytest.mark.parametrize("model", list(native.MODELS))
async def test_completed_response_replay_preserves_body_key_and_model(monkeypatch, model):
    payload = native.build_payload(model_key=model, prompt="Original", image_urls=["https://example.test/ref.png"],
                                   aspect_ratio="16:9", quality="4K")
    saved = native.snapshot(payload, RID, model_key=model)
    post = AsyncMock(return_value=URL)
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    assert await native.recover_completed(saved, RID, model_key=model) == URL
    assert post.await_args.args[0] == payload
    assert post.await_args.kwargs["request_id"] == RID
    assert post.await_args.kwargs["subdir"] == native.MODELS[model]


async def test_gpt2_route_is_audited_and_admin_only(monkeypatch):
    from api.web import admin as web_admin
    from bot.handlers import admin as bot_admin
    from core import provider_routing
    monkeypatch.setattr(web_admin.settings, "ADMIN_IDS", [42])
    request = web_admin.Nano21ProviderRoutingUpdate(primary_provider="neironych")
    assert (await web_admin.admin_get_gpt2_provider(session=object(), user=None)).status_code == 401
    assert (await web_admin.admin_set_gpt2_provider(body=request, session=object(), user=SimpleNamespace(tg_id=7))).status_code == 403
    row = SimpleNamespace(primary_provider="nexus", updated_by_admin_tg_id=42)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None, SimpleNamespace(scalar_one=lambda: row)]),
                              add=MagicMock(), commit=AsyncMock())
    await provider_routing.set_gpt2_route(session, "neironych", admin_tg_id=42, source="web")
    audit = session.add.call_args.args[0]
    assert (audit.model_key, audit.previous_provider, audit.new_provider) == ("gpt-image-2", "nexus", "neironych")
    assert "adm:gpt2_route" in {b.callback_data for r in bot_admin.admin_menu_kb().inline_keyboard for b in r}


async def test_gpt25_appears_in_website_and_miniapp_catalogs(monkeypatch):
    from api import miniapp_routes
    from api.web import models as web_models
    cost = SimpleNamespace(id=777, model_key="gpt-image-2.5-sunburst", display_name="GPT Image 2.5",
                           credits=7.25, is_active=True, gen_type=GenerationType.image)
    monkeypatch.setattr(repo, "get_all_model_costs", AsyncMock(return_value=[cost]))
    monkeypatch.setattr(miniapp_routes, "_resolve_image_quality_prices", AsyncMock(return_value={"2K": 7.25, "4K": 12.75}))
    models = await miniapp_routes.list_image_models(session=object(), user=SimpleNamespace(id=1))
    assert models[0].key == "gpt-image-2.5-sunburst"
    assert models[0].max_refs == 4
    assert models[0].modes == ["text", "image"]
    response = await web_models.models(session=object())
    assert response["data"]["image"][0]["model_key"] == "gpt-image-2.5-sunburst"


def test_native_gpt_models_are_in_reconciliation_scheduler():
    from core.neironych_image_reconcile_scheduler import _eligible_query
    sql = str(_eligible_query().compile(compile_kwargs={"literal_binds": True}))
    for model in native.MODELS:
        assert "'" + model + "'" in sql


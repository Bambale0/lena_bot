"""VIP commercial identities must share native family routes without losing billing fences."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import (
    image_service,
    miniapp_routes,
    neironych_gpt_image,
    neironych_image_adapter,
    neironych_nano_pro_runtime,
    nexus_image_adapter,
)
from bot.handlers import image_gen
from core import provider_routing
from db import repository as repo
from db.models import GenerationStatus, ImageGenerationAction
from tests.test_nano_banana_pro_reference_transport import local_launch

RID = "d9307625-cff7-4341-8280-5a778154ccef"
URL = "https://example.test/result.png"
VIP_MODELS = ["nano-banana-pro-vip", "gpt-image-2-vip"]


@pytest.mark.parametrize("model,refs", [(VIP_MODELS[0], 14), (VIP_MODELS[1], 4)])
async def test_vip_primary_maps_only_the_provider_model_and_preserves_all_references(monkeypatch, model, refs):
    post = AsyncMock(return_value=URL)
    fallback = AsyncMock(side_effect=AssertionError("unexpected reserve"))
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    freeze = AsyncMock()
    images = [f"https://example.test/{i}.png" for i in range(refs)]
    result = await image_service.generate_image(image_service.ImageModel(model), "Cup", image_url=images,
        aspect_ratio="1:1", quality="basic", primary_provider="neironych", request_id=RID, before_neironych_submit=freeze)
    assert result.provider == "neironych"
    payload = post.await_args.args[0]
    assert payload["model"] == model.removesuffix("-vip")
    assert payload["images"] == [{"image_url": url} for url in images]
    assert freeze.await_args.args[1]["model_key"] == model
    assert post.await_args.kwargs["request_id"] == RID
    fallback.assert_not_awaited()


@pytest.mark.parametrize("model", VIP_MODELS)
@pytest.mark.parametrize("entry", ["web", "miniapp", "web_feed", "miniapp_feed", "bot"])
async def test_vip_family_route_and_durable_admission_on_all_surfaces(monkeypatch, model, entry):
    launch = local_launch.__wrapped__(monkeypatch)
    gen = launch.generation
    gen.model, gen.task_id, gen.input_params = model, None, None
    family = "get_nano_pro_route" if model == VIP_MODELS[0] else "get_gpt2_route"
    route = AsyncMock(return_value=SimpleNamespace(primary_provider="neironych"))
    for module in (miniapp_routes, image_gen):
        monkeypatch.setattr(module, family, route)
    events = []
    async def mark(db, gid, task_id, **kwargs):
        gen.task_id = task_id
        return True
    async def freeze(db, gid, task_id, saved):
        assert task_id == gen.task_id and saved["model_key"] == model
        events.append("commit")
        return True
    async def post(payload, **kwargs):
        assert events == ["commit"]
        assert payload["model"] == model.removesuffix("-vip")
        events.append("post")
        return URL
    async def finish(db, gid, url, **kwargs):
        assert kwargs["expected_task_id"] == gen.task_id
        gen.status, gen.result_url, gen.result_urls = GenerationStatus.done, URL, json.dumps([URL])
        return gen
    monkeypatch.setattr(repo, "update_generation_task", mark)
    monkeypatch.setattr(repo, "persist_neironych_nano_pro_submission" if model == VIP_MODELS[0] else "persist_neironych_gpt_submission", freeze)
    monkeypatch.setattr(repo, "finish_generation", finish)
    monkeypatch.setattr(repo, "update_image_session_last_result", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_notify_direct_image_result_in_bot", AsyncMock())
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    refs = [f"https://example.test/{i}.png" for i in range(14 if model == VIP_MODELS[0] else 4)]
    if entry.endswith("_feed"):
        await miniapp_routes.remix_feed_post(77, miniapp_routes.FeedRemixRequest(
            model=model, image_url=refs[0], reference_urls=refs[1:], mode="image", aspect_ratio="16:9", quality="2K"),
            session=launch.session, user=launch.user, surface=entry.removesuffix("_feed"))
    elif entry == "bot":
        current = await repo.create_image_session(launch.session, launch.user.id, model, "image", "16:9", "basic", 1, "Cup")
        assert await image_gen._launch_session_generation(source_message=AsyncMock(), state=AsyncMock(),
            session=launch.session, db_user=launch.user, image_session=current, prompt="Cup",
            action_type=ImageGenerationAction.initial, reference_url=refs, parent_generation_id=None,
            launching_text="Starting", queued_text="Queued")
    else:
        await miniapp_routes.create_image_generation(miniapp_routes.ImageGenRequest(
            model=model, prompt="Cup", reference_urls=refs, aspect_ratio="16:9", quality="2K"),
            session=launch.session, user=launch.user, surface=entry)
    assert events == ["commit", "post"]
    route.assert_awaited_once()
    repo.charge_image_generation.assert_awaited_once()


@pytest.mark.parametrize("model", VIP_MODELS)
@pytest.mark.parametrize("error", [neironych_image_adapter.NeironychImageError("timeout"), neironych_image_adapter.NeironychImageError("server", status_code=503)])
async def test_vip_unknown_outcome_never_creates_a_second_paid_request(monkeypatch, model, error):
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", AsyncMock(side_effect=error))
    fallback = AsyncMock(side_effect=AssertionError("duplicate paid generation"))
    monkeypatch.setattr(nexus_image_adapter, "create_nexus_image_task", fallback)
    with pytest.raises(neironych_image_adapter.NeironychImageError):
        await image_service.generate_image(image_service.ImageModel(model), "Cup", aspect_ratio="1:1", quality="2K",
            primary_provider="neironych", request_id=RID)
    fallback.assert_not_awaited()


@pytest.mark.parametrize("model", VIP_MODELS)
async def test_vip_nexus_reserve_keeps_signed_callback_and_public_identity(monkeypatch, model):
    create = AsyncMock(return_value=SimpleNamespace(task_id="accepted"))
    monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: SimpleNamespace(create_params=create, base_url="https://nexus.test", api_key="synthetic"))
    saved = AsyncMock()
    await nexus_image_adapter.create_nexus_image_task(model_key=model, prompt="Cup", aspect_ratio="auto",
        idempotency_key=RID, before_submit=saved)
    params = create.await_args.args[0]
    assert params["model_name"] == model
    assert "nexus_request_id=" + RID in params["webhook_url"]
    assert "nexus_signature=" in params["webhook_url"]
    saved.assert_awaited_once()


@pytest.mark.parametrize("model", VIP_MODELS)
async def test_vip_reconciliation_checks_canonical_model_and_reads_frozen_response(monkeypatch, model):
    adapter = neironych_nano_pro_runtime if model == VIP_MODELS[0] else neironych_gpt_image
    gen = SimpleNamespace(id=12, user_id=7, model=model, task_id=neironych_image_adapter.encode_task_id(RID),
        image_session_id=None, created_at=datetime.now(timezone.utc), status=GenerationStatus.processing,
        input_params=json.dumps({adapter.SNAPSHOT_KEY: {"original": True}}), result_url=URL, result_urls=json.dumps([URL]))
    status = AsyncMock(return_value={"status": "completed", "result_url": None})
    replay = AsyncMock(return_value=URL)
    monkeypatch.setattr(neironych_image_adapter, "fetch_nano_banana21_status", status)
    monkeypatch.setattr(adapter, "recover_completed", replay)
    monkeypatch.setattr(repo, "finish_generation", AsyncMock(return_value=None))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=None))
    await miniapp_routes._reconcile_neironych_image_generation(object(), gen, RID)
    status.assert_awaited_once_with(RID, expected_model=model.removesuffix("-vip"))
    replay.assert_awaited_once_with({"original": True}, RID, model_key=model)


def test_vip_aliases_are_in_shared_routes_and_background_reconciliation():
    from core.neironych_image_reconcile_scheduler import _eligible_query
    sql = str(_eligible_query().compile(compile_kwargs={"literal_binds": True}))
    for model in VIP_MODELS:
        assert "'" + model + "'" in sql
    assert VIP_MODELS[0] in provider_routing.NANO_PRO_MODELS
    assert VIP_MODELS[1] in provider_routing.GPT_IMAGE_MODELS


async def test_nano_vip_snapshot_fences_public_identity_and_preserves_exact_replay(monkeypatch):
    from db.models import GenerationType
    model = VIP_MODELS[0]
    payload = neironych_nano_pro_runtime.build_payload(prompt="Original", image_urls=[f"https://example.test/{i}.png" for i in range(14)], aspect_ratio="3:2", quality="1K")
    saved = neironych_nano_pro_runtime.snapshot(payload, RID, model_key=model)
    gen = SimpleNamespace(model=model, gen_type=GenerationType.image, status=GenerationStatus.processing,
        task_id=neironych_image_adapter.encode_task_id(RID), input_params=json.dumps({"hidden_prompt": True}))
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: gen)), commit=AsyncMock())
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    canonical_saved = neironych_nano_pro_runtime.snapshot(payload, RID)
    assert not await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, canonical_saved)
    assert await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, saved)
    assert not await repo.persist_neironych_nano_pro_submission(db, 1, gen.task_id, saved)
    assert json.loads(gen.input_params)["hidden_prompt"] is True
    post = AsyncMock(return_value=URL)
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    assert await neironych_nano_pro_runtime.recover_completed(saved, RID, model_key=model) == URL
    assert post.await_args.args[0] == payload
    assert post.await_args.kwargs["request_id"] == RID
    post.reset_mock()
    with pytest.raises(ValueError):
        await neironych_nano_pro_runtime.recover_completed(saved, RID)
    post.assert_not_awaited()


@pytest.mark.parametrize("ratio", ["3:2", "2:3", "5:4", "4:5"])
async def test_nano_explicit_provider_ratios_use_neironych(monkeypatch, ratio):
    post = AsyncMock(return_value=URL)
    monkeypatch.setattr(neironych_image_adapter, "_generate_image", post)
    result = await image_service.generate_image(image_service.ImageModel(VIP_MODELS[0]), "Cup",
        aspect_ratio=ratio, quality="2K", primary_provider="neironych", request_id=RID)
    assert result.provider == "neironych"
    assert post.await_args.args[0]["aspect_ratio"] == ratio

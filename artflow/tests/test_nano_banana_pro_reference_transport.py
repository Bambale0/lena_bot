"""Reference preservation through real Pro adapters; all HTTP is intercepted."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from api import image_service, miniapp_routes, nexus_image_adapter
from api.image_service import ImageModel
from api.nexusapi_client import NexusApiClient
from bot.handlers import image_gen
from db import repository as repo
from db.models import GenerationStatus, GenerationType, ImageSession

REFS = [f"https://example.test/person-{index}.jpg" for index in range(1, 4)]
SOURCE = "https://example.test/public-scene.jpg"
SECRET = "private-author-text-never-disclosed"


@pytest.fixture
async def nexus_posts(monkeypatch):
    posts = []

    def capture(request):
        assert request.method == "POST"
        assert str(request.url) == "https://nexus.test/generate"
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"task_id": "synthetic-task", "status": "pending"})

    async with httpx.AsyncClient(
        base_url="https://nexus.test", transport=httpx.MockTransport(capture),
    ) as http:
        client = NexusApiClient(api_key="synthetic-test-only", base_url="https://nexus.test", client=http)
        monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
        for module, method in [
            (image_service.kieai_client, "create_task"),
            (image_service.comet_fallback, "generate_image"),
            (image_service.neironych_image_adapter, "generate_nano_banana21_image"),
        ]:
            monkeypatch.setattr(module, method, AsyncMock(side_effect=AssertionError("Pro must stay on Nexus")))
        yield posts


@pytest.fixture
def local_launch(monkeypatch):
    created_sessions = []
    generation = SimpleNamespace(
        id=99, user_id=42, gen_type=GenerationType.image, model="nano-banana-pro", prompt="own prompt",
        status=GenerationStatus.processing, result_url=None, result_urls=None, credits_spent=4,
        created_at=datetime.now(timezone.utc), finished_at=None, is_public_feed=False,
        is_prompt_library=False, source_feed_gen_id=None, image_session_id=7,
    )
    source = SimpleNamespace(
        id=77, user_id=100, gen_type=GenerationType.image, model="nano-banana-pro", prompt=SECRET,
        result_url=SOURCE, result_urls=None, is_public_feed=True,
    )
    for name, value in {
        "archive_active_image_sessions": AsyncMock(),
        "get_public_feed_generation": AsyncMock(return_value=source),
        "get_generation_by_id": AsyncMock(return_value=generation),
        "resolve_image_model_cost": AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
        "get_model_cost": AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
        "has_unlimited_image_model": AsyncMock(return_value=False),
        "count_user_active_generations": AsyncMock(return_value=0),
        "charge_image_generation": AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=4)),
        "create_generation": AsyncMock(return_value=generation),
        "update_image_session_last_prompt": AsyncMock(),
        "update_generation_task": AsyncMock(),
        "increment_feed_share": AsyncMock(),
    }.items():
        monkeypatch.setattr(repo, name, value)
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(image_gen, "safe_answer_callback", AsyncMock())
    session = AsyncMock()
    session.add = MagicMock(side_effect=created_sessions.append)

    async def refresh(obj):
        if isinstance(obj, ImageSession):
            obj.id = 7 + len(created_sessions)

    session.refresh = AsyncMock(side_effect=refresh)
    return SimpleNamespace(
        session=session, user=SimpleNamespace(id=42, credits=100, tg_id=777),
        created_sessions=created_sessions, source=source, generation=generation,
    )


@pytest.mark.parametrize("refs", [[], REFS[:1], REFS, REFS + [SOURCE]])
async def test_pro_real_serialized_post_preserves_direct_references(nexus_posts, refs):
    result = await image_service.generate_image(
        ImageModel.NANO_BANANA_PRO, "own prompt", image_url=refs, aspect_ratio="9:16", quality="2K",
    )
    assert result.task_id == "nexus:synthetic-task"
    assert nexus_posts[0]["params"].get("image_urls", []) == refs
    assert nexus_posts[0]["params"]["model_name"] == "nano-banana-pro"


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_pro_web_references_survive_telegram_repeat(local_launch, nexus_posts, monkeypatch, surface):
    launch = local_launch
    await miniapp_routes.create_image_generation(
        miniapp_routes.ImageGenRequest(model="nano-banana-pro", prompt="own prompt", reference_urls=REFS),
        session=launch.session, user=launch.user, surface=surface,
    )
    image_session = launch.created_sessions[0]
    assert json.loads(image_session.reference_urls) == REFS
    assert nexus_posts[0]["params"]["image_urls"] == REFS
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(image_session, 99)))
    state = AsyncMock()
    state.get_data.return_value = {"pending_image_prompt": "own prompt", "image_session_id": image_session.id}
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, AsyncMock())
    assert len(nexus_posts) == 2
    assert nexus_posts[1]["params"]["model_name"] == "nano-banana-pro"
    assert nexus_posts[1]["params"]["image_urls"] == REFS


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_pro_four_refs_in_actual_browser_request_reach_nexus(local_launch, nexus_posts, surface):
    refs = REFS + [SOURCE]
    await miniapp_routes.create_image_generation(
        miniapp_routes.ImageGenRequest(
            model="nano-banana-pro", prompt="own prompt", reference_url=refs[0], reference_urls=refs,
        ),
        session=local_launch.session, user=local_launch.user, surface=surface,
    )
    assert nexus_posts[0]["params"]["image_urls"] == refs
    assert json.loads(local_launch.created_sessions[0].reference_urls) == refs


@pytest.mark.parametrize("entrypoint", ["regen", "feed_again", "result_action"])
async def test_pro_session_clone_preserves_public_reference_list(local_launch, nexus_posts, monkeypatch, entrypoint):
    from bot.handlers import feed

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    launch.generation.image_session_id = old.id
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(None, None)))
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock())
    state = AsyncMock()
    state.get_data.return_value = {}
    if entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, AsyncMock())
    elif entrypoint == "feed_again":
        call.data = "feed:again:99"
        await feed.cb_feed_again(call, launch.session, launch.user, state, AsyncMock())
    else:
        await image_gen._image_session_for_result_action(call, launch.session, state, launch.user, launch.generation)
    copied = launch.created_sessions[-1]
    assert copied is not old
    assert json.loads(copied.reference_urls) == REFS
    resolved = await image_gen._session_reference_url(AsyncMock(), copied)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "own prompt", image_url=resolved)
    assert nexus_posts[-1]["params"]["image_urls"] == REFS


async def test_pro_model_switch_carries_all_public_refs_to_next_post(local_launch, nexus_posts, monkeypatch):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, None)))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    data = {}
    state = AsyncMock()
    state.get_data.side_effect = lambda: dict(data)
    state.clear.side_effect = data.clear

    async def update(**values):
        data.update(values)
    state.update_data.side_effect = update
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_wizard_v2.open_model_composer_for_selection(call, state, launch.session, "nano-banana-pro")
    copied = await image_gen._ensure_active_image_session_from_state(
        session=launch.session, state=state, db_user=launch.user,
    )
    resolved = await image_gen._session_reference_url(AsyncMock(), copied, state=state)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "own prompt", image_url=resolved)
    assert nexus_posts[-1]["params"]["image_urls"] == REFS


@pytest.mark.parametrize("file_ids", [[], ["new-telegram-photo"]])
async def test_replacing_telegram_references_clears_persisted_public_set(local_launch, file_ids):
    await repo.update_image_session_references(local_launch.session, 8, file_ids, mode="image")
    values = local_launch.session.execute.await_args.args[0].compile().params
    assert values["reference_url"] is None
    assert values.get("reference_urls", "not-cleared") is None


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_pro_five_distinct_browser_refs_fail_before_charge(local_launch, nexus_posts, surface):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await miniapp_routes.create_image_generation(
            miniapp_routes.ImageGenRequest(
                model="nano-banana-pro", prompt="own prompt", reference_url=REFS[0],
                reference_urls=REFS + [SOURCE, "https://example.test/extra.jpg"],
            ),
            session=local_launch.session, user=local_launch.user, surface=surface,
        )
    assert error.value.status_code == 422
    assert nexus_posts == []
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("surface", ["web", "miniapp"])
async def test_pro_feed_repeat_serializes_user_first_source_last_without_author_prompt(local_launch, nexus_posts, surface):
    launch = local_launch
    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model="nano-banana-pro", image_url=REFS[0], reference_urls=REFS[1:],
            mode="image", quality="2K", aspect_ratio="9:16",
        ),
        session=launch.session, user=launch.user, surface=surface,
    )
    assert nexus_posts[0]["params"]["model_name"] == "nano-banana-pro"
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
    assert SECRET not in nexus_posts[0]["params"]["prompt"]
    assert SECRET not in str(result)


def mutable_state(initial=None):
    data = dict(initial or {})
    state = AsyncMock()
    state.get_data.side_effect = lambda: dict(data)
    state.clear.side_effect = data.clear

    async def update(**values):
        data.update(values)
    state.update_data.side_effect = update
    return state, data


@pytest.mark.parametrize("action", ["skip", "new", "remix", "style"])
async def test_public_reference_state_is_cleared_when_replaced(local_launch, monkeypatch, action):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    launch.generation.result_url = SOURCE
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, 99)))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    state, data = mutable_state({
        "model_key": "nano-banana-pro", "reference_urls": REFS, "carryover_reference_urls": REFS,
        "carryover_reference_url": REFS[0], "reference_url": REFS[0],
    })
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_session:remix:99")
    if action == "skip":
        await image_gen.cb_image_reference_skip(call, state, launch.session, launch.user)
    elif action == "new":
        await image_gen._show_nana_banano_flow(call, state, launch.session, launch.user, preserve_refs=False)
    elif action == "remix":
        await image_gen.cb_image_session_remix(call, launch.session, state, launch.user)
    else:
        call.data = "img_style:hair_color:99"
        await image_gen.cb_image_style_choice(call, launch.session, state, launch.user)
    assert image_gen._state_reference_urls(data) == []
    assert data.get("carryover_reference_urls") == []
    if action in {"remix", "style"}:
        assert image_gen._state_reference_url(data) == SOURCE
    else:
        assert image_gen._state_reference_url(data) is None


async def test_switching_to_lower_cap_model_does_not_silently_discard_public_refs(local_launch, monkeypatch):
    from bot.handlers import image_wizard_v2

    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    state, data = mutable_state({"model_key": "nano-banana-pro", "reference_urls": REFS})
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    opened = await image_wizard_v2.open_model_composer_for_selection(
        call, state, local_launch.session, "qwen/image-edit",
    )
    assert opened is False
    assert data["reference_urls"] == REFS
    assert data["model_key"] == "nano-banana-pro"


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("add_photo", [False, True])
async def test_pro_legacy_reference_confirmation_persists_full_set(local_launch, nexus_posts, monkeypatch, reuse, add_photo):
    from bot.handlers import repeat_references

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=SOURCE))
    monkeypatch.setattr(repeat_references, "safe_answer_callback", AsyncMock())
    state, _ = mutable_state({
        "repeat_generation_id": 99, "repeat_model_key": "nano-banana-pro", "repeat_prompt": "own prompt",
        "repeat_max_refs": 4, "repeat_base_reference_urls": REFS, "repeat_source_reference_url": REFS[0],
        "repeat_new_reference_file_ids": ["new-photo"] if add_photo else [],
        "repeat_reuse_session_id": old.id if reuse else None,
    })
    await repeat_references._repeat_refs_run(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), launch.session, state, launch.user, AsyncMock(),
    )
    expected = REFS + ([SOURCE] if add_photo else [])
    assert nexus_posts[0]["params"]["image_urls"] == expected
    copied = launch.created_sessions[-1]
    resolved = await image_gen._session_reference_url(AsyncMock(), copied)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "own prompt", image_url=resolved)
    assert nexus_posts[-1]["params"]["image_urls"] == expected


async def test_pro_protected_feed_clone_keeps_order_and_excludes_author_prompt(local_launch, nexus_posts, monkeypatch):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        None, reference_urls=REFS + [SOURCE],
    )
    launch.generation.image_session_id = old.id
    launch.generation.source_feed_gen_id = 77
    launch.generation.prompt = SECRET
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation,
    ))
    await image_gen.cb_regen_image(
        SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock()),
        launch.session, mutable_state()[0], launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
    assert SECRET not in nexus_posts[0]["params"]["prompt"]
    assert SECRET not in repo.create_generation.await_args.args[4]
    assert launch.created_sessions[-1].base_prompt is None


async def test_pro_telegram_file_references_keep_order_through_real_post(local_launch, nexus_posts, monkeypatch):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_file_ids=["file-1", "file-2", "file-3"],
    )
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(side_effect=REFS))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, 99)))
    state, _ = mutable_state({"pending_image_prompt": "own prompt", "image_session_id": old.id})
    await image_gen.cb_image_repeat_launch(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), launch.session, state, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS


async def test_pro_safe_confirmation_uses_generation_reference_snapshot(local_launch, nexus_posts, monkeypatch):
    from bot.handlers import repeat_safe

    launch = local_launch
    launch.generation.input_params = json.dumps({"reference_images": REFS})
    launch.generation.image_session_id = None
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=launch.generation))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda _user: False)
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())
    state, data = mutable_state()
    call = SimpleNamespace(data="repeat_image_img_99", from_user=SimpleNamespace(id=777), message=AsyncMock(), answer=AsyncMock())
    await repeat_safe.open_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert data["repeat_reference_images"] == REFS
    assert nexus_posts == []
    await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, AsyncMock())
    assert nexus_posts[0]["params"]["image_urls"] == REFS

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
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
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
async def test_pro_feed_repeat_serializes_creator_prompt_with_reader_refs_only(local_launch, nexus_posts, surface):
    launch = local_launch
    result = await miniapp_routes.remix_feed_post(
        77, miniapp_routes.FeedRemixRequest(
            model="nano-banana-pro", image_url=REFS[0], reference_urls=REFS[1:],
            mode="image", quality="2K", aspect_ratio="9:16",
        ),
        session=launch.session, user=launch.user, surface=surface,
    )
    assert nexus_posts[0]["params"]["model_name"] == "nano-banana-pro"
    assert nexus_posts[0]["params"]["image_urls"] == REFS
    assert SECRET in nexus_posts[0]["params"]["prompt"]
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
        "carryover_ref_file_ids": ["stale-file"], "carryover_image_file_id": "stale-file",
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
    assert data.get("carryover_ref_file_ids") == []
    assert data.get("carryover_image_file_id") is None
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


async def test_pro_protected_feed_clone_sends_creator_prompt_and_reader_refs(local_launch, nexus_posts, monkeypatch):
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
    assert nexus_posts[0]["params"]["image_urls"] == REFS
    assert SECRET in nexus_posts[0]["params"]["prompt"]
    assert SECRET in repo.create_generation.await_args.args[4]
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


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("protected", [False, True])
async def test_pro_existing_mixed_session_keeps_public_and_telegram_refs_through_repeats(
    local_launch, nexus_posts, monkeypatch, reuse, protected,
):
    from bot.handlers import repeat_references

    launch = local_launch
    # A legacy session can store the original public references alongside later
    # Telegram uploads. Enter through the real collection resolver, not seeded FSM URLs.
    public_refs = [REFS[0], SOURCE] if protected else [REFS[0]]
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        None if protected else "own prompt", reference_urls=public_refs,
        reference_file_ids=["saved-photo-2", "saved-photo-3"],
    )
    launch.generation.image_session_id = old.id
    if protected:
        launch.generation.source_feed_gen_id = 77
        launch.generation.prompt = SECRET
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(
        side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation,
    ))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"saved-photo-2": REFS[1], "saved-photo-3": REFS[2]}[fid],
    ))
    monkeypatch.setattr(repeat_references, "safe_answer_callback", AsyncMock())
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    handled = await repeat_references._begin_repeat_collection(
        call=call, state=state, bot=AsyncMock(), session=launch.session, db_user=launch.user, generation=launch.generation,
        source_session=old, reuse_session=reuse, source_feed_gen_id=77 if protected else None,
    )
    assert handled is True
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    expected = REFS
    assert nexus_posts[0]["params"]["image_urls"] == expected
    assert (SECRET in nexus_posts[0]["params"]["prompt"]) is protected
    copied = launch.created_sessions[-1]
    assert not copied.reference_file_ids  # Mixed sets persist as one ordered URL list.
    assert set(json.loads(copied.reference_urls)) == set(expected)
    # Re-enter the real collection flow using the newly persisted session.
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=copied))
    await repeat_references._begin_repeat_collection(
        call=call, state=state, bot=AsyncMock(), session=launch.session, db_user=launch.user, generation=launch.generation,
        source_session=copied, reuse_session=True, source_feed_gen_id=77 if protected else None,
    )
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert nexus_posts[1]["params"]["image_urls"] == expected
    assert (SECRET in nexus_posts[1]["params"]["prompt"]) is protected


@pytest.mark.parametrize("state_kind", ["synced", "replacement", "other_session"])
async def test_pro_mixed_session_resolution_respects_reference_replacement(
    local_launch, nexus_posts, monkeypatch, state_kind,
):
    old = await repo.create_image_session(
        local_launch.session, local_launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:1], reference_file_ids=["saved-photo"],
    )
    state_ids = ["saved-photo"] if state_kind == "synced" else ["new-photo"]
    state, _ = mutable_state({
        "image_session_id": old.id if state_kind != "other_session" else old.id + 100,
        "ref_file_ids": state_ids,
    })
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"saved-photo": REFS[1], "new-photo": REFS[2]}[fid],
    ))
    resolved = await image_gen._session_reference_url(AsyncMock(), old, state=state)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "own prompt", image_url=resolved)
    expected = [REFS[2]] if state_kind == "replacement" else REFS[:2]
    assert nexus_posts[0]["params"]["image_urls"] == expected


async def test_pro_mixed_session_deduplicates_public_and_file_alias(local_launch, nexus_posts, monkeypatch):
    old = await repo.create_image_session(
        local_launch.session, local_launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:2], reference_file_id="same-photo",
    )
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[0]))
    resolved = await image_gen._session_reference_url(AsyncMock(), old)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "own prompt", image_url=resolved)
    assert nexus_posts[0]["params"]["image_urls"] == REFS[:2]


async def test_pro_existing_mixed_overflow_never_truncates_before_paid_post(local_launch, nexus_posts, monkeypatch):
    from bot.handlers import repeat_references

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS, reference_file_ids=["extra-1", "extra-2"],
    )
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: f"https://example.test/{fid}.jpg",
    ))
    monkeypatch.setattr(repeat_references, "safe_answer_callback", AsyncMock())
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    await repeat_references._begin_repeat_collection(
        call=call, state=state, bot=AsyncMock(), session=launch.session, db_user=launch.user, generation=launch.generation,
        source_session=old, reuse_session=False, source_feed_gen_id=None,
    )
    assert len(data["repeat_base_reference_urls"]) == 5
    await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
    assert nexus_posts == []
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("selected_model", ["nano-banana-pro", "nano-banana-2"])
async def test_actual_model_reselection_preserves_mixed_refs_through_review_post(
    local_launch, nexus_posts, monkeypatch, selected_model,
):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:2], reference_file_ids=["file-3", "file-4"],
    )
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, None)))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"file-3": REFS[2], "file-4": SOURCE}[fid],
    ))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data=f"img_model:{selected_model}")
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_gen.cb_image_model(call, state, launch.session, launch.user)
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()),
        state, launch.session, launch.user, AsyncMock(),
    )
    # Reuse the actual session just created by handle_prompt for review submission.
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["model_name"] == selected_model
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
    assert json.loads(current.reference_urls) == REFS[:2]


@pytest.mark.parametrize("entrypoint", ["active_prompt", "active_repeat"])
async def test_actual_active_launch_rejects_mixed_overflow_before_accounting(
    local_launch, nexus_posts, monkeypatch, entrypoint,
):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS, reference_file_ids=["extra-1", "extra-2"],
    )
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, None)))
    monkeypatch.setattr(repo, "fail_generation_and_refund", AsyncMock(return_value=(True, 4)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: f"https://example.test/{fid}.jpg",
    ))
    state, _ = mutable_state({"pending_image_prompt": "own prompt"})
    if entrypoint == "active_prompt":
        await image_gen.handle_session_prompt(
            SimpleNamespace(text="own prompt", answer=AsyncMock()), state,
            launch.session, launch.user, AsyncMock(),
        )
    else:
        await image_gen.cb_image_repeat_launch(
            SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), launch.session,
            state, launch.user, AsyncMock(),
        )
    assert nexus_posts == []
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    repo.fail_generation_and_refund.assert_not_awaited()


@pytest.mark.parametrize("public_refs", [[], REFS[:2]])
async def test_reopening_active_composer_keeps_complete_reference_set(local_launch, nexus_posts, monkeypatch, public_refs):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=public_refs, reference_file_id="file-3", reference_file_ids=["file-3", "file-4"],
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr("bot.ui.router.render_screen", AsyncMock(return_value=SimpleNamespace(text="active", reply_markup=None)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"file-3": REFS[2], "file-4": SOURCE}[fid],
    ))
    state, _ = mutable_state()
    await image_wizard_v2.open_image_composer(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), state, launch.session, launch.user,
    )
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == public_refs + [REFS[2], SOURCE]


@pytest.mark.parametrize("alias", [False, True])
async def test_actual_model_selection_validates_resolved_mixed_cap_without_truncation(local_launch, nexus_posts, monkeypatch, alias):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro-vip", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS, reference_file_id="file-a", reference_file_ids=["file-a", "file-b"],
    )
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, None)))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {
            "file-a": REFS[0] if alias else "https://example.test/distinct-fifth.jpg", "file-b": SOURCE,
        }[fid],
    ))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_model:nano-banana-pro", bot=AsyncMock())
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_gen.cb_image_model(call, state, launch.session, launch.user)
    if not alias:
        assert data.get("model_key") != "nano-banana-pro"
        assert data["carryover_reference_urls"] == REFS
        assert data["carryover_ref_file_ids"] == ["file-a", "file-b"]
        assert len(launch.created_sessions) == 1
        repo.charge_image_generation.assert_not_awaited()
        assert nexus_posts == []
        return
    assert data["model_key"] == "nano-banana-pro"
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()),
        state, launch.session, launch.user, call.bot,
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=launch.created_sessions[-1]))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
    repo.charge_image_generation.assert_awaited_once()


@pytest.mark.parametrize("existing_files", [[], ["file-3"]])
async def test_active_photo_add_preserves_public_and_file_inputs(local_launch, nexus_posts, monkeypatch, existing_files):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:2], reference_file_id=existing_files[0] if existing_files else None,
        reference_file_ids=existing_files,
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr("bot.ui.router.render_screen", AsyncMock(return_value=SimpleNamespace(text="active", reply_markup=None)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"file-3": REFS[2], "new-file": SOURCE}[fid],
    ))
    state, _ = mutable_state()
    await image_wizard_v2.open_image_composer(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), state, launch.session, launch.user,
    )
    await image_gen.handle_session_photo(
        SimpleNamespace(photo=[SimpleNamespace(file_id="new-file", file_size=100)], answer=AsyncMock()),
        state, launch.session, launch.user,
    )
    values = launch.session.execute.await_args.args[0].compile().params
    assert json.loads(values["reference_urls"]) == REFS[:2]
    assert json.loads(values["reference_file_ids"]) == existing_files + ["new-file"]
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS[:2] + ([REFS[2]] if existing_files else []) + [SOURCE]


@pytest.mark.parametrize("entrypoint", ["remix", "style"])
async def test_explicit_remix_photo_replaces_result_and_original_inputs(local_launch, nexus_posts, monkeypatch, entrypoint):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:2], reference_file_id="file-3", reference_file_ids=["file-3"],
    )
    old.last_result_url = SOURCE
    old.last_generation_id = launch.generation.id
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, old.last_generation_id)))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[2]))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_session:remix:99")
    if entrypoint == "remix":
        await image_gen.cb_image_session_remix(call, launch.session, state, launch.user)
    else:
        call.data = "img_style:clothes:99"
        await image_gen.cb_image_style_choice(call, launch.session, state, launch.user)
    await image_gen.handle_session_photo(
        SimpleNamespace(photo=[SimpleNamespace(file_id="replacement", file_size=100)], answer=AsyncMock()),
        state, launch.session, launch.user,
    )
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own edit", answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == [REFS[2]]
    assert "own edit" in nexus_posts[0]["params"]["prompt"]
    assert SECRET not in nexus_posts[0]["params"]["prompt"]
    assert json.loads(old.reference_file_ids) == ["replacement"]


@pytest.mark.parametrize("setting", ["ratio", "quality", "banana_model"])
async def test_actual_composer_settings_preserve_mixed_refs_on_session_recreation(local_launch, nexus_posts, monkeypatch, setting):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS[:2], reference_file_id="file-3", reference_file_ids=["file-3", "file-4"],
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr("bot.ui.router.render_screen", AsyncMock(return_value=SimpleNamespace(text="active", reply_markup=None)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"file-3": REFS[2], "file-4": SOURCE}[fid],
    ))
    state, _ = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data=None)
    await image_wizard_v2.open_image_composer(call, state, launch.session, launch.user)
    if setting == "ratio":
        call.data = "img_v2:ratio:set:3:4"
        await image_wizard_v2.set_default_ratio(call, state)
    elif setting == "quality":
        call.data = "img_v2:quality:set:4K"
        await image_wizard_v2.set_default_quality(call, state)
    else:
        call.data = "img_nb:model:nano-banana-pro"
        await image_gen.cb_nana_banano_model(call, state, launch.session, launch.user)
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()),
        state, launch.session, launch.user, AsyncMock(),
    )
    current = launch.created_sessions[-1]
    assert current is not old
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]


@pytest.mark.parametrize("alias", [False, True])
async def test_active_photo_add_checks_complete_deduplicated_cap(local_launch, nexus_posts, monkeypatch, alias):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS, reference_file_id="saved", reference_file_ids=["saved"],
    )
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(old, None)))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"saved": SOURCE, "new": REFS[0] if alias else "https://example.test/fifth.jpg"}[fid],
    ))
    state, _ = mutable_state()
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="new", file_size=100)], answer=AsyncMock(), bot=AsyncMock(),
    )
    await image_gen.handle_session_photo(message, state, launch.session, launch.user)
    assert json.loads(old.reference_file_ids) == (["saved", "new"] if alias else ["saved"])
    assert json.loads(old.reference_urls) == REFS
    if not alias:
        launch.session.execute.assert_not_awaited()
        return
    assert "4/4" in message.answer.await_args.args[0]
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]


@pytest.mark.parametrize("overflow", [False, True])
async def test_shared_launch_boundary_validates_deduplicated_refs_before_accounting(local_launch, nexus_posts, overflow):
    from db.models import ImageGenerationAction

    launch = local_launch
    current = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt",
    )
    refs = [f" {REFS[0]} ", *REFS, SOURCE]
    if overflow:
        refs.append("https://example.test/fifth.jpg")
    state, _ = mutable_state()
    started = await image_gen._launch_session_generation(
        source_message=AsyncMock(), state=state, session=launch.session, db_user=launch.user,
        image_session=current, prompt="own prompt", action_type=ImageGenerationAction.initial,
        reference_url=refs, parent_generation_id=None, launching_text="Starting", queued_text="Queued",
    )
    assert started is not overflow
    if overflow:
        assert nexus_posts == []
        repo.charge_image_generation.assert_not_awaited()
        repo.create_generation.assert_not_awaited()
    else:
        assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
        repo.charge_image_generation.assert_awaited_once()


@pytest.mark.parametrize("input_count", [0, 2, 4])
async def test_completed_session_model_selection_only_falls_back_to_result_without_inputs(local_launch, nexus_posts, monkeypatch, input_count):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    file_ids = ["file-1", "file-2", "file-3", "file-4"][:input_count]
    result_url = "https://example.test/completed-output.jpg"
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image" if input_count else "text", "9:16", "2K", 1,
        "own prompt", reference_file_id=file_ids[0] if file_ids else None, reference_file_ids=file_ids,
    )
    old.last_result_url = result_url
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: dict(zip(file_ids, REFS + [SOURCE], strict=False))[fid],
    ))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_model:nano-banana-pro", bot=AsyncMock())
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_gen.cb_image_model(call, state, launch.session, launch.user)
    assert data.get("model_key") == "nano-banana-pro"
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()),
        state, launch.session, launch.user, call.bot,
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=launch.created_sessions[-1]))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    expected = (REFS + [SOURCE])[:input_count] if input_count else [result_url]
    assert nexus_posts[0]["params"]["image_urls"] == expected
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr("bot.ui.router.render_screen", AsyncMock(return_value=SimpleNamespace(text="active", reply_markup=None)))
    await image_wizard_v2.open_image_composer(call, state, launch.session, launch.user)
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, call.bot,
    )
    assert nexus_posts[1]["params"]["image_urls"] == expected


async def open_carried_composer(monkeypatch, launch, refs, model="nano-banana-pro"):
    """Enter through the real settings/model callbacks, never a seeded reference FSM."""
    from bot.handlers import image_wizard_v2

    old = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "9:16", "2K", 1,
        "own prompt", reference_urls=refs,
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4, display_name=model)))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data=f"img_model:{model}", bot=AsyncMock())
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_gen.cb_image_model(call, state, launch.session, launch.user)
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    return old, state, data, call


@pytest.mark.parametrize("entrypoint", ["prompt_upload", "image_upload"])
@pytest.mark.parametrize("alias", [False, True])
async def test_carried_public_refs_upload_validates_union_before_mutation(local_launch, nexus_posts, monkeypatch, entrypoint, alias):
    from bot.handlers import image_wizard_v2

    refs = REFS + [SOURCE]
    old, state, data, call = await open_carried_composer(monkeypatch, local_launch, refs)
    if entrypoint == "image_upload":
        await image_wizard_v2.add_reference(call, state)
    before = dict(data)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        return_value=REFS[0] if alias else "https://example.test/fifth-input.jpg",
    ))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new", file_size=100)], answer=AsyncMock(), caption=None)
    handler = image_gen.handle_prompt_reference_upload if entrypoint == "prompt_upload" else image_gen.handle_reference_upload
    await handler(message, state, local_launch.session, local_launch.user, call.bot)
    if not alias:
        assert data == before
        assert len(local_launch.created_sessions) == 1
        assert json.loads(old.reference_urls) == refs
        repo.charge_image_generation.assert_not_awaited()
        assert nexus_posts == []
        return
    assert data["ref_file_ids"] == ["new"]
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()),
        state, local_launch.session, local_launch.user, call.bot,
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=local_launch.created_sessions[-1]))
    await image_gen.cb_image_review_launch(call, state, local_launch.session, local_launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == refs


@pytest.mark.parametrize("selected", ["nano-banana-pro", "nano-banana-2", "nano-banana-2.1"])
@pytest.mark.parametrize("entrypoint", ["quick", "repeat"])
async def test_lower_cap_model_switch_rejects_atomically(local_launch, nexus_posts, monkeypatch, selected, entrypoint):
    refs = [f"https://example.test/vip-input-{index}.jpg" for index in range(14)]
    old, state, data, call = await open_carried_composer(monkeypatch, local_launch, refs, "nano-banana-pro-vip")
    if entrypoint == "repeat":
        monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
        call.data = f"img_repeat:model:{old.id}"
        await image_gen.cb_image_repeat_model(call, local_launch.session, state, local_launch.user)
    before = dict(data)
    local_launch.session.commit.reset_mock()
    if entrypoint == "quick":
        call.data = f"img_nb:model:{selected}"
        await image_gen.cb_nana_banano_model(call, state, local_launch.session, local_launch.user)
    else:
        call.data = f"img_model:{selected}"
        await image_gen.cb_image_model(call, state, local_launch.session, local_launch.user)
    assert data == before
    assert old.model == "nano-banana-pro-vip"
    assert json.loads(old.reference_urls) == refs
    local_launch.session.commit.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    assert nexus_posts == []


@pytest.mark.parametrize("entrypoint", ["mode", "ratio", "quality", "count", "enhance", "reference", "continue", "mode_selection"])
async def test_encoded_model_callbacks_cannot_bypass_reference_cap(local_launch, nexus_posts, monkeypatch, entrypoint):
    refs = [f"https://example.test/vip-input-{index}.jpg" for index in range(14)]
    _, state, data, call = await open_carried_composer(monkeypatch, local_launch, refs, "nano-banana-pro-vip")
    before = dict(data)
    if entrypoint == "mode_selection":
        call.data = "img_mode:image:nano-banana-pro"
        handler = image_gen.cb_image_mode
    else:
        call.data = f"img_dyn:{entrypoint}:nano-banana-pro"
        handler = getattr(image_gen, f"cb_image_dynamic_{entrypoint}")
    await handler(call, state)
    assert data == before
    assert nexus_posts == []


async def test_settings_picker_rejection_keeps_previous_active_model_and_session(local_launch, monkeypatch):
    refs = [f"https://example.test/vip-{index}.jpg" for index in range(14)]
    old, state, data, call = await open_carried_composer(monkeypatch, local_launch, refs, "nano-banana-pro-vip")
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    repo.archive_active_image_sessions.reset_mock()
    await image_gen.cb_image_settings_model(call, local_launch.session, state, local_launch.user)
    call.data = "img_model:nano-banana-pro"
    await image_gen.cb_image_model(call, state, local_launch.session, local_launch.user)
    repo.archive_active_image_sessions.assert_not_awaited()
    assert data["model_key"] == old.model == "nano-banana-pro-vip"
    assert data["image_session_id"] == old.id
    assert data["carryover_reference_urls"] == refs
    assert json.loads(old.reference_urls) == refs


async def test_alias_file_references_survive_legacy_repeat_persistence(local_launch, nexus_posts, monkeypatch):
    from bot.handlers import repeat_references

    launch = local_launch
    file_ids = ["a", "alias-a", "b", "c", "d"]
    refs = REFS + [SOURCE]
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_file_id="a", reference_file_ids=file_ids,
    )
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: dict(zip(file_ids, [refs[0], *refs], strict=True))[fid],
    ))
    monkeypatch.setattr(repeat_references, "safe_answer_callback", AsyncMock())
    state, _ = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    for source in (old, None):
        current = source or launch.created_sessions[-1]
        monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
        await repeat_references._begin_repeat_collection(
            call=call, state=state, bot=AsyncMock(), session=launch.session, db_user=launch.user, generation=launch.generation,
            source_session=current, reuse_session=False, source_feed_gen_id=None,
        )
        await repeat_references._repeat_refs_run(call, launch.session, state, launch.user, AsyncMock())
        assert nexus_posts[-1]["params"]["image_urls"] == refs


@pytest.mark.parametrize("entrypoint", ["prompt_upload", "image_upload"])
async def test_review_back_reference_edit_survives_next_repeat(local_launch, nexus_posts, monkeypatch, entrypoint):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    _, state, _, call = await open_carried_composer(monkeypatch, launch, REFS[:1])
    prompt = SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock())
    await image_gen.handle_prompt(prompt, state, launch.session, launch.user, call.bot)
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_back(call, state)
    if entrypoint == "image_upload":
        await image_wizard_v2.add_reference(call, state)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[1]))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="added-photo", file_size=100)], answer=AsyncMock(), caption=None)
    handler = image_gen.handle_prompt_reference_upload if entrypoint == "prompt_upload" else image_gen.handle_reference_upload
    await handler(message, state, launch.session, launch.user, call.bot)
    await image_gen.handle_prompt(prompt, state, launch.session, launch.user, call.bot)
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == REFS[:2]
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    assert nexus_posts[1]["params"]["image_urls"] == REFS[:2]


@pytest.mark.parametrize("protected", [False, True])
async def test_new_feed_remix_replaces_previous_remix_reference_state(local_launch, nexus_posts, monkeypatch, protected):
    from bot.handlers import feed

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    old.last_result_url = REFS[0]
    old.last_generation_id = 99
    launch.generation.result_url = REFS[0]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(feed, "safe_answer_callback", AsyncMock())
    state, _ = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_session:remix:99", bot=AsyncMock())
    await image_gen.cb_image_session_remix(call, launch.session, state, launch.user)
    launch.source.status = GenerationStatus.done
    launch.source.user_id = 100 if protected else launch.user.id
    call.data = "feed:remix:77"
    await feed.cb_feed_remix(call, launch.session, launch.user, state)
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own edit", answer=AsyncMock()), state, launch.session, launch.user, call.bot,
    )
    assert nexus_posts[0]["params"]["image_urls"] == [SOURCE]
    assert SECRET not in nexus_posts[0]["params"]["prompt"]


@pytest.mark.parametrize("public_refs", [[], REFS[:2]])
async def test_dynamic_model_selection_persists_carried_refs_for_next_repeat(local_launch, nexus_posts, monkeypatch, public_refs):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro-vip", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=public_refs, reference_file_id="file-3", reference_file_ids=["file-3", "file-4"],
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda _bot, fid: {"file-3": REFS[2], "file-4": SOURCE}[fid],
    ))
    state, _ = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="img_dyn:continue:nano-banana-pro", bot=AsyncMock())
    await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
    await image_gen.cb_image_dynamic_continue(call, state)
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, call.bot,
    )
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == public_refs + [REFS[2], SOURCE]
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    assert nexus_posts[1]["params"]["image_urls"] == public_refs + [REFS[2], SOURCE]


@pytest.mark.parametrize("entrypoint", ["ratio", "quality", "count", "repeat_ratio", "repeat_quality"])
@pytest.mark.parametrize("unbound", [False, True])
async def test_targeted_settings_do_not_relabel_another_series_references(local_launch, monkeypatch, entrypoint, unbound):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    target = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "target prompt", reference_urls=REFS[:1],
    )
    current = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "current prompt", reference_urls=REFS[1:2],
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=target))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr("bot.ui.router.render_screen", AsyncMock(return_value=SimpleNamespace(text="active", reply_markup=None)))
    state, data = mutable_state()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock())
    await image_wizard_v2.open_image_composer(call, state, launch.session, launch.user)
    if unbound:
        await image_wizard_v2.choose_default_quality(call, state)
    before = dict(data)
    launch.session.commit.reset_mock()
    prefix, value = {
        "ratio": ("img_sset_ratio:set", "16:9"), "quality": ("img_sset_quality:set", "4K"),
        "count": ("img_sset_count:set", "1"), "repeat_ratio": ("img_repeat:ratio:set", "16:9"),
        "repeat_quality": ("img_repeat:quality:set", "4K"),
    }[entrypoint]
    call.data = f"{prefix}:{target.id}:{value}"
    handler = getattr(image_gen, f"cb_image_{entrypoint}" if entrypoint.startswith("repeat") else f"cb_image_settings_{entrypoint}_set")
    await handler(call, launch.session, state, launch.user)
    assert data == before
    assert target.aspect_ratio == "9:16"
    assert target.quality == "2K"
    launch.session.commit.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["prompt_upload", "image_upload"])
@pytest.mark.parametrize("resolution", [None, RuntimeError("synthetic mirror unavailable")])
async def test_unresolved_overbound_upload_fails_closed_without_mutation(local_launch, nexus_posts, monkeypatch, entrypoint, resolution):
    _, state, data, call = await open_carried_composer(monkeypatch, local_launch, REFS + [SOURCE])
    before = dict(data)
    mirror = AsyncMock(side_effect=resolution) if isinstance(resolution, Exception) else AsyncMock(return_value=resolution)
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    handler = image_gen.handle_prompt_reference_upload if entrypoint == "prompt_upload" else image_gen.handle_reference_upload
    await handler(
        SimpleNamespace(photo=[SimpleNamespace(file_id="new", file_size=100)], answer=AsyncMock(), caption="own prompt"),
        state, local_launch.session, local_launch.user, call.bot,
    )
    assert data == before
    assert len(local_launch.created_sessions) == 1
    repo.charge_image_generation.assert_not_awaited()
    assert nexus_posts == []


@pytest.mark.parametrize("bound", [False, True])
async def test_valid_targeted_settings_keep_target_references(local_launch, nexus_posts, monkeypatch, bound):
    launch = local_launch
    current = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=REFS,
    )
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    state, _ = mutable_state()
    if bound:
        await image_gen._sync_state_with_image_session(state, current)
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data=f"img_sset_ratio:set:{current.id}:16:9")
    await image_gen.cb_image_settings_ratio_set(call, launch.session, state, launch.user)
    assert current.aspect_ratio == "16:9"
    await image_gen.handle_session_prompt(
        SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS


@pytest.mark.parametrize("kind", ["public", "files", "mixed"])
@pytest.mark.parametrize("alias", [False, True])
async def test_historical_fsm_restore_validates_before_archiving_active_series(local_launch, nexus_posts, monkeypatch, kind, alias):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro-vip", "image", "9:16", "2K", 1,
        "existing own prompt", reference_urls=REFS[:1],
    )
    urls = REFS + [SOURCE, REFS[0] if alias else "https://example.test/fifth.jpg"]
    file_ids = [f"file-{index}" for index in range(5)]
    split = {"public": 5, "files": 0, "mixed": 2}[kind]
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(side_effect=lambda _bot, fid: urls[file_ids.index(fid)]))
    state, data = mutable_state({
        "model_key": "nano-banana-pro", "mode": "image", "image_mode": "image", "quality": "2K", "aspect_ratio": "9:16",
        "reference_urls": urls[:split], "ref_file_ids": file_ids[split:],
    })
    before = json.loads(json.dumps(data))
    repo.archive_active_image_sessions.reset_mock()
    launch.session.commit.reset_mock()
    await image_gen.handle_prompt(
        SimpleNamespace(text="new own prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    if not alias:
        assert data == before
        assert len(launch.created_sessions) == 1
        assert old.model == "nano-banana-pro-vip"
        assert json.loads(old.reference_urls) == REFS[:1]
        repo.archive_active_image_sessions.assert_not_awaited()
        launch.session.commit.assert_not_awaited()
        repo.charge_image_generation.assert_not_awaited()
        assert nexus_posts == []
        return
    current = launch.created_sessions[-1]
    assert current is not old
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_review_launch(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), state, launch.session, launch.user,
    )
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]


@pytest.mark.parametrize("public_refs,files,expected", [(REFS, [], 3), (REFS[:2], ["file"], 3), ([], [], 0)])
async def test_active_series_counter_counts_stored_public_attachments_without_network(local_launch, monkeypatch, public_refs, files, expected):
    from bot.ui.image_menu import render_active_image_session

    current = await repo.create_image_session(
        local_launch.session, local_launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_urls=public_refs, reference_file_ids=files,
    )
    mirror = AsyncMock(side_effect=AssertionError("UI counting must not resolve references"))
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    rendered = render_active_image_session(current)
    expected_label = f"{expected} шт" if expected else "нет"
    assert f"Референсы: {expected_label}" in rendered.text
    mirror.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["active", "active_repeat", "review", "new_review", "regen", "feed_again", "photo_prompt", "legacy_collect", "safe_open"])
@pytest.mark.parametrize("failure", [None, RuntimeError("synthetic unavailable photo")])
async def test_unavailable_saved_photo_never_launches_surviving_subset(local_launch, nexus_posts, monkeypatch, entrypoint, failure):
    from bot.handlers import feed, image_wizard_v2, photo_prompt, repeat_references, repeat_safe

    launch = local_launch
    current = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "1:1", "2K", 1,
        "own prompt", reference_urls=REFS[:1], reference_file_id="ok", reference_file_ids=["ok", "unavailable"],
    )
    launch.generation.image_session_id = current.id
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=launch.generation))
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())

    async def mirror(_bot, file_id):
        if file_id == "ok":
            return REFS[1]
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    state, data = mutable_state()
    await image_gen._sync_state_with_image_session(state, current)
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="regen:image:99", bot=AsyncMock(), from_user=SimpleNamespace(id=777))
    message = SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock())
    if entrypoint == "new_review":
        await image_wizard_v2.choose_default_quality(call, state)
    before = json.loads(json.dumps(data))
    repo.archive_active_image_sessions.reset_mock()
    launch.session.commit.reset_mock()
    if entrypoint == "active":
        await image_gen.handle_session_prompt(message, state, launch.session, launch.user, call.bot)
    elif entrypoint == "active_repeat":
        await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    elif entrypoint in {"review", "new_review"}:
        await image_gen.handle_prompt(message, state, launch.session, launch.user, call.bot)
    elif entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
    elif entrypoint == "feed_again":
        call.data = "feed:again:99"
        await feed.cb_feed_again(call, launch.session, launch.user, state, call.bot)
    elif entrypoint == "photo_prompt":
        await photo_prompt._launch_in_session(
            source_message=message, state=state, session=launch.session, db_user=launch.user,
            bot=call.bot, image_session=current, prompt="own prompt",
        )
    elif entrypoint == "legacy_collect":
        await repeat_references._begin_repeat_collection(
            call=call, state=state, bot=call.bot, session=launch.session, db_user=launch.user, generation=launch.generation,
            source_session=current, reuse_session=False, source_feed_gen_id=None,
        )
    else:
        call.data = "repeat_image_img_99"
        await repeat_safe.open_repeat(call, launch.session, state, launch.user, call.bot)
    assert data == before
    assert current.aspect_ratio == "1:1"
    assert len(launch.created_sessions) == 1
    assert json.loads(current.reference_file_ids) == ["ok", "unavailable"]
    assert json.loads(current.reference_urls) == REFS[:1]
    repo.archive_active_image_sessions.assert_not_awaited()
    launch.session.commit.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    assert nexus_posts == []

    if entrypoint in {"active", "active_repeat", "review", "new_review"}:
        monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(side_effect=lambda _bot, fid: REFS[1] if fid == "ok" else REFS[2]))
        if entrypoint == "active":
            await image_gen.handle_session_prompt(message, state, launch.session, launch.user, call.bot)
        elif entrypoint == "active_repeat":
            await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
        else:
            await image_gen.handle_prompt(message, state, launch.session, launch.user, call.bot)
            await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
        assert nexus_posts[0]["params"]["image_urls"] == REFS
        repo.charge_image_generation.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["active_upload", "prompt_upload", "legacy_upload", "model_select"])
@pytest.mark.parametrize("failure", [None, RuntimeError("synthetic unavailable photo")])
async def test_under_cap_admission_checks_every_photo_before_mutation(local_launch, nexus_posts, monkeypatch, entrypoint, failure):
    launch = local_launch
    current = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "own prompt", reference_file_id="saved", reference_file_ids=["saved"],
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True, display_name="Pro")))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    state, data = mutable_state()
    await image_gen._sync_state_with_image_session(state, current)
    before = json.loads(json.dumps(data))
    fields = (current.model, current.reference_file_id, current.reference_file_ids, current.reference_url, current.reference_urls)

    async def mirror(_bot, fid):
        if fid == "new":
            return REFS[0]  # Valid alias must be accepted after the saved photo recovers.
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new", file_size=100)], caption=None, answer=AsyncMock(), bot=AsyncMock())
    call = SimpleNamespace(data="img_nb:model:nano-banana-pro", message=AsyncMock(), answer=AsyncMock(), bot=message.bot)

    async def invoke():
        if entrypoint == "active_upload":
            await image_gen.handle_session_photo(message, state, launch.session, launch.user)
        elif entrypoint == "model_select":
            await image_gen.cb_nana_banano_model(call, state, launch.session, launch.user)
        else:
            handler = image_gen.handle_prompt_reference_upload if entrypoint == "prompt_upload" else image_gen.handle_reference_upload
            await handler(message, state, launch.session, launch.user, message.bot)

    launch.session.commit.reset_mock()
    launch.session.execute.reset_mock()
    repo.archive_active_image_sessions.reset_mock()
    await invoke()
    assert data == before
    assert fields == (current.model, current.reference_file_id, current.reference_file_ids, current.reference_url, current.reference_urls)
    assert len(launch.created_sessions) == 1
    launch.session.commit.assert_not_awaited()
    launch.session.execute.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    assert nexus_posts == []

    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[0]))
    await invoke()
    assert data["ref_file_ids"] == (["saved"] if entrypoint == "model_select" else ["saved", "new"])
    await image_gen.handle_prompt(
        SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, message.bot,
    )
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == REFS[:1]


@pytest.mark.parametrize("entrypoint", ["regen", "feed_again"])
@pytest.mark.parametrize("mode", ["image", "text"])
@pytest.mark.parametrize("model,max_refs", [("nano-banana-pro", 4), ("qwen/image-to-image", 1)])
async def test_restored_clone_checks_resolved_cap_before_archiving(local_launch, nexus_posts, monkeypatch, entrypoint, model, max_refs, mode):
    from bot.handlers import feed

    launch = local_launch
    refs = [f"https://example.test/clone-{i}.jpg" for i in range(max_refs + 1)]
    source = await repo.create_image_session(
        launch.session, launch.user.id, model, mode, "9:16", "2K", 1,
        "own prompt", reference_urls=refs,
    )
    active = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "active prompt", reference_urls=REFS[:1],
    )
    launch.generation.model = model
    launch.generation.image_session_id = source.id
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=source))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=active))
    state, data = mutable_state()
    await image_gen._sync_state_with_image_session(state, active)
    before = json.loads(json.dumps(data))
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    launch.session.commit.reset_mock()
    launch.session.execute.reset_mock()
    repo.archive_active_image_sessions.reset_mock()
    if entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
    else:
        call.data = "feed:again:99"
        await feed.cb_feed_again(call, launch.session, launch.user, state, call.bot)
    assert len(launch.created_sessions) == 2
    assert data == before
    assert json.loads(source.reference_urls) == refs
    assert json.loads(active.reference_urls) == REFS[:1]
    launch.session.commit.assert_not_awaited()
    launch.session.execute.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    assert nexus_posts == []


@pytest.fixture
async def image_provider_posts(monkeypatch):
    posts = []

    def capture(request):
        assert request.method == "POST"
        assert str(request.url) in {"https://nexus.test/generate", "https://kie.test/api/v1/jobs/createTask"}
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"task_id": "synthetic-task", "status": "pending", "code": 200, "data": {"taskId": "synthetic-task"}})

    async with httpx.AsyncClient(base_url="https://nexus.test", transport=httpx.MockTransport(capture)) as nexus_http:
        async with httpx.AsyncClient(base_url="https://kie.test", transport=httpx.MockTransport(capture)) as kie_http:
            client = NexusApiClient(api_key="synthetic-test-only", base_url="https://nexus.test", client=nexus_http)
            monkeypatch.setattr(nexus_image_adapter, "NexusApiClient", lambda: client)
            monkeypatch.setattr(image_service.kieai_client, "get_client", lambda: kie_http)
            monkeypatch.setattr(image_service.comet_fallback, "generate_image", AsyncMock(side_effect=AssertionError("Unexpected fallback")))
            yield posts


@pytest.mark.parametrize("entrypoint", ["regen", "feed_again"])
@pytest.mark.parametrize("model,max_refs", [("nano-banana-pro", 4), ("qwen/image-to-image", 1)])
@pytest.mark.parametrize("protected", [False, True])
async def test_clone_retry_accepts_exact_cap_and_source_file_aliases(local_launch, image_provider_posts, monkeypatch, entrypoint, model, max_refs, protected):
    from bot.handlers import feed

    launch = local_launch
    refs = [f"https://example.test/retry-{i}.jpg" for i in range(max_refs)]
    old = await repo.create_image_session(
        launch.session, launch.user.id, model, "image", "9:16", "2K", 1,
        None if protected else "own prompt", reference_urls=refs, reference_file_id="extra", reference_file_ids=["extra"],
    )
    launch.generation.model = model
    launch.generation.image_session_id = old.id
    launch.generation.source_feed_gen_id = 77 if protected else None
    launch.generation.prompt = SECRET if protected else "own prompt"
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=SOURCE))
    state, data = mutable_state({"image_session_id": old.id, "ref_file_ids": ["extra"]})
    before = json.loads(json.dumps(data))
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())

    async def invoke():
        if entrypoint == "regen":
            await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
        else:
            call.data = "feed:again:99"
            await feed.cb_feed_again(call, launch.session, launch.user, state, call.bot)

    repo.archive_active_image_sessions.reset_mock()
    await invoke()
    if protected:
        # A historical source alias does not consume a reader photo slot.
        assert len(image_provider_posts) == 1
        inp = image_provider_posts[0]["params"] if model == "nano-banana-pro" else image_provider_posts[0]["input"]
        assert (inp["image_urls"] if model == "nano-banana-pro" else [inp["image_url"]]) == refs
        assert SECRET in inp["prompt"]
        return
    assert data == before
    assert len(launch.created_sessions) == 1
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    assert image_provider_posts == []
    # Keep every attachment: making the public/file/source aliases identical
    # gives a valid exact-cap candidate, without truncating representations.
    refs[-1] = SOURCE
    old.reference_urls = json.dumps(refs)
    old.reference_url = refs[0]
    await invoke()
    assert len(launch.created_sessions) == 2
    payload = image_provider_posts[0]
    inp = payload["params"] if model == "nano-banana-pro" else payload["input"]
    expected_provider_refs = (
        [SOURCE, *(url for url in refs if url != SOURCE)]
        if protected and model == "nano-banana-pro"
        else refs
    )
    assert (inp["image_urls"] if model == "nano-banana-pro" else [inp["image_url"]]) == expected_provider_refs
    assert json.loads(launch.created_sessions[-1].reference_file_ids) == ["extra"]
    assert json.loads(launch.created_sessions[-1].reference_urls) == refs
    if protected:
        assert launch.created_sessions[-1].base_prompt is None
        if max_refs > 1:
            assert SECRET not in inp["prompt"]


@pytest.mark.parametrize("failure", [None, RuntimeError("synthetic unavailable photo")])
async def test_explicit_photo_prompt_ref_resolves_before_replacing_series(local_launch, nexus_posts, monkeypatch, failure):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1,
        "old prompt", reference_urls=REFS[:1],
    )
    state, data = mutable_state({"generated_prompt": "own new prompt", "p2p_model_key": "nano-banana-pro", "p2p_ref_file_id": "new"})
    before = dict(data)
    mirror = AsyncMock(side_effect=failure) if isinstance(failure, Exception) else AsyncMock(return_value=failure)
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    repo.archive_active_image_sessions.reset_mock()
    launch.session.commit.reset_mock()
    await image_gen.cb_p2p_generate(call, state, launch.session, launch.user, call.bot)
    assert data == before
    assert len(launch.created_sessions) == 1
    assert json.loads(old.reference_urls) == REFS[:1]
    repo.archive_active_image_sessions.assert_not_awaited()
    launch.session.commit.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    assert nexus_posts == []
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[1]))
    await image_gen.cb_p2p_generate(call, state, launch.session, launch.user, call.bot)
    assert nexus_posts[0]["params"]["image_urls"] == REFS[1:2]


@pytest.mark.parametrize("invalid", ["missing", "overflow"])
async def test_result_action_fallback_clone_rejects_invalid_refs_without_writes(local_launch, monkeypatch, invalid):
    launch = local_launch
    source = await repo.create_image_session(
        launch.session, launch.user.id, "qwen/image-to-image", "image", "9:16", "basic", 1, "own prompt",
        reference_urls=REFS[:2] if invalid == "overflow" else [], reference_file_ids=["missing"] if invalid == "missing" else [],
    )
    launch.generation.model = source.model
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=source))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=None))
    state, data = mutable_state({"image_session_id": 123, "ref_file_ids": ["current-photo"]})
    before = dict(data)
    call = SimpleNamespace(data="reprompt:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    repo.archive_active_image_sessions.reset_mock()
    launch.session.commit.reset_mock()
    await image_gen.cb_reprompt_image(call, launch.session, state, launch.user)
    assert data == before
    assert len(launch.created_sessions) == 1
    repo.archive_active_image_sessions.assert_not_awaited()
    launch.session.commit.assert_not_awaited()


async def test_photo_prompt_active_text_only_model_ignores_unused_stale_photo(local_launch, image_provider_posts, monkeypatch):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "google/nano-banana", "text", "9:16", "basic", 1, "own prompt",
    )
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    mirror = AsyncMock(side_effect=AssertionError("Text-only model must not resolve unused photo"))
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    state, _ = mutable_state({"generated_prompt": "own new prompt", "p2p_ref_file_id": "stale-unused"})
    repo.archive_active_image_sessions.reset_mock()
    await image_gen.cb_p2p_generate(
        SimpleNamespace(message=AsyncMock(), answer=AsyncMock()), state, launch.session, launch.user, AsyncMock(),
    )
    mirror.assert_not_awaited()
    assert len(launch.created_sessions) == 1
    repo.archive_active_image_sessions.assert_not_awaited()
    assert image_provider_posts[0]["input"]["prompt"] == "own new prompt"
    assert "image_url" not in image_provider_posts[0]["input"]


@pytest.mark.parametrize("entrypoint", ["regen", "feed_again"])
async def test_text_only_protected_exact_repeat_does_not_count_unconsumed_source(local_launch, image_provider_posts, monkeypatch, entrypoint):
    from bot.handlers import feed

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "google/nano-banana", "text", "9:16", "basic", 1, None,
    )
    launch.generation.model = old.model
    launch.generation.image_session_id = old.id
    launch.generation.prompt = SECRET
    launch.generation.source_feed_gen_id = 77
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(side_effect=lambda _session, gid: launch.source if gid == 77 else launch.generation))
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    state, _ = mutable_state()
    if entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
    else:
        call.data = "feed:again:99"
        await feed.cb_feed_again(call, launch.session, launch.user, state, call.bot)
    assert image_provider_posts == []
    repo.charge_image_generation.assert_not_awaited()
    assert launch.created_sessions[-1].base_prompt is None
    assert SECRET not in str(call.message.answer.call_args_list)


@pytest.mark.parametrize("entrypoint", ["active", "regen", "feed_again", "safe_repeat", "model_switch", "legacy_state"])
@pytest.mark.parametrize("duplicate_lead", [False, True])
async def test_legacy_scalar_and_plural_refs_keep_lead_through_real_routes(local_launch, nexus_posts, monkeypatch, entrypoint, duplicate_lead):
    from api.repeat_runtime import _urls_from_image_session
    from bot.handlers import feed, image_wizard_v2, repeat_safe

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt",
    )
    # Legacy/imported row shape: lead scalar is independent of plural extras.
    old.reference_url = REFS[0]
    old.reference_urls = json.dumps(REFS if duplicate_lead else REFS[1:])
    launch.generation.image_session_id = old.id
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=launch.generation))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda _user: False)
    state, data = mutable_state()
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock(), from_user=SimpleNamespace(id=777))
    assert _urls_from_image_session(old) == REFS
    if entrypoint == "active":
        await image_gen._sync_state_with_image_session(state, old)
        await image_gen.handle_session_prompt(SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, call.bot)
    elif entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
    elif entrypoint == "feed_again":
        call.data = "feed:again:99"
        await feed.cb_feed_again(call, launch.session, launch.user, state, call.bot)
    elif entrypoint == "safe_repeat":
        call.data = "repeat_image_img_99"
        await repeat_safe.open_repeat(call, launch.session, state, launch.user, call.bot)
        assert data["repeat_reference_images"] == REFS
        await repeat_safe.confirm_repeat(call, launch.session, state, launch.user, call.bot)
    else:
        if entrypoint == "model_switch":
            await image_gen._sync_state_with_image_session(state, old)
            await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
        else:
            await state.update_data(model_key="nano-banana-pro", mode="image", reference_url=REFS[0], reference_urls=REFS[1:])
        await image_wizard_v2.open_model_composer_for_selection(call, state, launch.session, "nano-banana-pro")
        await image_gen.handle_prompt(SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, call.bot)
        await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[-1]["params"]["image_urls"] == REFS
    current = launch.created_sessions[-1]
    resolved = await image_gen._session_reference_url(call.bot, current)
    await image_service.generate_image(ImageModel.NANO_BANANA_PRO, "next own prompt", image_url=resolved)
    assert nexus_posts[-1]["params"]["image_urls"] == REFS


@pytest.mark.parametrize("entrypoint", ["dynamic", "repeat_model", "composer", "mode", "forced_composer"])
async def test_explicit_text_transition_ignores_refs_through_provider_payload(local_launch, image_provider_posts, monkeypatch, entrypoint):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt",
        reference_urls=REFS, reference_file_id="stale", reference_file_ids=["stale"],
    )
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    mirror = AsyncMock(side_effect=AssertionError("Text transition must not resolve unused references"))
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    state, data = mutable_state()
    await image_gen._sync_state_with_image_session(state, old)
    model = "nano-banana-pro" if entrypoint in {"mode", "forced_composer"} else "google/nano-banana"
    call = SimpleNamespace(data=f"img_dyn:continue:{model}", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    if entrypoint == "dynamic":
        await image_gen.cb_image_dynamic_continue(call, state)
    elif entrypoint == "repeat_model":
        await state.update_data(repeat_model_select=True)
        call.data = f"img_model:{model}"
        await image_gen.cb_image_model(call, state, launch.session, launch.user)
    elif entrypoint == "mode":
        call.data = f"img_mode:text:{model}"
        await image_gen.cb_image_mode(call, state)
    else:
        await image_wizard_v2.open_model_composer_for_selection(call, state, launch.session, model, forced_mode="text" if entrypoint == "forced_composer" else None)
    assert data["model_key"] == model
    assert data["image_mode"] == "text"
    mirror.assert_not_awaited()
    await image_gen.handle_prompt(SimpleNamespace(text="own text-only prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, call.bot)
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    mirror.assert_not_awaited()
    inp = image_provider_posts[-1]["params"] if model == "nano-banana-pro" else image_provider_posts[-1]["input"]
    assert not inp.get("image_urls")
    assert not inp.get("image_url")
    current = launch.created_sessions[-1]
    assert current.mode == "text"
    if current is not old:
        assert not current.reference_file_ids
        assert not current.reference_url
        assert not current.reference_urls

    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    mirror.assert_not_awaited()
    repeated = image_provider_posts[-1]["params"] if model == "nano-banana-pro" else image_provider_posts[-1]["input"]
    assert not repeated.get("image_urls")
    assert not repeated.get("image_url")


async def test_mode_picker_allows_text_escape_without_mutating_or_resolving_refs(local_launch, image_provider_posts, monkeypatch):
    launch = local_launch
    state, data = mutable_state({
        "model_key": "nano-banana-pro-vip", "image_model": "nano-banana-pro-vip", "image_session_id": 88,
        "mode": "image", "image_mode": "image", "ref_file_ids": [f"missing-{i}" for i in range(5)],
        "reference_urls": REFS, "carryover_reference_urls": [SOURCE],
    })
    before = json.loads(json.dumps(data))
    mirror = AsyncMock(side_effect=AssertionError("Mode navigation must not resolve files"))
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    edit = AsyncMock()
    monkeypatch.setattr(image_gen, "safe_edit_message", edit)
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=None))
    call = SimpleNamespace(data="img_dyn:mode:nano-banana-pro", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    await image_gen.cb_image_dynamic_mode(call, state)
    assert data == before
    edit.assert_awaited_once()
    mirror.assert_not_awaited()
    call.data = "img_mode:text:nano-banana-pro"
    await image_gen.cb_image_mode(call, state)
    await image_gen.handle_prompt(SimpleNamespace(text="own text prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, call.bot)
    await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    mirror.assert_not_awaited()
    assert not image_provider_posts[0]["params"].get("image_urls")


@pytest.mark.parametrize("entrypoint", ["active", "repeat"])
async def test_legacy_mixed_matching_fsm_keeps_scalar_lead_with_telegram_file(local_launch, nexus_posts, monkeypatch, entrypoint):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt",
        reference_file_id="saved", reference_file_ids=["saved"],
    )
    old.reference_url = REFS[0]
    old.reference_urls = json.dumps(REFS[1:])
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=SOURCE))
    state, _ = mutable_state({
        "image_session_id": old.id, "model_key": old.model, "mode": "image", "image_mode": "image",
        "reference_url": REFS[0], "reference_urls": REFS[1:], "image_file_id": "saved", "ref_file_ids": ["saved"],
    })
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    if entrypoint == "active":
        await image_gen.handle_session_prompt(SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, call.bot)
    else:
        await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    assert nexus_posts[0]["params"]["image_urls"] == REFS + [SOURCE]
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    assert nexus_posts[1]["params"]["image_urls"] == REFS + [SOURCE]


@pytest.mark.parametrize("entrypoint", ["active", "repeat", "repeat_unbound", "regen", "model_switch"])
@pytest.mark.parametrize("with_public", [False, True])
async def test_legacy_file_id_scalar_plural_union_survives_matching_state_and_repeat(local_launch, nexus_posts, monkeypatch, entrypoint, with_public):
    from bot.handlers import image_wizard_v2

    launch = local_launch
    public = [SOURCE] if with_public else []
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt",
        reference_urls=public,
    )
    old.reference_file_id = "lead"
    old.reference_file_ids = json.dumps(["second", "third"])
    launch.generation.image_session_id = old.id
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=old))
    monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_gen, "_open_image_model_select", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_edit_message", AsyncMock())
    monkeypatch.setattr(image_wizard_v2, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(side_effect=lambda _bot, fid: dict(zip(["lead", "second", "third"], REFS))[fid]))
    state, _ = mutable_state({
        "image_session_id": old.id, "model_key": old.model, "mode": "image", "image_mode": "image",
        "reference_urls": public, "image_file_id": "lead", "ref_file_ids": ["second", "third"],
    })
    if entrypoint == "repeat_unbound":
        await state.clear()
        await state.update_data(image_session_id=old.id)
    call = SimpleNamespace(data="regen:image:99", message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    if entrypoint == "active":
        await image_gen.handle_session_prompt(SimpleNamespace(text="own prompt", answer=AsyncMock()), state, launch.session, launch.user, call.bot)
    elif entrypoint in {"repeat", "repeat_unbound"}:
        await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    elif entrypoint == "regen":
        await image_gen.cb_regen_image(call, launch.session, state, launch.user, call.bot)
    else:
        await image_gen.cb_image_settings_model(call, launch.session, state, launch.user)
        await image_wizard_v2.open_model_composer_for_selection(call, state, launch.session, "nano-banana-pro")
        await image_gen.handle_prompt(SimpleNamespace(text="own prompt", caption=None, answer=AsyncMock()), state, launch.session, launch.user, call.bot)
        await image_gen.cb_image_review_launch(call, state, launch.session, launch.user)
    assert nexus_posts[0]["params"]["image_urls"] == public + REFS
    current = launch.created_sessions[-1]
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=current))
    monkeypatch.setattr(repo, "get_active_image_session", AsyncMock(return_value=current))
    await image_gen._sync_state_with_image_session(state, current)
    await image_gen.cb_image_repeat_launch(call, launch.session, state, launch.user, call.bot)
    assert nexus_posts[1]["params"]["image_urls"] == public + REFS


@pytest.mark.parametrize("entrypoint", ["dynamic", "mode", "repeat_model"])
async def test_unknown_model_cannot_clear_inputs_as_text_transition(local_launch, monkeypatch, entrypoint):
    launch = local_launch
    old = await repo.create_image_session(
        launch.session, launch.user.id, "nano-banana-pro", "image", "9:16", "2K", 1, "own prompt", reference_urls=REFS,
    )
    state, data = mutable_state()
    await image_gen._sync_state_with_image_session(state, old)
    if entrypoint == "repeat_model":
        await state.update_data(repeat_model_select=True)
    before = json.loads(json.dumps(data))
    mirror = AsyncMock(side_effect=AssertionError("Unknown target must not resolve references"))
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=old))
    launch.session.commit.reset_mock()
    call = SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), bot=AsyncMock())
    if entrypoint == "dynamic":
        call.data = "img_dyn:continue:removed-model"
        await image_gen.cb_image_dynamic_continue(call, state)
    elif entrypoint == "mode":
        call.data = "img_mode:text:removed-model"
        await image_gen.cb_image_mode(call, state)
    else:
        call.data = "img_model:removed-model"
        await image_gen.cb_image_model(call, state, launch.session, launch.user)
    assert data == before
    assert old.model == "nano-banana-pro"
    assert json.loads(old.reference_urls) == REFS
    launch.session.commit.assert_not_awaited()
    mirror.assert_not_awaited()

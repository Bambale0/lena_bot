"""Restored repeat admission stays atomic; database and provider I/O is intercepted."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers import image_gen, repeat_reference_marketplace, repeat_safe
from db import repository as repo
from db.models import GenerationStatus, GenerationType, ImageSession, ImageSessionStatus

REFS = [f"https://example.test/photo-{number}.jpg" for number in range(1, 6)]
SOURCE = "https://example.test/public-scene.jpg"
FILE_IDS = [f"file-{number}" for number in range(1, 6)]


class RepeatState:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **values):
        self.data.update(values)

    async def clear(self):
        self.data.clear()
        self.state = None

    async def set_state(self, state):
        self.state = state


def callback(data=""):
    return SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=777), message=AsyncMock(),
        answer=AsyncMock(), bot=AsyncMock(),
    )


@pytest.fixture
def repeat_runtime(monkeypatch):
    active = ImageSession(
        id=1, user_id=42, model="nano-banana-pro", status=ImageSessionStatus.active,
        mode="image", base_prompt="previous series", last_prompt="previous series",
        reference_urls=json.dumps(REFS[:1]),
    )
    created = []
    generation = SimpleNamespace(
        id=99, user_id=42, model="nano-banana-pro", gen_type=GenerationType.image,
        prompt="my prompt", image_session_id=None, source_feed_gen_id=None,
        input_params="{}", status=GenerationStatus.done, credits_spent=4,
    )
    source = SimpleNamespace(
        id=77, user_id=100, model="nano-banana-pro", gen_type=GenerationType.image,
        prompt="private author prompt", result_url=SOURCE, result_urls=None,
        is_public_feed=True,
    )

    async def archive(*args, **kwargs):
        active.status = ImageSessionStatus.archived

    for name, value in {
        "archive_active_image_sessions": AsyncMock(side_effect=archive),
        "get_generation_by_id": AsyncMock(side_effect=lambda session, pk: source if pk == 77 else generation),
        "get_public_feed_generation": AsyncMock(return_value=source),
        "resolve_image_model_cost": AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
        "get_model_cost": AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)),
        "count_user_active_generations": AsyncMock(return_value=0),
        "charge_image_generation": AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=4)),
        "create_generation": AsyncMock(return_value=generation),
        "update_image_session_last_prompt": AsyncMock(),
        "update_generation_task": AsyncMock(),
    }.items():
        monkeypatch.setattr(repo, name, value)
    session = AsyncMock()
    session.add = MagicMock(side_effect=created.append)

    async def refresh(item):
        item.id = 7 + len(created)

    session.refresh = AsyncMock(side_effect=refresh)
    provider = AsyncMock(return_value=SimpleNamespace(task_id="synthetic-task", is_async=True))
    monkeypatch.setattr(image_gen.image_service, "generate_image", provider)
    monkeypatch.setattr(image_gen, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_reference_marketplace, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(repeat_safe, "get_repeat_task_by_any_id", AsyncMock(return_value=generation))
    monkeypatch.setattr(repeat_safe, "find_repeat_by_confirm_key", AsyncMock(return_value=None))
    monkeypatch.setattr(repeat_safe, "_is_admin", lambda user: False)
    monkeypatch.setattr(repeat_safe, "public_url_is_available", lambda url: True)
    return SimpleNamespace(
        session=session, user=SimpleNamespace(id=42, tg_id=777, credits=100),
        active=active, created=created, generation=generation, source=source, provider=provider,
    )


@pytest.mark.parametrize("protected_feed", [False, True])
async def test_safe_repeat_rejects_restored_overflow_before_archiving(repeat_runtime, protected_feed):
    runtime = repeat_runtime
    refs = REFS
    runtime.generation.input_params = json.dumps({"reference_images": refs})
    if protected_feed:
        runtime.generation.source_feed_gen_id = 77
        runtime.generation.prompt = runtime.source.prompt
    state = RepeatState()
    call = callback("repeat_image_img_99")
    await repeat_safe.open_repeat(call, runtime.session, state, runtime.user, call.bot)
    before = dict(state.data)
    runtime.session.commit.reset_mock()

    await repeat_safe.confirm_repeat(call, runtime.session, state, runtime.user, call.bot)

    assert state.data == before
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.active.base_prompt == "previous series"
    assert runtime.created == []
    runtime.session.add.assert_not_called()
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("protected_feed", [False, True])
async def test_safe_repeat_overflow_is_visible_after_callback_was_answered(repeat_runtime, monkeypatch, protected_feed):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import AnswerCallbackQuery

    from bot.utils.telegram_ui import safe_answer_callback

    runtime = repeat_runtime
    runtime.generation.input_params = json.dumps({"reference_images": REFS})
    if protected_feed:
        runtime.generation.source_feed_gen_id = 77
        runtime.generation.prompt = runtime.source.prompt
    state = RepeatState()
    opened = callback("repeat_image_img_99")
    await repeat_safe.open_repeat(opened, runtime.session, state, runtime.user, opened.bot)
    before = dict(state.data)
    call = callback("repeat_run_confirm_99")
    call.message = SimpleNamespace(answer=AsyncMock())
    delivered = []

    async def answer_once(text=None, **kwargs):
        if delivered:
            raise TelegramBadRequest(
                method=AnswerCallbackQuery(callback_query_id="consumed"),
                message="query ID is invalid",
            )
        delivered.append(text)

    call.answer = AsyncMock(side_effect=answer_once)
    monkeypatch.setattr(repeat_safe, "safe_answer_callback", safe_answer_callback)
    monkeypatch.setattr(image_gen, "safe_answer_callback", safe_answer_callback)

    await repeat_safe.confirm_repeat(call, runtime.session, state, runtime.user, call.bot)

    visible = delivered + [item.args[0] for item in call.message.answer.await_args_list]
    assert any("до 4 фото" in text for text in visible)
    call.answer.assert_awaited_once()
    assert runtime.source.prompt not in str(visible)
    assert state.data == before
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.created == []
    runtime.session.add.assert_not_called()
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("protected_feed", [False, True])
async def test_safe_repeat_deduplicates_restored_urls_without_losing_inputs(repeat_runtime, protected_feed):
    runtime = repeat_runtime
    original_saved_refs = [*REFS[:3], SOURCE] if protected_feed else REFS[:4]
    runtime.generation.input_params = json.dumps({"reference_images": [original_saved_refs[0], *original_saved_refs]})
    expected = REFS[:3] if protected_feed else REFS[:4]
    if protected_feed:
        runtime.generation.source_feed_gen_id = 77
        runtime.generation.prompt = runtime.source.prompt
    state = RepeatState()
    call = callback("repeat_image_img_99")
    await repeat_safe.open_repeat(call, runtime.session, state, runtime.user, call.bot)
    await repeat_safe.confirm_repeat(call, runtime.session, state, runtime.user, call.bot)

    assert runtime.provider.await_args.kwargs["image_url"] == expected
    # The saved legacy session retains its original input snapshot, while the
    # protected feed submission resolves the effective provider order afresh.
    assert json.loads(runtime.created[-1].reference_urls) == original_saved_refs
    assert await image_gen._session_reference_url(call.bot, runtime.created[-1]) == original_saved_refs


@pytest.mark.parametrize("alias", [False, True])
async def test_marketplace_restored_ids_are_validated_before_use_and_survive_repeat(repeat_runtime, monkeypatch, alias):
    runtime = repeat_runtime
    prompt = SimpleNamespace(id=8, prompt_text="chosen prompt", author_id=43, title="synthetic")
    use = AsyncMock(return_value=(prompt, {}))
    monkeypatch.setattr(repeat_reference_marketplace.marketplace, "get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr(repeat_reference_marketplace.marketplace, "use_prompt", use)

    def resolve(bot, file_id):
        index = FILE_IDS.index(file_id)
        return REFS[0 if alias and index == 1 else index]

    mirror = AsyncMock(side_effect=resolve)
    monkeypatch.setattr(repeat_reference_marketplace, "mirror_telegram_file", mirror)
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    state = RepeatState({
        "use_model_key": "nano-banana-pro", "use_prompt_id": 8,
        "prompt_multi_ref_file_ids": FILE_IDS, "prompt_multi_ref_max": 14,
    })
    before = dict(state.data)
    call = callback("prompt_multi_ref:run")
    await repeat_reference_marketplace._run(call, runtime.session, runtime.user, state, call.bot)

    if not alias:
        assert state.data == before
        assert runtime.active.status == ImageSessionStatus.active
        assert runtime.created == []
        runtime.session.commit.assert_not_awaited()
        use.assert_not_awaited()
        repo.archive_active_image_sessions.assert_not_awaited()
        repo.charge_image_generation.assert_not_awaited()
        runtime.provider.assert_not_awaited()
        return

    expected = [REFS[0], REFS[2], REFS[3], REFS[4]]
    assert runtime.provider.await_args.kwargs["image_url"] == expected
    copied = runtime.created[-1]
    assert json.loads(copied.reference_file_ids) == FILE_IDS
    assert await image_gen._session_reference_url(call.bot, copied) == expected
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(copied, 99)))
    await image_gen.cb_image_repeat_launch(call, runtime.session, state, runtime.user, call.bot)
    assert runtime.provider.await_count == 2
    assert runtime.provider.await_args.kwargs["image_url"] == expected


@pytest.mark.parametrize("alias", [False, True])
async def test_marketplace_collector_validates_resolved_candidate_atomically(repeat_runtime, monkeypatch, alias):
    state = RepeatState({
        "use_model_key": "nano-banana-pro", "prompt_multi_ref_file_ids": FILE_IDS[:4],
        "prompt_multi_ref_max": 14,
    })
    before = dict(state.data)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda bot, file_id: REFS[0 if alias and file_id == FILE_IDS[1] else FILE_IDS.index(file_id)],
    ))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id=FILE_IDS[-1], file_size=10)], answer=AsyncMock())
    await repeat_reference_marketplace._collect_prompt_reference(
        message, repeat_runtime.session, repeat_runtime.user, state, AsyncMock(),
    )
    if alias:
        assert state.data["prompt_multi_ref_file_ids"] == FILE_IDS
        assert "<b>4/4</b>" in message.answer.await_args.args[0]
    else:
        assert state.data == before
    repo.archive_active_image_sessions.assert_not_awaited()
    repeat_runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["menu", "set"])
@pytest.mark.parametrize("alias", [False, True])
async def test_marketplace_model_selection_counts_resolved_photos(repeat_runtime, monkeypatch, entrypoint, alias):
    state = RepeatState({
        "use_model_key": "nano-banana-pro-vip", "prompt_multi_ref_file_ids": FILE_IDS,
        "prompt_multi_ref_max": 14,
    })
    before = dict(state.data)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(
        side_effect=lambda bot, file_id: REFS[0 if alias and file_id == FILE_IDS[1] else FILE_IDS.index(file_id)],
    ))
    monkeypatch.setattr(repo, "get_all_model_costs", AsyncMock(return_value=[SimpleNamespace(model_key="nano-banana-pro")]))
    call = callback("pmr:m:nano-banana-pro")
    if entrypoint == "menu":
        await repeat_reference_marketplace._model_menu(call, repeat_runtime.session, state)
        markup = call.message.answer.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert ("pmr:m:nano-banana-pro" in callbacks) is alias
        assert state.data == before
    else:
        await repeat_reference_marketplace._set_model(call, repeat_runtime.session, state)
        if alias:
            assert state.data["use_model_key"] == "nano-banana-pro"
            assert state.data["prompt_multi_ref_file_ids"] == FILE_IDS
        else:
            assert state.data == before


@pytest.mark.parametrize("alias", [False, True])
async def test_legacy_collector_counts_resolved_url_file_union(monkeypatch, alias):
    from bot.handlers import repeat_references

    state = RepeatState({
        "repeat_model_key": "nano-banana-pro", "repeat_max_refs": 4,
        "repeat_base_reference_urls": REFS[:4], "repeat_new_reference_file_ids": [],
    })
    before = dict(state.data)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[0 if alias else 4]))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new-file", file_size=10)], answer=AsyncMock(), bot=AsyncMock())
    await repeat_references._collect_repeat_reference(message, state, AsyncMock(), SimpleNamespace(id=42), message.bot)
    if alias:
        assert state.data["repeat_new_reference_file_ids"] == ["new-file"]
        assert "<b>4/4</b>" in message.answer.await_args.args[0]
    else:
        assert state.data == before


@pytest.mark.parametrize("source_in_state", [77, None, 123])
async def test_legacy_collector_rejects_fifth_user_photo_with_protected_source(repeat_runtime, monkeypatch, source_in_state):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.source_feed_gen_id = 77
    creator_prompt = runtime.source.prompt
    runtime.generation.prompt = runtime.source.prompt
    runtime.active.reference_urls = json.dumps(REFS[:4])
    state = RepeatState()
    call = callback("img_session:repeat:99")
    await repeat_references._begin_repeat_collection(
        call=call, state=state, bot=call.bot, session=runtime.session, db_user=runtime.user, generation=runtime.generation,
        source_session=runtime.active, reuse_session=True, source_feed_gen_id=77,
    )
    await state.update_data(repeat_source_feed_gen_id=source_in_state)
    before = dict(state.data)
    stored_before = dict(runtime.active.__dict__)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[4]))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="fourth-user-file", file_size=10)], answer=AsyncMock(), bot=call.bot)
    handler = next(item for router in image_gen.router.chain_tail for item in router.message.handlers if item.callback is repeat_references._collect_repeat_reference)

    await handler.call(message, state=state, session=runtime.session, db_user=runtime.user, bot=call.bot)

    assert state.data == before
    assert runtime.active.__dict__ == stored_before
    assert "до 4 фото" in message.answer.await_args.args[0]
    assert creator_prompt not in str(message.answer.await_args_list)
    assert runtime.created == []
    runtime.session.add.assert_not_called()
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["collect", "run"])
@pytest.mark.parametrize("missing", ["publication", "recipe"])
async def test_legacy_repeat_missing_protected_source_is_atomic(repeat_runtime, monkeypatch, missing, entrypoint):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.source_feed_gen_id = 77
    creator_prompt = runtime.source.prompt
    state = RepeatState({
        "repeat_generation_id": 99, "repeat_source_feed_gen_id": 77,
        "repeat_model_key": "nano-banana-pro", "repeat_max_refs": 4,
        "repeat_base_reference_urls": REFS[:2], "repeat_new_reference_file_ids": [],
    })
    before = dict(state.data)
    if missing == "publication":
        monkeypatch.setattr(repo, "get_public_feed_generation", AsyncMock(return_value=None))
    elif missing == "recipe":
        runtime.source.prompt = ""
    else:
        raise AssertionError(missing)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[2]))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new-user-file", file_size=10)], answer=AsyncMock())

    if entrypoint == "collect":
        await repeat_references._collect_repeat_reference(message, state, runtime.session, runtime.user, AsyncMock())
    else:
        call = callback("repeat_refs:run")
        call.message = message
        await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)

    assert state.data == before
    visible = [item.args[0] for item in message.answer.await_args_list]
    if entrypoint == "run":
        visible.extend(item.args[0] for item in call.answer.await_args_list)
    assert any("недоступ" in text for text in visible)
    assert creator_prompt not in str(message.answer.await_args_list)
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.created == []
    runtime.session.add.assert_not_called()
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    repo.create_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("addition", ["third_user", "user_alias", "source_alias"])
async def test_legacy_collector_preserves_canonical_source_union_on_first_and_next_repeat(repeat_runtime, monkeypatch, addition):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.source_feed_gen_id = 77
    runtime.generation.prompt = runtime.source.prompt
    # The feed's ordered result list is authoritative over its stale scalar.
    runtime.source.result_urls = json.dumps([SOURCE])
    runtime.source.result_url = "https://example.test/stale-source.jpg"
    runtime.active.reference_urls = json.dumps(REFS[:2] if addition == "third_user" else REFS[:3])
    uploaded_url = {"third_user": REFS[2], "user_alias": REFS[0], "source_alias": SOURCE}[addition]
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=uploaded_url))
    state = RepeatState()
    call = callback("img_session:repeat:99")
    call.message = SimpleNamespace(answer=AsyncMock())
    await repeat_references._begin_repeat_collection(
        call=call, state=state, bot=call.bot, session=runtime.session, db_user=runtime.user, generation=runtime.generation,
        source_session=runtime.active, reuse_session=False, source_feed_gen_id=77,
    )
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new-user-file", file_size=10)], answer=AsyncMock())

    await repeat_references._collect_repeat_reference(message, state, runtime.session, runtime.user, call.bot)

    assert state.data["repeat_new_reference_file_ids"] == ["new-user-file"]
    assert state.data["repeat_reference_count"] == 3
    assert "<b>3/4</b>" in message.answer.await_args.args[0]
    runtime.session.commit.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()
    await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)

    expected = REFS[:3]
    assert runtime.provider.await_count == 1
    assert runtime.provider.await_args.kwargs["image_url"] == expected
    copied = runtime.created[-1]
    assert copied.base_prompt is None
    assert runtime.source.prompt not in str(copied.last_prompt)
    assert runtime.source.prompt in str(runtime.provider.await_args)
    assert runtime.source.prompt not in str(call.message.answer.await_args_list)
    assert runtime.source.prompt not in str(message.answer.await_args_list)
    runtime.generation.prompt = repo.create_generation.await_args.args[4]
    runtime.generation.input_params = json.dumps(repo.create_generation.await_args.kwargs["input_params"])
    runtime.generation.image_session_id = copied.id
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=copied))
    monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(copied, 99)))

    await repeat_references._session_repeat_interceptor(call, runtime.session, state, runtime.user, call.bot)
    await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)

    assert runtime.provider.await_count == 2
    assert runtime.provider.await_args.kwargs["image_url"] == expected
    assert copied.base_prompt is None
    assert runtime.source.prompt not in str(copied.last_prompt)
    assert runtime.source.prompt in str(runtime.provider.await_args_list)
    assert runtime.source.prompt not in str(call.message.answer.await_args_list)


@pytest.mark.parametrize("alias", [False, True])
async def test_safe_collector_checks_after_resolving_new_photo(monkeypatch, alias):
    state = RepeatState({
        "repeat_model_key": "nano-banana-pro", "repeat_max_refs": 4,
        "repeat_reference_images": REFS[:4],
    })
    state.state = repeat_safe.SafeRepeatFSM.collecting_refs
    before = dict(state.data)
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(return_value=REFS[0 if alias else 4]))
    message = SimpleNamespace(photo=[SimpleNamespace(file_id="new-file", file_size=10)], answer=AsyncMock())
    await repeat_safe.collect_repeat_ref(message, state, AsyncMock())
    if alias:
        assert state.state == repeat_safe.SafeRepeatFSM.confirming
        assert state.data["repeat_reference_images"] == REFS[:4]
    else:
        assert state.data == before
        assert state.state == repeat_safe.SafeRepeatFSM.collecting_refs


@pytest.mark.parametrize("protected_feed", [False, True])
@pytest.mark.parametrize("reuse_session", [False, True])
async def test_legacy_repeat_rejects_restored_overflow_before_session_writes(repeat_runtime, monkeypatch, protected_feed, reuse_session):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    refs = REFS
    if protected_feed:
        runtime.generation.source_feed_gen_id = 77
        runtime.generation.prompt = runtime.source.prompt
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=runtime.active))
    state = RepeatState({
        "repeat_generation_id": 99, "repeat_parent_generation_id": 99,
        "repeat_model_key": "nano-banana-pro", "repeat_max_refs": 14,
        "repeat_base_reference_urls": refs, "repeat_new_reference_file_ids": [],
        "repeat_reuse_session_id": 1 if reuse_session else None,
        "repeat_prompt": runtime.generation.prompt,
    })
    before = dict(state.data)
    stored_before = dict(runtime.active.__dict__)
    call = callback("repeat_refs:run")
    await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)

    assert state.data == before
    assert runtime.active.__dict__ == stored_before
    assert runtime.created == []
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["marketplace", "legacy"])
@pytest.mark.parametrize("unavailable", [None, "   ", RuntimeError("synthetic mirror failure")])
async def test_unresolved_restored_photo_never_launches_partial_inputs(repeat_runtime, monkeypatch, entrypoint, unavailable):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    prompt = SimpleNamespace(id=8, prompt_text="chosen prompt", author_id=43, title="synthetic")
    use = AsyncMock(return_value=(prompt, {}))
    monkeypatch.setattr(repeat_reference_marketplace.marketplace, "get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr(repeat_reference_marketplace.marketplace, "use_prompt", use)
    mirror = AsyncMock(side_effect=[REFS[0], unavailable])
    monkeypatch.setattr(repeat_reference_marketplace, "mirror_telegram_file", mirror)
    monkeypatch.setattr(image_gen, "_telegram_file_url", mirror)
    if entrypoint == "marketplace":
        state = RepeatState({
            "use_model_key": "nano-banana-pro", "use_prompt_id": 8,
            "prompt_multi_ref_file_ids": FILE_IDS[:2], "prompt_multi_ref_max": 14,
        })
    else:
        state = RepeatState({
            "repeat_generation_id": 99, "repeat_model_key": "nano-banana-pro",
            "repeat_new_reference_file_ids": FILE_IDS[:2], "repeat_max_refs": 14,
        })
    before = dict(state.data)
    call = callback()
    if entrypoint == "marketplace":
        await repeat_reference_marketplace._run(call, runtime.session, runtime.user, state, call.bot)
    else:
        await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)
    assert state.data == before
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.created == []
    runtime.session.commit.assert_not_awaited()
    use.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("missing_when_opened", [False, True])
@pytest.mark.parametrize("missing_count", [1, 2])
async def test_safe_repeat_never_drops_saved_photos_when_they_become_unavailable(repeat_runtime, monkeypatch, missing_when_opened, missing_count):
    runtime = repeat_runtime
    runtime.generation.input_params = json.dumps({"reference_images": REFS[:2]})
    unavailable = set(REFS[:missing_count])
    if missing_when_opened:
        monkeypatch.setattr(repeat_safe, "public_url_is_available", lambda url: url not in unavailable)
    state = RepeatState()
    call = callback("repeat_image_img_99")
    await repeat_safe.open_repeat(call, runtime.session, state, runtime.user, call.bot)
    before = dict(state.data)
    monkeypatch.setattr(repeat_safe, "public_url_is_available", lambda url: url not in unavailable)
    await repeat_safe.confirm_repeat(call, runtime.session, state, runtime.user, call.bot)
    assert state.data == before
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.created == []
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["collect", "menu", "set", "run"])
async def test_feed_marketplace_counts_user_photo_aliasing_public_source_once(repeat_runtime, monkeypatch, entrypoint):
    runtime = repeat_runtime
    file_ids = FILE_IDS[:4]

    def mirror(bot, file_id):
        return SOURCE if file_id == FILE_IDS[0] else REFS[FILE_IDS.index(file_id) - 1]

    monkeypatch.setattr(repeat_reference_marketplace, "mirror_telegram_file", AsyncMock(side_effect=mirror))
    monkeypatch.setattr(image_gen, "_telegram_file_url", AsyncMock(side_effect=mirror))
    monkeypatch.setattr(repo, "get_all_model_costs", AsyncMock(return_value=[SimpleNamespace(model_key="nano-banana-pro")]))
    use = AsyncMock()
    monkeypatch.setattr(repeat_reference_marketplace.marketplace, "use_prompt", use)
    runtime.generation.source_feed_gen_id = 77
    state = RepeatState({
        "feed_use_prompt": runtime.source.prompt, "feed_use_gen_id": 77,
        "feed_use_user_id": runtime.user.id, "feed_original_recipe_replay": True,
        "use_model_key": "nano-banana-pro-vip" if entrypoint in {"menu", "set"} else "nano-banana-pro",
        "prompt_multi_ref_file_ids": file_ids[:3] if entrypoint == "collect" else file_ids,
        "prompt_multi_ref_max": 14,
    })
    call = callback("pmr:m:nano-banana-pro")
    if entrypoint == "collect":
        message = SimpleNamespace(photo=[SimpleNamespace(file_id=file_ids[-1], file_size=10)], answer=AsyncMock())
        await repeat_reference_marketplace._collect_prompt_reference(message, runtime.session, runtime.user, state, call.bot)
        assert state.data["prompt_multi_ref_file_ids"] == file_ids
        assert "<b>4/4</b>" in message.answer.await_args.args[0]
    elif entrypoint == "menu":
        await repeat_reference_marketplace._model_menu(call, runtime.session, state)
        markup = call.message.answer.await_args.kwargs["reply_markup"]
        assert "pmr:m:nano-banana-pro" in [button.callback_data for row in markup.inline_keyboard for button in row]
    elif entrypoint == "set":
        await repeat_reference_marketplace._set_model(call, runtime.session, state)
        assert state.data["use_model_key"] == "nano-banana-pro"
        assert state.data["prompt_multi_ref_file_ids"] == file_ids
    else:
        await repeat_reference_marketplace._run(call, runtime.session, runtime.user, state, call.bot)
        expected = REFS[:3]
        assert runtime.provider.await_args.kwargs["image_url"] == expected
        copied = runtime.created[-1]
        assert json.loads(copied.reference_file_ids) == file_ids
        assert await image_gen._session_reference_url(call.bot, copied) == [SOURCE, *REFS[:3]]
        runtime.generation.prompt = repo.create_generation.await_args.args[4]
        runtime.generation.input_params = json.dumps(repo.create_generation.await_args.kwargs["input_params"])
        monkeypatch.setattr(repo, "get_last_session_generation", AsyncMock(return_value=runtime.generation))
        monkeypatch.setattr(image_gen, "safe_edit_message", AsyncMock())
        monkeypatch.setattr(image_gen, "_resolve_image_session", AsyncMock(return_value=(copied, 99)))
        call.data = "img_session:repeat:99"
        await image_gen.cb_image_session_repeat(call, runtime.session, state, runtime.user, call.bot)
        await image_gen.cb_image_repeat_launch(call, runtime.session, state, runtime.user, call.bot)
        assert runtime.provider.await_count == 2
        assert runtime.provider.await_args.kwargs["image_url"] == expected
    use.assert_not_awaited()


@pytest.mark.parametrize("entrypoint", ["safe", "legacy"])
async def test_repeat_open_resolution_failure_keeps_previous_series_and_state(repeat_runtime, monkeypatch, entrypoint):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    monkeypatch.setattr(image_gen, "_session_reference_url", AsyncMock(
        side_effect=image_gen.ImageReferenceUnavailable(),
    ))
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=runtime.active))
    runtime.generation.image_session_id = runtime.active.id
    state = RepeatState({"image_session_id": runtime.active.id, "ref_file_ids": ["saved-file"]})
    before = dict(state.data)
    call = callback("repeat_image_img_99")
    if entrypoint == "safe":
        await repeat_safe.open_repeat(call, runtime.session, state, runtime.user, call.bot)
    else:
        handled = await repeat_references._begin_repeat_collection(
            call=call, state=state, bot=call.bot, session=runtime.session, db_user=runtime.user, generation=runtime.generation,
            source_session=runtime.active, reuse_session=True, source_feed_gen_id=None,
        )
        assert handled is True
    assert state.data == before
    assert runtime.active.status == ImageSessionStatus.active
    assert runtime.created == []
    runtime.session.commit.assert_not_awaited()
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()


@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2", "seedream/4.5-edit"])
@pytest.mark.parametrize("available", [False, True])
@pytest.mark.parametrize("bound_alias", [False, True])
async def test_clear_repeat_keeps_only_available_protected_scene(repeat_runtime, monkeypatch, model, available, bound_alias):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.model = model
    runtime.generation.source_feed_gen_id = 77
    from core.feed_remix_prompt import (
        FEED_REMIX_CONTEXT_KEY,
        build_feed_image_prompt,
        feed_image_remix_context,
    )

    runtime.generation.prompt = build_feed_image_prompt(has_user_references=True, has_source_media=True)
    selected = "https://example.test/second-scene.jpg"
    runtime.generation.input_params = {FEED_REMIX_CONTEXT_KEY: feed_image_remix_context(
        77, runtime.generation.prompt, source_image_url=selected,
    )}
    runtime.source.result_urls = json.dumps([SOURCE, selected])
    source_refs = [selected]
    if bound_alias:
        from bot.utils.feed_media import feed_source_output_id
        from core.config import settings

        monkeypatch.setattr(settings, "WEB_PUBLIC_URL", "https://app.example.test")
        source_refs = [selected, f"https://app.example.test/api/v1/feed/77/display.webp?index=1&output_id={feed_source_output_id(runtime.source, selected)}"]
    state = RepeatState({
        "repeat_generation_id": 99, "repeat_parent_generation_id": 99,
        "repeat_source_feed_gen_id": 77, "repeat_model_key": model,
        "repeat_prompt": runtime.generation.prompt,
        "repeat_max_refs": repeat_references._repeat_max_refs(model),
        "repeat_reference_required": image_gen._requires_reference_image(model),
        "repeat_base_reference_urls": [REFS[0], *source_refs],
        "repeat_new_reference_file_ids": ["new-user-photo"],
        "repeat_source_reference_file_ids": ["old-user-photo"],
        "repeat_source_reference_url": REFS[0], "repeat_mode": "image",
    })
    monkeypatch.setattr(repeat_references, "public_url_is_available", lambda url: available if url == selected else True)
    call = callback("repeat_refs:clear")
    handler = next(item for router in image_gen.router.chain_tail for item in router.callback_query.handlers if item.callback is repeat_references._repeat_refs_clear)
    await handler.call(call, state=state, session=runtime.session, db_user=runtime.user, bot=call.bot)

    assert state.data["repeat_reference_count"] == 0
    assert state.data["repeat_base_reference_urls"] == []
    assert state.data["repeat_new_reference_file_ids"] == []
    assert state.data["repeat_source_reference_file_ids"] == []
    await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)
    runtime.provider.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()


@pytest.mark.parametrize("model", ["nano-banana-pro", "seedream/4.5-edit"])
@pytest.mark.parametrize("protected", [False, True])
async def test_run_repeat_required_reference_uses_actual_source_candidate(repeat_runtime, model, protected):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.model = model
    runtime.generation.source_feed_gen_id = 77 if protected else None
    runtime.generation.prompt = runtime.source.prompt if protected else "my visible prompt"
    state = RepeatState({
        "repeat_generation_id": 99, "repeat_parent_generation_id": 99,
        "repeat_model_key": model, "repeat_base_reference_urls": [],
        "repeat_new_reference_file_ids": [], "repeat_mode": "text",
        "repeat_reference_required": image_gen._requires_reference_image(model),
    })
    call = callback("repeat_refs:run")
    await repeat_references._repeat_refs_run(call, runtime.session, state, runtime.user, call.bot)
    if protected or image_gen._requires_reference_image(model):
        assert runtime.created == []
        runtime.provider.assert_not_awaited()
        repo.charge_image_generation.assert_not_awaited()
    else:
        runtime.provider.assert_awaited_once()
        assert runtime.provider.await_args.kwargs["image_url"] is None
        assert runtime.created[-1].mode == "text"


@pytest.mark.parametrize("available", [False, True])
async def test_repeat_collection_initial_count_includes_protected_scene(repeat_runtime, monkeypatch, available):
    from bot.handlers import repeat_references

    runtime = repeat_runtime
    runtime.generation.model = "seedream/4.5-edit"
    runtime.generation.source_feed_gen_id = 77
    runtime.generation.prompt = runtime.source.prompt
    runtime.generation.image_session_id = runtime.active.id
    runtime.active.reference_urls = None
    monkeypatch.setattr(repo, "get_image_session", AsyncMock(return_value=runtime.active))
    monkeypatch.setattr(repeat_references, "public_url_is_available", lambda url: available)
    state = RepeatState({"image_session_id": runtime.active.id, "accepted": "previous state"})
    call = callback("regen:image:99")
    await repeat_references._regen_repeat_interceptor(call, runtime.session, state, runtime.user, call.bot)
    assert state.data["repeat_reference_count"] == 0
    assert state.data["repeat_base_reference_urls"] == []
    assert runtime.source.result_url not in str(state.data)
    assert runtime.created == []
    repo.archive_active_image_sessions.assert_not_awaited()
    repo.charge_image_generation.assert_not_awaited()
    runtime.provider.assert_not_awaited()

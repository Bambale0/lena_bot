from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.web import sessions as web_sessions
from bot.handlers import (
    feed,
    image_gen,
    marketplace,
    repeat_reference_marketplace,
    repeat_references,
)
from db import repository as repo
from db.models import (
    Base,
    Generation,
    GenerationStatus,
    GenerationType,
    ImageSession,
    ImageSessionStatus,
    User,
)

SECRET = "synthetic-author-private-prompt-5b184a"
SOURCE_IMAGE = "https://example.test/published-source.jpg"
USER_IMAGE = "https://example.test/uploaded-user-reference.jpg"


class LocalSession:
    """Run repository SQL against isolated SQLite, without an async-driver dependency."""

    def __init__(self, session: Session) -> None:
        self.sync = session
        self.persisted_prompts: list[tuple[str | None, str | None]] = []

    def add(self, value) -> None:
        self.sync.add(value)

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def commit(self) -> None:
        self.sync.commit()
        self.persisted_prompts.extend(
            self.sync.execute(select(ImageSession.base_prompt, ImageSession.last_prompt)).all()
        )

    async def refresh(self, value) -> None:
        self.sync.refresh(value)


@pytest.fixture
def local_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[User.__table__, ImageSession.__table__, Generation.__table__],
    )
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all([
            User(id=42, tg_id=4200, credits=100, referral_code="synthetic-reader"),
            User(id=99, tg_id=9900, credits=100, referral_code="synthetic-author"),
            Generation(
                id=77, user_id=99, model="nano-banana-2", gen_type=GenerationType.image,
                prompt=SECRET, result_url=SOURCE_IMAGE, is_public_feed=True,
                status=GenerationStatus.done,
            ),
        ])
        sync.commit()
        yield LocalSession(sync)
    engine.dispose()


@pytest.fixture
def feed_launch(local_session, monkeypatch):
    charge = AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=4))
    generate = AsyncMock(return_value=SimpleNamespace(task_id="synthetic-task", is_async=True))
    monkeypatch.setattr(repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr(repo, "charge_image_generation", charge)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(image_gen.image_service, "generate_image", generate)
    mirror = AsyncMock(return_value=USER_IMAGE)
    monkeypatch.setattr("api.public_files.mirror_telegram_file", mirror)
    monkeypatch.setattr(repeat_reference_marketplace, "mirror_telegram_file", mirror)
    state = AsyncMock()
    data = {
        "feed_use_prompt": SECRET,
        "feed_use_gen_id": 77,
        "use_model_key": "nano-banana-2",
        "prompt_multi_ref_file_ids": ["synthetic-reference"],
    }
    state.get_data.return_value = data
    message = AsyncMock()
    message.photo = [SimpleNamespace(file_id="synthetic-reference", file_size=10)]
    call = SimpleNamespace(message=message, answer=AsyncMock())
    return SimpleNamespace(
        session=local_session, charge=charge, generate=generate, mirror=mirror,
        state=state, data=data, message=message, call=call,
        user=local_session.sync.get(User, 42),
    )


async def _run_feed_reference(launch, entrypoint: str) -> None:
    if entrypoint == "single":
        await marketplace.fsm_prompt_use_reference(
            launch.message, launch.session, launch.user, launch.state, AsyncMock(),
        )
    else:
        await repeat_reference_marketplace._run(
            launch.call, launch.session, launch.user, launch.state, AsyncMock(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["single", "multi"])
@pytest.mark.parametrize("failure", ["reference_limit", "missing_public_media"])
async def test_rejected_feed_reference_never_persists_or_serializes_author_prompt(
    feed_launch, entrypoint, failure,
):
    if failure == "reference_limit":
        feed_launch.data["use_model_key"] = "qwen/image-edit"
    else:
        source = feed_launch.session.sync.get(Generation, 77)
        source.result_url = None
        await feed_launch.session.commit()

    await _run_feed_reference(feed_launch, entrypoint)

    feed_launch.charge.assert_not_awaited()
    feed_launch.generate.assert_not_awaited()
    assert feed_launch.session.sync.scalars(
        select(Generation).where(Generation.user_id == 42)
    ).all() == []
    # Inspect every committed version, including the intermediate session before
    # core launch validation; clearing it after launch leaves a disclosure window.
    assert all(
        SECRET not in (base or "") and SECRET not in (last or "")
        for base, last in feed_launch.session.persisted_prompts
    )
    active = await web_sessions.active_image_session(feed_launch.session, feed_launch.user)
    if entrypoint == "multi" and failure == "reference_limit":
        # Capacity now rejects before a session exists, which also closes the
        # intermediate-persistence window this regression protects.
        assert active["data"] is None
        assert feed_launch.session.sync.scalars(select(ImageSession)).all() == []
        feed_launch.mirror.assert_not_awaited()
        assert feed_launch.call.answer.await_args.kwargs["show_alert"] is True
        return
    assert active["data"]["base_prompt"] is None
    assert active["data"]["last_prompt"] is None
    archived = await web_sessions.archive_image_session(
        active["data"]["id"], feed_launch.session, feed_launch.user,
    )
    assert archived["data"]["base_prompt"] is None
    assert archived["data"]["last_prompt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["single", "multi"])
@pytest.mark.parametrize("source_id", [None, 0, "", "invalid", -1, True])
async def test_feed_reference_without_valid_source_provenance_stops_before_session_creation(
    feed_launch, entrypoint, source_id,
):
    feed_launch.data["feed_use_gen_id"] = source_id

    await _run_feed_reference(feed_launch, entrypoint)

    assert feed_launch.session.sync.scalars(select(ImageSession)).all() == []
    assert feed_launch.session.sync.scalars(
        select(Generation).where(Generation.user_id == 42)
    ).all() == []
    feed_launch.charge.assert_not_awaited()
    feed_launch.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_multi_reference_does_not_report_a_successful_launch(feed_launch):
    feed_launch.data["use_model_key"] = "qwen/image-edit"

    await _run_feed_reference(feed_launch, "multi")

    feed_launch.generate.assert_not_awaited()
    assert feed_launch.call.answer.await_args.kwargs["show_alert"] is True
    assert feed_launch.session.sync.scalars(select(ImageSession)).all() == []
    feed_launch.mirror.assert_not_awaited()
    assert "Запущено" not in str(feed_launch.call.answer.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["single", "multi"])
async def test_successful_feed_reference_stays_protected_without_session_secret(feed_launch, entrypoint):
    await _run_feed_reference(feed_launch, entrypoint)

    feed_launch.generate.assert_awaited_once()
    assert SECRET not in feed_launch.generate.await_args.args[1]
    generation = feed_launch.session.sync.scalars(
        select(Generation).where(Generation.user_id == 42)
    ).one()
    assert generation.source_feed_gen_id == 77
    assert SECRET not in generation.prompt
    assert all(
        SECRET not in (base or "") and SECRET not in (last or "")
        for base, last in feed_launch.session.persisted_prompts
    )
    active = await web_sessions.active_image_session(feed_launch.session, feed_launch.user)
    assert active["data"]["prompt_hidden"] is True
    assert active["data"]["prompt_actions_allowed"] is False
    assert active["data"]["base_prompt"] is None
    assert active["data"]["last_prompt"] is None
    archived = await web_sessions.archive_image_session(
        active["data"]["id"], feed_launch.session, feed_launch.user,
    )
    assert archived["data"]["prompt_hidden"] is True
    assert archived["data"]["base_prompt"] is None
    assert archived["data"]["last_prompt"] is None


async def _saved_session(local_session, *, protected: bool, later_ordinary: bool = False):
    image_session = await repo.create_image_session(
        session=local_session, user_id=42, model="nano-banana-2", mode="image",
        aspect_ratio="1:1", quality="2K", count=1,
        base_prompt=SECRET if protected else "my ordinary user prompt",
        prompt_provenance=None if protected else "user_supplied",
    )
    now = datetime.now(timezone.utc)
    local_session.add(Generation(
        user_id=42, image_session_id=image_session.id, model=image_session.model,
        gen_type=GenerationType.image, prompt=image_session.base_prompt,
        source_feed_gen_id=77 if protected else None, status=GenerationStatus.done,
        created_at=now - timedelta(seconds=1),
    ))
    if later_ordinary:
        local_session.add(Generation(
            user_id=42, image_session_id=image_session.id, model=image_session.model,
            gen_type=GenerationType.image, prompt="later ordinary prompt",
            status=GenerationStatus.done, created_at=now,
        ))
    await local_session.commit()
    return image_session


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["active", "archive"])
@pytest.mark.parametrize("later_ordinary", [False, True])
async def test_session_serialization_masks_historical_protected_prompts(
    local_session, endpoint, later_ordinary,
):
    image_session = await _saved_session(local_session, protected=True, later_ordinary=later_ordinary)
    user = local_session.sync.get(User, 42)

    if endpoint == "active":
        response = await web_sessions.active_image_session(local_session, user)
    else:
        response = await web_sessions.archive_image_session(image_session.id, local_session, user)

    assert response["data"]["base_prompt"] is None
    assert response["data"]["last_prompt"] is None
    assert response["data"]["prompt_hidden"] is True
    assert response["data"]["prompt_actions_allowed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["active", "archive"])
async def test_ordinary_session_prompts_remain_visible(local_session, endpoint):
    image_session = await _saved_session(local_session, protected=False)
    user = local_session.sync.get(User, 42)

    if endpoint == "active":
        response = await web_sessions.active_image_session(local_session, user)
    else:
        response = await web_sessions.archive_image_session(image_session.id, local_session, user)

    assert response["data"]["base_prompt"] == "my ordinary user prompt"
    assert response["data"]["last_prompt"] == "my ordinary user prompt"
    assert response["data"]["prompt_hidden"] is False
    assert response["data"]["prompt_actions_allowed"] is True


@pytest.mark.asyncio
async def test_archive_session_preserves_owner_boundary(local_session):
    image_session = await _saved_session(local_session, protected=True)

    response = await web_sessions.archive_image_session(
        image_session.id, local_session, local_session.sync.get(User, 99),
    )

    assert response.status_code == 404
    assert image_session.status == ImageSessionStatus.active


async def _owned_result(local_session, *, protected=True, public=False, model="nano-banana-2"):
    generation = Generation(
        id=88, user_id=42, model=model, gen_type=GenerationType.image,
        prompt=SECRET if protected else "my ordinary user prompt",
        source_feed_gen_id=77 if protected else None,
        is_public_feed=public, status=GenerationStatus.done,
        result_url="https://example.test/own-result.jpg",
    )
    local_session.add(generation)
    await local_session.commit()
    return generation


@pytest.mark.asyncio
@pytest.mark.parametrize("owned", [False, True])
async def test_feed_remix_preparation_never_persists_protected_prompt(feed_launch, owned):
    generation_id = 77
    if owned:
        generation_id = (await _owned_result(feed_launch.session)).id
    feed_launch.call.data = f"feed:remix:{generation_id}"

    await feed.cb_feed_remix(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state,
    )

    active = await web_sessions.active_image_session(feed_launch.session, feed_launch.user)
    assert active["data"]["base_prompt"] is None
    assert active["data"]["last_prompt"] is None
    assert all(
        SECRET not in (base or "") and SECRET not in (last or "")
        for base, last in feed_launch.session.persisted_prompts
    )
    assert feed_launch.state.update_data.await_args.kwargs["source_feed_gen_id"] == 77
    feed_launch.charge.assert_not_awaited()
    feed_launch.generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ["private", "unfinished", "video"])
async def test_feed_remix_cannot_prepare_an_unavailable_foreign_source(feed_launch, unavailable):
    source = feed_launch.session.sync.get(Generation, 77)
    if unavailable == "private":
        source.is_public_feed = False
    elif unavailable == "unfinished":
        source.status = GenerationStatus.processing
    else:
        source.gen_type = GenerationType.video
    await feed_launch.session.commit()
    feed_launch.call.data = "feed:remix:77"

    await feed.cb_feed_remix(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state,
    )

    assert feed_launch.session.sync.scalars(select(ImageSession)).all() == []
    feed_launch.state.set_state.assert_not_awaited()
    feed_launch.charge.assert_not_awaited()
    feed_launch.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_feed_remix_keeps_owned_private_ordinary_prompt(feed_launch):
    generation = await _owned_result(feed_launch.session, protected=False)
    feed_launch.call.data = f"feed:remix:{generation.id}"

    await feed.cb_feed_remix(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state,
    )

    image_session = feed_launch.session.sync.scalars(select(ImageSession)).one()
    assert image_session.base_prompt == "my ordinary user prompt"
    assert image_session.last_prompt == "my ordinary user prompt"
    assert feed_launch.state.update_data.await_args.kwargs["source_feed_gen_id"] is None
    assert getattr(image_session, "prompt_provenance", None) == "user_supplied"


@pytest.mark.asyncio
@pytest.mark.parametrize("public", [False, True])
async def test_feed_again_never_persists_protected_prompt_before_launch(feed_launch, public):
    generation = await _owned_result(feed_launch.session, public=public)
    feed_launch.call.data = f"feed:again:{generation.id}"

    await feed.cb_feed_again(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state, AsyncMock(),
    )

    assert all(
        SECRET not in (base or "") and SECRET not in (last or "")
        for base, last in feed_launch.session.persisted_prompts
    )
    created = feed_launch.session.sync.scalars(
        select(Generation).where(Generation.id > 88)
    ).one()
    assert created.source_feed_gen_id == 77


@pytest.mark.asyncio
async def test_feed_again_keeps_ordinary_user_prompt(feed_launch):
    generation = await _owned_result(feed_launch.session, protected=False)
    feed_launch.call.data = f"feed:again:{generation.id}"

    await feed.cb_feed_again(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state, AsyncMock(),
    )

    image_session = feed_launch.session.sync.scalars(select(ImageSession)).one()
    assert image_session.base_prompt == "my ordinary user prompt"
    assert image_session.last_prompt == "my ordinary user prompt"
    assert feed_launch.generate.await_args.args[1] == "my ordinary user prompt"
    assert getattr(image_session, "prompt_provenance", None) == "user_supplied"


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("state_source_id", [None, 77, 88])
async def test_repeat_reference_constructor_uses_durable_protection_before_rejection(
    feed_launch, reuse, state_source_id,
):
    generation = await _owned_result(feed_launch.session, model="qwen/image-edit")
    image_session = None
    if reuse:
        image_session = await repo.create_image_session(
            session=feed_launch.session, user_id=42, model=generation.model, mode="image",
            aspect_ratio="1:1", quality="basic", count=1, base_prompt=SECRET,
        )
        generation.image_session_id = image_session.id
        await feed_launch.session.commit()
        feed_launch.session.persisted_prompts.clear()
    feed_launch.data.clear()
    feed_launch.data.update(
        repeat_generation_id=88, repeat_parent_generation_id=88,
        repeat_prompt=SECRET, repeat_source_feed_gen_id=state_source_id,
        repeat_base_reference_urls=[USER_IMAGE], repeat_max_refs=1,
        repeat_reuse_session_id=image_session.id if image_session else None,
    )

    await repeat_references._repeat_refs_run(
        feed_launch.call, feed_launch.session, feed_launch.state, feed_launch.user, AsyncMock(),
    )

    feed_launch.charge.assert_not_awaited()
    feed_launch.generate.assert_not_awaited()
    assert all(
        SECRET not in (base or "") and SECRET not in (last or "")
        for base, last in feed_launch.session.persisted_prompts
    )
    stored = feed_launch.session.sync.scalars(select(ImageSession)).one()
    assert stored.base_prompt is None
    assert stored.last_prompt is None


@pytest.mark.asyncio
async def test_repeat_reference_constructor_keeps_ordinary_user_prompt(feed_launch):
    await _owned_result(feed_launch.session, protected=False)
    feed_launch.data.clear()
    feed_launch.data.update(
        repeat_generation_id=88, repeat_parent_generation_id=88,
        repeat_prompt="my ordinary user prompt", repeat_base_reference_urls=[USER_IMAGE],
        repeat_max_refs=3,
    )

    await repeat_references._repeat_refs_run(
        feed_launch.call, feed_launch.session, feed_launch.state, feed_launch.user, AsyncMock(),
    )

    stored = feed_launch.session.sync.scalars(select(ImageSession)).one()
    assert stored.base_prompt == "my ordinary user prompt"
    assert stored.last_prompt == "my ordinary user prompt"
    assert feed_launch.generate.await_args.args[1] == "my ordinary user prompt"
    assert getattr(stored, "prompt_provenance", None) == "user_supplied"


@pytest.mark.asyncio
@pytest.mark.parametrize("input_params", ['{"hidden_prompt": true}', "malformed-json", "[]"])
async def test_feed_remix_never_attests_hidden_or_unknown_owned_prompt(feed_launch, input_params):
    generation = await _owned_result(feed_launch.session, protected=False)
    generation.prompt = SECRET
    generation.input_params = input_params
    await feed_launch.session.commit()
    feed_launch.call.data = f"feed:remix:{generation.id}"

    await feed.cb_feed_remix(
        feed_launch.call, feed_launch.session, feed_launch.user, feed_launch.state,
    )

    stored = feed_launch.session.sync.scalars(select(ImageSession)).one()
    assert stored.base_prompt is None
    assert stored.last_prompt is None
    assert getattr(stored, "prompt_provenance", None) is None

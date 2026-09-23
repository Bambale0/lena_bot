from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import miniapp_routes
from bot.handlers import admin, image_gen
from bot.keyboards.models import image_models_kb
from db import repository
from db.models import GenerationStatus, GenerationType, UserImageModelEntitlement


class FakeState:
    def __init__(self, data: dict | None = None):
        self.data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.data.clear()
        self.state = None


@pytest.mark.asyncio
async def test_effective_image_credits_zero_only_for_entitled_model(monkeypatch) -> None:
    session = AsyncMock()
    check = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(repository, "is_image_model_unlimited", check)

    assert await repository.effective_image_generation_credits(
        session, 7, "nano-banana-2", 4.5
    ) == 0.0
    assert await repository.effective_image_generation_credits(
        session, 7, "gpt-image-2-text-to-image", 4.5
    ) == 4.5


@pytest.mark.asyncio
async def test_set_unlimited_image_models_creates_auditable_rows() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    updated = await repository.set_image_models_unlimited_for_users(
        session,
        user_ids=[10, 20, 10],
        model_key="nano-banana-2",
        enabled=True,
        admin_tg_id=999,
    )

    assert updated == 2
    assert session.add.call_count == 2
    rows = [call.args[0] for call in session.add.call_args_list]
    assert {row.user_id for row in rows} == {10, 20}
    assert all(row.model_key == "nano-banana-2" for row in rows)
    assert all(row.is_unlimited is True for row in rows)
    assert all(row.granted_by_tg_id == 999 for row in rows)
    session.commit.assert_awaited_once()


def test_entitlement_model_has_unique_user_model_pair() -> None:
    unique_constraints = {
        constraint.name
        for constraint in UserImageModelEntitlement.__table__.constraints
        if constraint.name
    }
    assert "uq_user_image_model_entitlements_user_model" in unique_constraints


def test_admin_menu_exposes_unlimited_image_control() -> None:
    callbacks = {
        button.callback_data
        for row in admin.admin_menu_kb().inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "adm:unlimited_images" in callbacks


@pytest.mark.asyncio
async def test_admin_resolves_multiple_telegram_ids_and_reports_missing() -> None:
    message = SimpleNamespace(
        text="111, 222\n333",
        answer=AsyncMock(),
    )
    state = FakeState()
    model = SimpleNamespace(
        id=5,
        model_key="nano-banana-2",
        display_name="Nano Banana 2",
        gen_type=GenerationType.image,
        is_active=True,
    )
    users = {
        111: SimpleNamespace(id=10, tg_id=111),
        222: SimpleNamespace(id=20, tg_id=222),
    }

    repo_stub = SimpleNamespace(
        get_user_by_tg_id=AsyncMock(side_effect=lambda _session, tg_id: users.get(tg_id)),
        get_all_model_costs=AsyncMock(return_value=[model]),
        get_unlimited_image_model_keys_for_users=AsyncMock(
            return_value={10: set(), 20: set()}
        ),
    )
    with patch("bot.handlers.admin.repo", new=repo_stub):
        await admin.handle_unlimited_image_tg_ids(message, state, AsyncMock())

    assert state.data["unlimited_image_user_ids"] == [10, 20]
    assert state.data["unlimited_image_tg_ids"] == [111, 222]
    assert state.data["unlimited_image_missing_tg_ids"] == [333]
    rendered = message.answer.await_args.args[0]
    assert "111, 222" in rendered
    assert "333" in rendered


@pytest.mark.asyncio
async def test_admin_toggle_enables_model_for_all_selected_users() -> None:
    model = SimpleNamespace(
        id=5,
        model_key="nano-banana-2",
        display_name="Nano Banana 2",
        gen_type=GenerationType.image,
        is_active=True,
    )
    call = SimpleNamespace(
        data="adm:unlim:toggle:5:0",
        from_user=SimpleNamespace(id=999),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    state = FakeState({
        "unlimited_image_user_ids": [10, 20],
        "unlimited_image_tg_ids": [111, 222],
        "unlimited_image_missing_tg_ids": [],
    })
    set_access = AsyncMock(return_value=2)
    mappings = [
        {10: {"nano-banana-2"}, 20: set()},
        {10: {"nano-banana-2"}, 20: {"nano-banana-2"}},
    ]
    repo_stub = SimpleNamespace(
        get_model_cost_by_id=AsyncMock(return_value=model),
        get_unlimited_image_model_keys_for_users=AsyncMock(side_effect=mappings),
        set_image_models_unlimited_for_users=set_access,
        get_all_model_costs=AsyncMock(return_value=[model]),
    )

    with patch("bot.handlers.admin.repo", new=repo_stub):
        await admin.cb_unlimited_image_model_toggle(call, state, AsyncMock())

    set_access.assert_awaited_once()
    assert set_access.await_args.kwargs["user_ids"] == [10, 20]
    assert set_access.await_args.kwargs["model_key"] == "nano-banana-2"
    assert set_access.await_args.kwargs["enabled"] is True
    assert set_access.await_args.kwargs["admin_tg_id"] == 999
    assert "включён" in call.answer.await_args.args[0]


def test_telegram_image_model_keyboard_marks_entitlement() -> None:
    model = SimpleNamespace(
        model_key="nano-banana-2",
        display_name="Nano Banana 2",
        gen_type=GenerationType.image,
        credits=4.0,
    )
    markup = image_models_kb([model], unlimited_model_keys={"nano-banana-2"})
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert any("♾️ Безлимит" in text for text in texts)


@pytest.mark.asyncio
async def test_bot_unlimited_image_skips_debit_and_records_zero_cost() -> None:
    source_message = AsyncMock()
    status_msg = AsyncMock()
    source_message.answer = AsyncMock(return_value=status_msg)
    state = AsyncMock()
    session = AsyncMock()
    db_user = SimpleNamespace(id=42)
    image_session = SimpleNamespace(
        id=7,
        model="wan/2-7-image-pro",
        mode="text",
        aspect_ratio="1:1",
        quality="2K",
        count=1,
        reference_file_id=None,
        reference_file_ids=None,
    )
    generation = SimpleNamespace(id=99)
    spend_credits = AsyncMock(return_value=True)
    create_generation = AsyncMock(return_value=generation)
    repo_stub = SimpleNamespace(
        resolve_image_model_cost=AsyncMock(return_value=SimpleNamespace(credits=4)),
        effective_image_generation_credits=AsyncMock(return_value=0.0),
        count_user_active_generations=AsyncMock(return_value=0),
        spend_credits=spend_credits,
        create_generation=create_generation,
        update_image_session_last_prompt=AsyncMock(),
        update_generation_task=AsyncMock(),
    )

    with (
        patch("bot.handlers.image_gen.repo", new=repo_stub),
        patch(
            "bot.handlers.image_gen.image_service.generate_image",
            AsyncMock(return_value=SimpleNamespace(task_id="task_1")),
        ),
    ):
        ok = await image_gen._launch_session_generation(
            source_message=source_message,
            state=state,
            session=session,
            db_user=db_user,
            image_session=image_session,
            prompt="portrait",
            action_type=image_gen.ImageGenerationAction.initial,
            reference_url=None,
            parent_generation_id=None,
            launching_text="launching",
            queued_text="queued",
        )

    assert ok is True
    spend_credits.assert_not_awaited()
    assert create_generation.await_args.args[5] == 0.0


@pytest.mark.asyncio
async def test_miniapp_model_metadata_marks_unlimited_and_zeroes_quality_prices(monkeypatch) -> None:
    session = AsyncMock()
    user = SimpleNamespace(id=1)
    model = SimpleNamespace(
        model_key="nano-banana-pro",
        display_name="Nano Banana Pro",
        credits=4.0,
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "get_all_model_costs",
        AsyncMock(return_value=[model]),
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "get_user_unlimited_image_model_keys",
        AsyncMock(return_value={"nano-banana-pro"}),
    )

    async def fake_quality_cost(_session, _model_key, *, quality=None):
        return SimpleNamespace(credits=5.0 if quality == "4K" else 4.0)

    monkeypatch.setattr(
        miniapp_routes.repo,
        "resolve_image_model_cost",
        fake_quality_cost,
    )

    models = await miniapp_routes.list_image_models(session=session, user=user)

    assert models[0].is_unlimited is True
    assert models[0].credits == 0.0
    assert set(models[0].quality_prices.values()) == {0.0}


@pytest.mark.asyncio
async def test_miniapp_unlimited_image_skips_debit_and_records_zero_cost(monkeypatch) -> None:
    session = AsyncMock()
    user = SimpleNamespace(
        id=1,
        tg_id=111,
        username="tester",
        full_name="Test",
        credits=0.0,
    )
    spend_credits = AsyncMock(return_value=True)
    captured: dict[str, float] = {}

    async def fake_create_generation(
        _session,
        _user_id,
        model,
        gen_type,
        prompt,
        credits_spent,
        **_kwargs,
    ):
        captured["credits_spent"] = credits_spent
        return SimpleNamespace(
            id=501,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            status=GenerationStatus.processing,
            result_url=None,
            result_urls=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
            source_feed_gen_id=None,
        )

    monkeypatch.setattr(
        miniapp_routes.repo,
        "resolve_image_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=4.0)),
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "effective_image_generation_credits",
        AsyncMock(return_value=0.0),
    )
    monkeypatch.setattr(
        miniapp_routes,
        "_reconcile_user_active_generations",
        AsyncMock(),
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "count_user_active_generations",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(miniapp_routes.repo, "spend_credits", spend_credits)
    monkeypatch.setattr(
        miniapp_routes.repo,
        "create_image_session",
        AsyncMock(return_value=SimpleNamespace(id=77)),
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "create_generation",
        fake_create_generation,
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "update_generation_task",
        AsyncMock(),
    )
    monkeypatch.setattr(
        miniapp_routes.repo,
        "update_image_session_last_prompt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        miniapp_routes,
        "_mark_prompt_used_after_generation",
        AsyncMock(),
    )
    monkeypatch.setattr(
        miniapp_routes.image_service,
        "generate_image",
        AsyncMock(return_value=SimpleNamespace(task_id="img-task", is_async=True)),
    )

    result = await miniapp_routes.create_image_generation(
        miniapp_routes.ImageGenRequest(
            model="nano-banana-pro",
            prompt="portrait",
            quality="2K",
        ),
        session=session,
        user=user,
    )

    spend_credits.assert_not_awaited()
    assert captured["credits_spent"] == 0.0
    assert result.credits_spent == 0.0

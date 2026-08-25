from __future__ import annotations

from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from api import pinterest_service_routes as PSR
from bot.handlers import pinterest_flow as pf
from bot.handlers.pinterest_flow import PinterestFlow
from bot.ui.main_menu import render_main_menu


class FakeState:
    def __init__(self) -> None:
        self.data: dict = {}
        self.current: Optional[str] = None

    async def get_data(self) -> dict:
        return dict(self.data or {})

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def set_state(self, state) -> None:
        self.current = state

    async def clear(self) -> None:
        self.data = {}
        self.current = None


def make_message(*, text: str | None = None, photo: bool = False) -> SimpleNamespace:
    answers: list[dict] = []

    async def answer(*args, **kwargs):
        answers.append({"args": args, "kwargs": kwargs})
        return None

    return SimpleNamespace(
        text=text,
        photo=[SimpleNamespace(file_id="f1", file_size=1)] if photo else None,
        answer=answer,
        answers=answers,
    )


def make_call() -> SimpleNamespace:
    message = SimpleNamespace(
        edit_text=AsyncMock(),
        edit_caption=AsyncMock(),
        answer=AsyncMock(),
    )
    return SimpleNamespace(message=message, answer=AsyncMock())


def complete_state() -> dict:
    return {
        "scene_asset_id": "scene",
        "identity_asset_id": "identity",
        "extra_asset_ids": ["extra-1", "extra-2"],
        "height_cm": 175,
        "weight_kg": 70,
    }


def complete_state_ok(overrides=None):
    base = {
        "scene_asset_id": "s",
        "identity_asset_id": "i",
        "extra_asset_ids": [],
        "height_cm": 175,
        "weight_kg": 70,
    }
    base.update(overrides or {})
    return base


# ── Entry ─────────────────────────────────────────────────────────────────────

def test_menu_places_pinterest_next_to_trends_and_opens_fsm() -> None:
    context = SimpleNamespace(active_image_session=None, balance=100.0, is_admin=True)
    rendered = render_main_menu(context, "ru")
    rows = rendered.reply_markup.inline_keyboard
    trend_row = next(row for row in rows if any(b.callback_data == "menu:trends" for b in row))
    assert [b.text for b in trend_row] == ["👑 Тренды", "📌 Pinterest"]
    assert trend_row[1].callback_data == "menu:pinterest"
    assert trend_row[1].web_app is None


@pytest.mark.asyncio
async def test_open_flow_sets_scene_state() -> None:
    state = FakeState()
    message = make_message()
    await pf.open_pinterest_flow(message, state)
    assert state.current == PinterestFlow.waiting_scene_reference.state
    assert state.data.get("extra_asset_ids") == []
    assert "Повторите фото в стиле Pinterest" in message.answers[0]["args"][0]


# ── Validation (pure helpers) ────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("value", "expected"),
    [("175", 175), ("  170 ", 170), ("120", 120), ("230", 230),
     ("119", None), ("231", None), ("abc", None), ("", None), ("175.5", None)],
)
def test_parse_height(value: str, expected: int | None) -> None:
    assert pf.parse_height(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("70", 70), ("30", 30), ("250", 250), ("29", None), ("251", None), ("abc", None)],
)
def test_parse_weight(value: str, expected: int | None) -> None:
    assert pf.parse_weight(value) == expected


def test_reference_payload_order_scene_identity_extras() -> None:
    payload = pf.reference_asset_ids("scene", "identity", ["extra-1", "extra-2"])
    assert payload == ["scene", "identity", "extra-1", "extra-2"]


def test_reference_payload_dedupes_and_skips_empty() -> None:
    payload = pf.reference_asset_ids("scene", "identity", ["identity", "", "extra"])
    assert payload == ["scene", "identity", "extra"]


@pytest.mark.parametrize(
    ("data", "missing"),
    [
        (dict(complete_state_ok({"height_cm": 175, "weight_kg": 70})), set()),
        (dict(complete_state_ok({"identity_asset_id": "i", "height_cm": 175, "weight_kg": 70}), **{"scene_asset_id": None}), {"scene"}),
        (dict(complete_state_ok({"scene_asset_id": "s", "height_cm": 175, "weight_kg": 70}), **{"identity_asset_id": None}), {"identity"}),
        (dict(complete_state_ok({"scene_asset_id": "s", "identity_asset_id": "i", "weight_kg": 70}), **{"height_cm": None}), {"height"}),
        (dict(complete_state_ok({"scene_asset_id": "s", "identity_asset_id": "i", "height_cm": 175}), **{"weight_kg": None}), {"weight"}),
        ({}, {"scene", "identity", "height", "weight"}),
    ],
)
def test_missing_fields(data: dict, missing: set[str]) -> None:
    assert pf.flow_missing_fields(data) == missing


# ── FSM transitions ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scene_upload(monkeypatch) -> None:
    monkeypatch.setattr(pf, "_best_photo_asset_id", AsyncMock(return_value="scene-asset"))
    state = FakeState()
    message = make_message(photo=True)
    await pf.scene_reference_photo(message, state, bot=AsyncMock(), db_user=SimpleNamespace(id=42))
    assert state.data.get("scene_asset_id") == "scene-asset"
    assert state.current == PinterestFlow.waiting_identity_reference.state
    assert message.answers[0]["args"][0] == "✅ <b>РЕФЕРЕНС добавлен</b>"


@pytest.mark.asyncio
async def test_scene_rejects_non_photo() -> None:
    message = make_message()
    await pf.scene_ask_photo(message)
    assert "изображение" in message.answers[0]["args"][0]


@pytest.mark.asyncio
async def test_identity_upload(monkeypatch) -> None:
    monkeypatch.setattr(pf, "_best_photo_asset_id", AsyncMock(return_value="identity-asset"))
    state = FakeState()
    message = make_message(photo=True)
    await pf.identity_reference_photo(message, state, bot=AsyncMock(), db_user=SimpleNamespace(id=1))
    assert state.data.get("identity_asset_id") == "identity-asset"
    assert state.current == PinterestFlow.waiting_extra_references.state


@pytest.mark.asyncio
async def test_extra_references_collection(monkeypatch) -> None:
    monkeypatch.setattr(pf, "_best_photo_asset_id", AsyncMock(return_value="extra-asset"))
    state = FakeState()
    await state.update_data(scene_asset_id="s", identity_asset_id="i", extra_asset_ids=[])
    message = make_message(photo=True)
    await pf.extra_photo(message, state, bot=AsyncMock(), db_user=SimpleNamespace(id=1))
    assert state.data["extra_asset_ids"] == ["extra-asset"]


@pytest.mark.asyncio
async def test_height_weight_lead_to_confirmation(monkeypatch) -> None:
    state = FakeState()
    await state.update_data(scene_asset_id="s", identity_asset_id="i")

    await pf.height_input(make_message(text="175"), state)
    assert state.data["height_cm"] == 175
    assert state.current == PinterestFlow.waiting_weight.state

    monkeypatch.setattr(pf, "_pinterest_price", AsyncMock(return_value=3.5))
    w_msg = make_message(text="70")
    await pf.weight_input(w_msg, state, session=AsyncMock())
    assert state.data["weight_kg"] == 70
    assert state.current == PinterestFlow.confirmation.state

    last = w_msg.answers[-1]
    text = last["args"][0]
    assert "Рост:\n175 см" in text
    assert "Вес:\n70 кг" in text
    assert "3.5" in text
    kb = last["kwargs"]["reply_markup"].inline_keyboard
    assert any(b.callback_data == "pinterest:confirm" for row in kb for b in row)


@pytest.mark.asyncio
async def test_run_blocked_when_fields_missing(monkeypatch) -> None:
    run = AsyncMock()
    monkeypatch.setattr(pf, "_run_pinterest_service", run)
    state = FakeState()
    await state.update_data(identity_asset_id="i", height_cm=175, weight_kg=70)  # missing scene
    call = make_call()
    await pf.confirm_and_run(call, state, session=AsyncMock(), db_user=SimpleNamespace(id=1))
    run.assert_not_awaited()
    call.answer.assert_awaited_with("Сначала заполните все шаги.", show_alert=True)


# ── Run + payload + delivery ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_runs_and_clears_state(monkeypatch) -> None:
    run = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(pf, "_run_pinterest_service", run)
    state = FakeState()
    await state.update_data(**complete_state())
    call = make_call()
    await pf.confirm_and_run(call, state, session=AsyncMock(), db_user=SimpleNamespace(id=1))

    run.assert_awaited_once()
    # FSM cleared after success so a repeat run never reuses old references.
    assert state.current is None and state.data == {}


@pytest.mark.asyncio
async def test_run_builds_payload_in_correct_order(monkeypatch) -> None:
    from api import pinterest_service_routes as PSR

    launch = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(PSR, "launch_pinterest_service", launch)
    await pf._run_pinterest_service(
        AsyncMock(),
        SimpleNamespace(id=1),
        complete_state(),
        idempotency_key="pinterest-tg-12345678",
    )
    launch.assert_awaited_once()
    kwargs = launch.await_args.kwargs
    assert kwargs["reference_asset_ids"] == ["scene", "identity", "extra-1", "extra-2"]
    assert kwargs["height_cm"] == 175
    assert kwargs["weight_kg"] == 70


@pytest.mark.asyncio
async def test_confirm_success_announces_chat_delivery(monkeypatch) -> None:
    monkeypatch.setattr(pf, "_run_pinterest_service", AsyncMock(return_value={"ok": True}))
    state = FakeState()
    await state.update_data(**complete_state())
    call = make_call()
    await pf.confirm_and_run(call, state, session=AsyncMock(), db_user=SimpleNamespace(id=1))
    text = call.message.answer.await_args.args[0]
    assert "придут в этот чат" in text


@pytest.mark.asyncio
async def test_confirm_error_clears_state() -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("provider down")
    state = FakeState()
    await state.update_data(**complete_state())
    call = make_call()
    await pf.confirm_and_run(call, state, session=AsyncMock(), db_user=SimpleNamespace(id=1))
    assert state.data == {} and state.current is None


@pytest.mark.asyncio
async def test_launch_reuses_miniapp_delivery_surface(monkeypatch) -> None:
    from api import miniapp_routes

    captured: dict = {}

    async def fake_create(*, body, session, user, surface):
        captured["surface"] = surface
        captured["prompt_id"] = body.prompt_id
        captured["reference_url"] = body.reference_url
        captured["reference_urls"] = list(getattr(body, "reference_urls", []) or [])
        return SimpleNamespace(id=555, model_dump=lambda: {"id": 555})

    monkeypatch.setattr(PSR, "_service_price_credits", AsyncMock(return_value=2.0))
    monkeypatch.setattr(PSR, "_validate_runtime", AsyncMock())
    monkeypatch.setattr(PSR, "_find_idempotent_run", AsyncMock(return_value=None))
    monkeypatch.setattr(PSR, "_patch_service_snapshot", AsyncMock())
    monkeypatch.setattr(
        PSR, "verify_uploaded_asset",
        lambda aid, **_k: {"url": f"https://x/{aid}", "kind": "image"},
    )
    monkeypatch.setattr(PSR, "_scene_matched_ratio", lambda _u: "9:16")
    monkeypatch.setattr(miniapp_routes, "create_image_generation", fake_create)

    session = SimpleNamespace(refresh=AsyncMock())
    result = await PSR.launch_pinterest_service(
        session,
        SimpleNamespace(id=42, credits=10),
        idempotency_key="pinterest-tg-abcdef0123456789",
        reference_asset_ids=["scene", "identity", "extra"],
        height_cm=175,
        weight_kg=70,
    )
    assert result["ok"] is True
    assert captured["surface"] == "miniapp"
    assert captured["prompt_id"] is None  # no published prompt recipe
    assert captured["reference_url"] == "https://x/scene"
    assert captured["reference_urls"] == ["https://x/identity", "https://x/extra"]
    # miniapp surface → Telegram delivery is not suppressed (result + source sent).
    stored_task = miniapp_routes.task_id_for_surface("provider-task-9", captured["surface"])
    assert miniapp_routes.is_web_task_id(stored_task) is False

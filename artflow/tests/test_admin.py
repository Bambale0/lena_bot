"""Тесты хендлеров admin — админ-панель, статистика, прайс, бан, рассылка."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from aiogram.types import CallbackQuery, Message

from bot.handlers import admin
from db.models import PricePlan, GenerationType, User
from tests.factories import make_callback, make_message


# ── /admin command ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_admin_opens_menu() -> None:
    msg = make_message(text="/admin")
    msg.answer = AsyncMock()
    await admin.cmd_admin(msg)
    msg.answer.assert_awaited_once()


# ── menu:admin ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_admin_menu() -> None:
    call = make_callback(data="menu:admin")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_admin_menu(call, mock_state)
    mock_state.clear.assert_called_once()


# ── adm:back ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_admin_back() -> None:
    call = make_callback(data="adm:back")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_admin_back(call, mock_state)
    call.message.edit_text.assert_awaited_once()
    assert "Панель администратора" in call.message.edit_text.call_args[0][0]


# ── adm:stats ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_stats() -> None:
    call = make_callback(data="adm:stats")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_session = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(
        count_users=AsyncMock(return_value=42),
        count_generations_today=AsyncMock(return_value=7),
        get_revenue_today=AsyncMock(return_value=1234.5),
    )):
        await admin.cb_stats(call, mock_session)
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0]
    assert "Статистика" in text
    assert "42" in text


# ── adm:referrals ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_referrals_no_leaders() -> None:
    call = make_callback(data="adm:referrals")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(get_referral_leaders=AsyncMock(return_value=[]))):
        await admin.cb_referrals(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_referrals_with_leaders() -> None:
    call = make_callback(data="adm:referrals")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_user = SimpleNamespace(id=1, username="leader", tg_id=100, full_name="Leader")
    mock_leader = SimpleNamespace(user=mock_user, l1_count=3, l2_count=5, l3_count=10, total_count=18)
    with patch("bot.handlers.admin.repo", AsyncMock(get_referral_leaders=AsyncMock(return_value=[mock_leader]))):
        await admin.cb_referrals(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:ref_user: ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_referral_user_not_found() -> None:
    call = make_callback(data="adm:ref_user:999")
    call.answer = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(get_user_by_id=AsyncMock(return_value=None))):
        await admin.cb_referral_user(call, AsyncMock())
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cb_referral_user_found() -> None:
    call = make_callback(data="adm:ref_user:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_user = SimpleNamespace(id=1, username="leader", tg_id=100, full_name="Leader", credits=100, referral_code="abc")
    with patch("bot.handlers.admin.repo", AsyncMock(get_user_by_id=AsyncMock(return_value=mock_user), count_user_referrals=AsyncMock(return_value=(1, 2, 3)))):
        await admin.cb_referral_user(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:ref_level: ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_referral_level_empty() -> None:
    call = make_callback(data="adm:ref_level:1:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_user = SimpleNamespace(id=1, username="leader", tg_id=200)
    with patch("bot.handlers.admin.repo", AsyncMock(
        get_user_by_id=AsyncMock(return_value=mock_user),
        get_referral_children=AsyncMock(return_value=[]),
    )):
        await admin.cb_referral_level(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    assert "нет пользователей" in call.message.edit_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cb_referral_level_with_children() -> None:
    call = make_callback(data="adm:ref_level:1:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    # mock_user — родитель с tg_id
    mock_user = SimpleNamespace(id=1, username="leader", tg_id=200, full_name="LeaderName")
    # mock_child — объект с .user (SimpleNamespace с нужными полями)
    mock_child_user = SimpleNamespace(id=2, username="kid", tg_id=300, full_name="KidName", credits=100)
    mock_child = SimpleNamespace(user=mock_child_user, generations_count=5, paid_rub=500)
    with patch("bot.handlers.admin.repo", AsyncMock(
        get_user_by_id=AsyncMock(return_value=mock_user),
        get_referral_children=AsyncMock(return_value=[mock_child]),
    )):
        await admin.cb_referral_level(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:withdrawals ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_withdrawals_empty() -> None:
    call = make_callback(data="adm:withdrawals")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(get_pending_withdrawal_requests=AsyncMock(return_value=[]))):
        await admin.cb_withdrawals(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    assert "Нет ожидающих" in call.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_withdrawals_with_requests() -> None:
    call = make_callback(data="adm:withdrawals")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_req = SimpleNamespace(id=1, amount_rub=1500.0, payout_details="Сбер", status=SimpleNamespace(value="pending"))
    mock_user = SimpleNamespace(id=42, username="user1", tg_id=123)
    mock_view = SimpleNamespace(request=mock_req, user=mock_user)
    with patch("bot.handlers.admin.repo", AsyncMock(get_pending_withdrawal_requests=AsyncMock(return_value=[mock_view]))):
        await admin.cb_withdrawals(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:wd:view: ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_withdrawal_view() -> None:
    call = make_callback(data="adm:wd:view:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_req = SimpleNamespace(id=1, amount_rub=1500.0, payout_details="Сбер", status=SimpleNamespace(value="pending"))
    mock_user = SimpleNamespace(id=42, username="user1", tg_id=123, full_name="Test")
    mock_view = SimpleNamespace(request=mock_req, user=mock_user)
    with patch("bot.handlers.admin.repo", AsyncMock(get_withdrawal_request=AsyncMock(return_value=mock_view))):
        await admin.cb_withdrawal_view(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:wd:approve / reject ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_withdrawal_approve() -> None:
    call = make_callback(data="adm:wd:approve:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_req = SimpleNamespace(id=1, amount_rub=1500.0, status=SimpleNamespace(value="pending"))
    mock_user = SimpleNamespace(id=42, username="user1", tg_id=123, full_name="Test")
    mock_view = SimpleNamespace(request=mock_req, user=mock_user)
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(set_withdrawal_status=AsyncMock(return_value=mock_view))):
        await admin.cb_withdrawal_decide(call, mock_session, bot=mock_bot)
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0].lower()
    assert "подтверждена" in text


@pytest.mark.asyncio
async def test_cb_withdrawal_reject() -> None:
    call = make_callback(data="adm:wd:reject:1")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_req = SimpleNamespace(id=1, amount_rub=1500.0, status=SimpleNamespace(value="pending"))
    mock_user = SimpleNamespace(id=42, username="user1", tg_id=123, full_name="Test")
    mock_view = SimpleNamespace(request=mock_req, user=mock_user)
    mock_session = AsyncMock()
    mock_bot = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(set_withdrawal_status=AsyncMock(return_value=mock_view))):
        await admin.cb_withdrawal_decide(call, mock_session, bot=mock_bot)
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0].lower()
    assert "отклонена" in text


# ── adm:price ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_price_list() -> None:
    call = make_callback(data="adm:price")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_plan = SimpleNamespace(
        key="credits_500", label="500 💋", credits=500, price_rub=799.0,
        is_active=True, sort_order=1,
    )
    mock_result = MagicMock()
    mock_result.scalars = MagicMock()
    mock_result.scalars.all = AsyncMock(return_value=[mock_plan])
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("bot.handlers.admin.select", return_value=mock_result):
        await admin.cb_price_list(call, mock_session)
    call.message.edit_text.assert_awaited_once()


# ── adm:price_edit: ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_price_edit() -> None:
    call = make_callback(data="adm:price_edit:credits_500")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_plan = SimpleNamespace(key="credits_500", label="500 💋", credits=500, price_rub=799.0, is_active=True, sort_order=1)
    with patch("bot.handlers.admin.repo", AsyncMock(get_price_plan_by_key=AsyncMock(return_value=mock_plan))):
        await admin.cb_price_edit(call, AsyncMock(), AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:price_toggle: ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_price_toggle() -> None:
    call = make_callback(data="adm:price_toggle:credits_500")
    call.answer = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(toggle_price_plan=AsyncMock(return_value=False))):
        with patch("bot.handlers.admin.cb_price_list", new_callable=AsyncMock) as mock_list:
            await admin.cb_price_toggle(call, AsyncMock())
    call.answer.assert_awaited_once()


# ── adm:price_new — start ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_price_new_start() -> None:
    call = make_callback(data="adm:price_new")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_price_new_start(call, mock_state)
    mock_state.set_state.assert_called_with(admin.AdminFSM.new_price_credits)


# ── handle_new_price_credits ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_new_price_credits_valid() -> None:
    msg = make_message(text="500")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.handle_new_price_credits(msg, mock_state)
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_called_with(admin.AdminFSM.new_price_rub)


@pytest.mark.asyncio
async def test_handle_new_price_credits_invalid() -> None:
    msg = make_message(text="abc")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.handle_new_price_credits(msg, mock_state)
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_new_price_credits_zero() -> None:
    msg = make_message(text="0")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.handle_new_price_credits(msg, mock_state)
    msg.answer.assert_awaited_once()


# ── handle_new_price_rub ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_new_price_rub_valid() -> None:
    msg = make_message(text="799")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"new_price_credits": 500})
    mock_plan = SimpleNamespace(key="credits_500", label="500 💋", credits=500, price_rub=799.0, sort_order=1)

    # mock max sort_order query result
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=5)
    mock_session.execute = AsyncMock(return_value=mock_scalar)

    with patch("bot.handlers.admin.repo", AsyncMock(
        get_price_plan_by_key=AsyncMock(return_value=None),
        upsert_price_plan=AsyncMock(return_value=mock_plan),
    )):
        await admin.handle_new_price_rub(msg, mock_session, mock_state)
    msg.answer.assert_awaited_once()
    assert "Новый тариф создан" in msg.answer.call_args[0][0]


# ── handle_price_rub ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_price_rub_valid() -> None:
    msg = make_message(text="599")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"edit_plan_key": "credits_500"})
    mock_plan = SimpleNamespace(key="credits_500", label="500 💋", credits=500, price_rub=599.0, is_active=True, sort_order=1)
    with patch("bot.handlers.admin.repo", AsyncMock(get_price_plan_by_key=AsyncMock(return_value=mock_plan))):
        await admin.handle_price_rub(msg, mock_session, mock_state)
    msg.answer.assert_awaited_once()


# ── handle_price_credits ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_price_credits_valid() -> None:
    msg = make_message(text="600")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"edit_plan_key": "credits_500"})
    mock_plan = SimpleNamespace(key="credits_500", label="500 💋", credits=600, price_rub=599.0, is_active=True, sort_order=1)
    with patch("bot.handlers.admin.repo", AsyncMock(get_price_plan_by_key=AsyncMock(return_value=mock_plan))):
        await admin.handle_price_credits(msg, mock_session, mock_state)
    msg.answer.assert_awaited_once()


# ── handle_price_label ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_price_label_valid() -> None:
    msg = make_message(text="1000 💋")
    msg.answer = AsyncMock()
    mock_session = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"edit_plan_key": "credits_500"})
    mock_plan = SimpleNamespace(key="credits_500", label="1000 💋", credits=1000, price_rub=999.0, is_active=True, sort_order=1)
    with patch("bot.handlers.admin.repo", AsyncMock(get_price_plan_by_key=AsyncMock(return_value=mock_plan))):
        await admin.handle_price_label(msg, mock_session, mock_state)
    msg.answer.assert_awaited_once()


# ── adm:models ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_models() -> None:
    call = make_callback(data="adm:models")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_cost = SimpleNamespace(model_key="sdxl__res=1024x1024", display_name="SDXL 1024", credits=8, gen_type=GenerationType("image"))
    with patch("bot.handlers.admin.repo", AsyncMock(get_all_model_costs=AsyncMock(return_value=[mock_cost]))):
        await admin.cb_models(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── adm:model_edit: ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_model_edit() -> None:
    call = make_callback(data="adm:model_edit:sdxl")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_cost = SimpleNamespace(model_key="sdxl", display_name="SDXL", credits=8)
    with patch("bot.handlers.admin.repo", AsyncMock(get_model_cost=AsyncMock(return_value=mock_cost))):
        await admin.cb_model_edit(call, AsyncMock())
    call.message.edit_text.assert_awaited_once()


# ── add_credits flow ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_add_credits() -> None:
    call = make_callback(data="adm:add_credits")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_add_credits(call, mock_state)
    mock_state.set_state.assert_called_with(admin.AdminFSM.await_credits_tg_id)


# ── ban flow ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_ban() -> None:
    call = make_callback(data="adm:ban")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_ban(call, mock_state)
    mock_state.set_state.assert_called_with(admin.AdminFSM.await_ban_tg_id)


# ── handle_ban ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_ban() -> None:
    msg = make_message(text="12345")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(ban_user=AsyncMock(return_value=True))):
        await admin.handle_ban(msg, mock_state, AsyncMock())
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_unban() -> None:
    msg = make_message(text="12345 unban")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(unban_user=AsyncMock(return_value=True))):
        await admin.handle_ban(msg, mock_state, AsyncMock())
    msg.answer.assert_awaited_once()


# ── broadcast ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_broadcast() -> None:
    call = make_callback(data="adm:broadcast")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    await admin.cb_broadcast(call, mock_state)
    mock_state.set_state.assert_called_with(admin.AdminFSM.await_broadcast_text)


@pytest.mark.asyncio
async def test_handle_broadcast() -> None:
    msg = make_message(text="Hello!")
    # status_msg — это AsyncMock, который вернёт message.answer()
    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)
    mock_state = AsyncMock()
    mock_bot = AsyncMock()
    mock_session = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(get_all_user_ids=AsyncMock(return_value=[100, 200]))):
        await admin.handle_broadcast(msg, mock_state, mock_session)
    # Финальный edit_text вызывается на status_msg
    status_msg.edit_text.assert_awaited_once()
    text = status_msg.edit_text.call_args[0][0]
    assert "Рассылка завершена" in text


# ── handle_credits_tg_id ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_credits_tg_id_not_found() -> None:
    msg = make_message(text="99999")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(get_user_by_tg_id=AsyncMock(return_value=None))):
        await admin.handle_credits_tg_id(msg, mock_state, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "не найден" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_credits_tg_id_found() -> None:
    msg = make_message(text="100")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_user = SimpleNamespace(
        id=42, username="target", tg_id=100,
        full_name="Target User", credits=500,
    )
    with patch("bot.handlers.admin.repo", AsyncMock(get_user_by_tg_id=AsyncMock(return_value=mock_user))):
        await admin.handle_credits_tg_id(msg, mock_state, AsyncMock())
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_called_with(admin.AdminFSM.await_credits_amount)


# ── handle_credits_amount ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_credits_amount() -> None:
    msg = make_message(text="100")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"target_user_id": 42, "target_tg_id": 123})
    mock_session = AsyncMock()
    with patch("bot.handlers.admin.repo", AsyncMock(add_credits=AsyncMock(return_value=600))):
        await admin.handle_credits_amount(msg, mock_state, mock_session)
    msg.answer.assert_awaited_once()


# ── Utility functions ─────────────────────────────────────────────────────────

def test_fmt_price_int() -> None:
    assert admin._fmt_price(199.0) == "199"


def test_fmt_price_float() -> None:
    assert admin._fmt_price(99.5) == "99.5"


def test_user_label_with_username() -> None:
    user = SimpleNamespace(username="testuser", tg_id=123)
    result = admin._user_label(user)
    assert "@testuser" in result


def test_user_label_no_username() -> None:
    user = SimpleNamespace(username=None, tg_id=123)
    result = admin._user_label(user)
    assert "без username" in result
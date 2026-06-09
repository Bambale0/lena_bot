"""Тесты хендлеров balance — пополнение, вывод, история, рефералы."""
from __future__ import annotations

import pytest
from aiogram.types import CallbackQuery, Message
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import balance
from db.models import GenerationType
from tests.factories import make_callback, make_message


@pytest.fixture
def db_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=42, tg_id=123456, credits=500, username="testuser",
        full_name="Test User", is_subscribed=True,
        subscription_until=MagicMock(),
        referral_code="abc123", referral_balance=10.5, language="ru",
    )


# ── menu:balance ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_balance_shows_screen(db_user) -> None:
    call = make_callback(data="menu:balance")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_costs = [
        SimpleNamespace(gen_type=GenerationType.image, model_key="nano-banana-2", credits=1.0),
        SimpleNamespace(gen_type=GenerationType.image, model_key="midjourney-blend", credits=12.0),
        SimpleNamespace(gen_type=GenerationType.video, model_key="grok-imagine/text-to-video", credits=3.0),
        SimpleNamespace(gen_type=GenerationType.video, model_key="veo3", credits=70.0),
        SimpleNamespace(gen_type=GenerationType.music, model_key="suno/v4.5", credits=20.0),
    ]
    with patch("bot.handlers.balance.repo", AsyncMock(get_all_model_costs=AsyncMock(return_value=mock_costs))):
        await balance.cb_balance(call, db_user, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0]
    assert "1–12 💋" in text
    assert "3–70 💋" in text
    assert "20 💋" in text


# ── menu:referral ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_referral_shows_screen(db_user) -> None:
    call = make_callback(data="menu:referral")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_bot = AsyncMock()
    mock_bot.get_me = AsyncMock(return_value=SimpleNamespace(username="testbot"))
    with patch("bot.handlers.balance.repo", AsyncMock(
        count_user_referrals=AsyncMock(return_value=(1, 2, 3)),
        get_user_withdrawal_requests=AsyncMock(return_value=[]),
        get_user_referral_balance_snapshot=AsyncMock(
            return_value=SimpleNamespace(total_earned=10.5, available_to_withdraw=10.5, pending_withdrawals=0.0)
        ),
        get_user_feed_remix_reward_rub=AsyncMock(return_value=0.0),
    )):
        await balance.cb_referral(call, db_user, mock_bot, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    assert "Партнёрская программа" in call.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_referral_list_empty(db_user) -> None:
    call = make_callback(data="referral:list")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.balance.repo", AsyncMock(get_referral_children=AsyncMock(return_value=[]))):
        await balance.cb_referral_list(call, db_user, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0]
    assert "Мои партнёры" in text
    assert "не был зарегистрирован раньше" in text


@pytest.mark.asyncio
async def test_cb_referral_list_with_children(db_user) -> None:
    call = make_callback(data="referral:list")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    child_user = SimpleNamespace(
        tg_id=777888999,
        username="friend_one",
        full_name="Friend One",
        created_at=MagicMock(strftime=MagicMock(return_value="12.05.2026")),
    )
    child = SimpleNamespace(user=child_user, generations_count=3, paid_rub=500.0)
    with patch("bot.handlers.balance.repo", AsyncMock(get_referral_children=AsyncMock(return_value=[child]))):
        await balance.cb_referral_list(call, db_user, AsyncMock())
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.call_args[0][0]
    assert "@friend_one" in text
    assert "777888999" in text
    assert "500₽" in text


# ── referral:withdraw ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_referral_withdraw(db_user) -> None:
    call = make_callback(data="referral:withdraw")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_session = AsyncMock()
    db_user.referral_balance = 1500.0
    with patch("bot.handlers.balance.repo", AsyncMock(
        get_user_referral_balance_snapshot=AsyncMock(
            return_value=SimpleNamespace(total_earned=1500.0, available_to_withdraw=1500.0, pending_withdrawals=0.0)
        ),
    )):
        await balance.cb_referral_withdraw(call, mock_state, db_user, mock_session)
    mock_state.set_state.assert_called_with(balance.WithdrawalFSM.amount)


# ── WithdrawalFSM.amount ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_withdraw_amount_valid(db_user) -> None:
    msg = make_message(text="1500")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_session = AsyncMock()
    with patch("bot.handlers.balance.repo", AsyncMock(
        get_user_referral_balance_snapshot=AsyncMock(
            return_value=SimpleNamespace(total_earned=2000.0, available_to_withdraw=2000.0, pending_withdrawals=0.0)
        ),
    )):
        await balance.handle_withdraw_amount(msg, mock_state, db_user, mock_session)
    mock_state.update_data.assert_awaited_once()
    mock_state.set_state.assert_called_with(balance.WithdrawalFSM.details)


@pytest.mark.asyncio
async def test_handle_withdraw_amount_invalid(db_user) -> None:
    msg = make_message(text="abc")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    await balance.handle_withdraw_amount(msg, mock_state, db_user, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "числом" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_withdraw_amount_zero(db_user) -> None:
    msg = make_message(text="0")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    await balance.handle_withdraw_amount(msg, mock_state, db_user, AsyncMock())
    msg.answer.assert_awaited_once()
    assert "больше нуля" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_withdraw_amount_exceeds_available(db_user) -> None:
    msg = make_message(text="1500")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_session = AsyncMock()
    with patch("bot.handlers.balance.repo", AsyncMock(
        get_user_referral_balance_snapshot=AsyncMock(
            return_value=SimpleNamespace(total_earned=500.0, available_to_withdraw=120.0, pending_withdrawals=380.0)
        ),
    )):
        await balance.handle_withdraw_amount(msg, mock_state, db_user, mock_session)
    msg.answer.assert_awaited_once()
    assert "доступно" in msg.answer.call_args[0][0].lower()
    mock_state.set_state.assert_not_called()


# ── ExchangeFSM.amount ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_exchange_amount_uses_standard_tariff_rate(db_user) -> None:
    msg = make_message(text="500")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_session = AsyncMock()
    converted = SimpleNamespace(id=3, amount_rub=500.0)
    mock_repo = AsyncMock(
        get_user_referral_balance_snapshot=AsyncMock(
            return_value=SimpleNamespace(total_earned=900.0, available_to_withdraw=900.0, pending_withdrawals=0.0)
        ),
        convert_referral_balance_to_credits=AsyncMock(return_value=converted),
    )

    with patch("bot.handlers.balance.repo", mock_repo):
        await balance.handle_exchange_amount(msg, mock_state, db_user, mock_session)

    mock_repo.convert_referral_balance_to_credits.assert_awaited_once()
    assert mock_repo.convert_referral_balance_to_credits.await_args.kwargs["amount_rub"] == 500.0
    assert mock_repo.convert_referral_balance_to_credits.await_args.kwargs["rub_per_credit"] == 10.0
    assert "50.00💋" in msg.answer.call_args[0][0]


# ── WithdrawalFSM.details ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_withdraw_details_too_short(db_user) -> None:
    msg = make_message(text="ab")
    msg.answer = AsyncMock()
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"withdraw_amount": 100.0})
    mock_bot = AsyncMock()
    mock_session = AsyncMock()
    await balance.handle_withdraw_details(msg, mock_state, mock_session, SimpleNamespace(id=42, language="ru"), mock_bot)
    msg.answer.assert_awaited_once()
    assert "короткие" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_withdraw_details_success(db_user) -> None:
    msg = make_message(text="Сбербанк +79991234567")
    msg.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, username="testuser", tg_id=123456, full_name="Test", language="ru")
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"withdraw_amount": 1500.0})
    mock_bot = AsyncMock()
    mock_session = AsyncMock()

    mock_request = SimpleNamespace(id=1, amount_rub=1500.0, user=mock_db_user, payout_details="Сбербанк +79991234567")
    with patch("bot.handlers.balance.repo", AsyncMock(
        create_withdrawal_request=AsyncMock(return_value=mock_request),
    )):
        with patch("bot.handlers.balance.settings", SimpleNamespace(ADMIN_IDS=[999])):
            await balance.handle_withdraw_details(msg, mock_state, mock_session, mock_db_user, mock_bot)

    msg.answer.assert_awaited_once()
    assert "Заявка на вывод" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_withdraw_details_insufficient_balance(db_user) -> None:
    msg = make_message(text="Сбербанк +79991234567")
    msg.answer = AsyncMock()
    mock_db_user = SimpleNamespace(id=42, username="testuser", tg_id=123456, full_name="Test", language="ru")
    mock_state = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={"withdraw_amount": 1500.0})
    mock_bot = AsyncMock()
    mock_session = AsyncMock()

    with patch("bot.handlers.balance.repo", AsyncMock(
        create_withdrawal_request=AsyncMock(
            side_effect=balance.InsufficientReferralBalanceError(120.0)
        ),
    )):
        await balance.handle_withdraw_details(msg, mock_state, mock_session, mock_db_user, mock_bot)

    msg.answer.assert_awaited_once()
    assert "доступно" in msg.answer.call_args[0][0].lower()


# ── menu:history ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_history_empty() -> None:
    call = make_callback(data="menu:history")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    with patch("bot.handlers.balance.repo", AsyncMock(get_user_history=AsyncMock(return_value=[]))):
        await balance.cb_history(call, AsyncMock(), SimpleNamespace(id=42, language="ru"))
    call.message.edit_text.assert_awaited_once()
    assert "История пуста" in call.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_history_with_items() -> None:
    call = make_callback(data="menu:history")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    mock_gen = MagicMock()
    mock_gen.gen_type = GenerationType("image")
    mock_gen.status.value = "done"
    mock_gen.model = "sdxl"
    mock_gen.prompt = "a beautiful cat"
    mock_gen.credits_spent = 5
    with patch("bot.handlers.balance.repo", AsyncMock(get_user_history=AsyncMock(return_value=[mock_gen]))):
        await balance.cb_history(call, AsyncMock(), SimpleNamespace(id=42, language="ru"))
    call.message.edit_text.assert_awaited_once()

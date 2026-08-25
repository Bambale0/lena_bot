from __future__ import annotations

import hashlib
import secrets
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.telegram_ui import safe_answer_callback
from db.models import User

router = Router(name="repeat_confirmation_guard")

_CONFIRM_PREFIX = "repeat_run_confirm_"
_CANCEL_PREFIX = "repeat_run_cancel_"
_EDIT_PREFIX = "repeat_edit_prompt_"
_ADD_REFS_PREFIX = "repeat_add_refs_"
_PROTECTED_PREFIXES = (
    _CONFIRM_PREFIX,
    _CANCEL_PREFIX,
    _EDIT_PREFIX,
    _ADD_REFS_PREFIX,
)
_repeat_safe_module: Any | None = None


def confirmation_callback_token(confirm_key: str | None) -> str:
    """Return a short, callback-safe token bound to exactly one confirmation."""
    value = str(confirm_key or "").strip()
    if not value:
        return ""
    return hashlib.blake2s(value.encode("utf-8"), digest_size=8).hexdigest()


def _callback_token(callback_data: str | None, prefix: str) -> str:
    value = str(callback_data or "")
    return value[len(prefix) :] if value.startswith(prefix) else ""


def callback_matches_confirmation(
    *,
    callback_data: str | None,
    prefix: str,
    confirm_key: str | None,
) -> bool:
    expected = confirmation_callback_token(confirm_key)
    actual = _callback_token(callback_data, prefix)
    return bool(expected and actual and secrets.compare_digest(expected, actual))


def install_repeat_confirmation_guard(repeat_safe: Any) -> None:
    """Bind confirmation buttons to the exact FSM confirmation that rendered them."""
    global _repeat_safe_module
    _repeat_safe_module = repeat_safe
    if getattr(repeat_safe, "_confirmation_token_keyboard_installed", False):
        return

    original_keyboard = repeat_safe._confirmation_keyboard

    def confirmation_keyboard(data: dict[str, Any]):
        markup = original_keyboard(data)
        token = confirmation_callback_token(data.get("repeat_confirm_key"))
        if not token:
            return markup
        for row in getattr(markup, "inline_keyboard", []) or []:
            for button in row:
                callback = str(getattr(button, "callback_data", "") or "")
                for prefix in _PROTECTED_PREFIXES:
                    if callback.startswith(prefix):
                        button.callback_data = f"{prefix}{token}"
                        break
        return markup

    repeat_safe._confirmation_keyboard = confirmation_keyboard
    repeat_safe._confirmation_token_keyboard_installed = True


async def _current_confirmation_or_reject(
    call: CallbackQuery,
    state: FSMContext,
    *,
    prefix: str,
) -> bool:
    data = await state.get_data()
    if callback_matches_confirmation(
        callback_data=call.data,
        prefix=prefix,
        confirm_key=data.get("repeat_confirm_key"),
    ):
        return True
    await safe_answer_callback(
        call,
        "Это подтверждение уже устарело. Используйте последнее сообщение повтора.",
        show_alert=True,
    )
    return False


def _repeat_safe() -> Any:
    if _repeat_safe_module is None:
        raise RuntimeError("repeat confirmation guard is not installed")
    return _repeat_safe_module


@router.callback_query(F.data.startswith(_CONFIRM_PREFIX))
async def guarded_confirm_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    if not await _current_confirmation_or_reject(call, state, prefix=_CONFIRM_PREFIX):
        return
    await _repeat_safe().confirm_repeat(call, session, state, db_user, bot)


@router.callback_query(F.data.startswith(_CANCEL_PREFIX))
async def guarded_cancel_repeat(call: CallbackQuery, state: FSMContext) -> None:
    if not await _current_confirmation_or_reject(call, state, prefix=_CANCEL_PREFIX):
        return
    await _repeat_safe().cancel_repeat(call, state)


@router.callback_query(F.data.startswith(_EDIT_PREFIX))
async def guarded_edit_repeat_prompt(call: CallbackQuery, state: FSMContext) -> None:
    if not await _current_confirmation_or_reject(call, state, prefix=_EDIT_PREFIX):
        return
    await _repeat_safe().edit_repeat_prompt(call, state)


@router.callback_query(F.data.startswith(_ADD_REFS_PREFIX))
async def guarded_add_repeat_refs(call: CallbackQuery, state: FSMContext) -> None:
    if not await _current_confirmation_or_reject(call, state, prefix=_ADD_REFS_PREFIX):
        return
    await _repeat_safe().add_repeat_refs(call, state)

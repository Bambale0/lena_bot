from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import repeat_callback_guard, repeat_safe


class FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})
        self.clear = AsyncMock(side_effect=self._clear)

    async def _clear(self) -> None:
        self.data = {}

    async def get_data(self) -> dict:
        return dict(self.data)

    async def set_state(self, state) -> None:
        self.data["state"] = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)


def _call(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
        from_user=SimpleNamespace(id=777),
    )


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_confirmation_keyboard_uses_short_session_token_not_source_id() -> None:
    data = {
        "repeat_raw_task_id": "img_same_source",
        "repeat_confirm_key": "repeat-42-5-session-a",
        "repeat_cost": 2.5,
        "repeat_supports_refs": True,
        "repeat_is_pinterest": False,
    }
    markup = repeat_safe._confirmation_keyboard(data)
    token = repeat_callback_guard.confirmation_callback_token(data["repeat_confirm_key"])

    assert token
    assert _callbacks(markup) == [
        f"repeat_run_confirm_{token}",
        f"repeat_edit_prompt_{token}",
        f"repeat_add_refs_{token}",
        f"repeat_run_cancel_{token}",
    ]
    assert all("img_same_source" not in callback for callback in _callbacks(markup))


@pytest.mark.asyncio
async def test_stale_confirm_cannot_launch_newer_repeat_session() -> None:
    current_key = "repeat-42-5-session-b"
    stale_token = repeat_callback_guard.confirmation_callback_token("repeat-42-5-session-a")
    state = FakeState({"repeat_confirm_key": current_key})
    call = _call(f"repeat_run_confirm_{stale_token}")

    with patch.object(repeat_safe, "confirm_repeat", AsyncMock()) as delegate:
        await repeat_callback_guard.guarded_confirm_repeat(
            call,
            AsyncMock(),
            state,
            SimpleNamespace(id=5),
            AsyncMock(),
        )

    delegate.assert_not_awaited()
    call.answer.assert_awaited_once()
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_stale_cancel_cannot_clear_newer_repeat_session() -> None:
    current_key = "repeat-42-5-session-b"
    stale_token = repeat_callback_guard.confirmation_callback_token("repeat-42-5-session-a")
    state = FakeState({"repeat_confirm_key": current_key, "repeat_prompt": "newer"})
    call = _call(f"repeat_run_cancel_{stale_token}")

    with patch.object(repeat_safe, "cancel_repeat", AsyncMock()) as delegate:
        await repeat_callback_guard.guarded_cancel_repeat(call, state)

    delegate.assert_not_awaited()
    state.clear.assert_not_awaited()
    assert state.data["repeat_prompt"] == "newer"


@pytest.mark.asyncio
async def test_current_confirmation_delegates_to_repeat_handler() -> None:
    confirm_key = "repeat-42-5-current"
    token = repeat_callback_guard.confirmation_callback_token(confirm_key)
    state = FakeState({"repeat_confirm_key": confirm_key})
    call = _call(f"repeat_run_confirm_{token}")
    session = AsyncMock()
    user = SimpleNamespace(id=5)
    bot = AsyncMock()

    with patch.object(repeat_safe, "confirm_repeat", AsyncMock()) as delegate:
        await repeat_callback_guard.guarded_confirm_repeat(call, session, state, user, bot)

    delegate.assert_awaited_once_with(call, session, state, user, bot)

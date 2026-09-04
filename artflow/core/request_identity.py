from __future__ import annotations

from contextvars import ContextVar, Token

_current_user_id: ContextVar[int | None] = ContextVar("apix_current_user_id", default=None)


def current_user_id() -> int | None:
    return _current_user_id.get()


def bind_current_user(user_id: int) -> Token[int | None]:
    return _current_user_id.set(int(user_id))


def clear_current_user() -> Token[int | None]:
    return _current_user_id.set(None)


def reset_current_user(token: Token[int | None]) -> None:
    _current_user_id.reset(token)

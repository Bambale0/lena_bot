from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from tests.factories import make_message, make_update_with_start_payload, make_user


@pytest.mark.asyncio
async def test_throttling_allows_first_message() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    handler = AsyncMock(return_value="ok")
    event = make_message(user_id=111)

    result = await ThrottlingMiddleware(redis)(handler, event, {})

    assert result == "ok"
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_throttling_skips_repeated_message() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=None)
    handler = AsyncMock()
    event = make_message(user_id=111)

    result = await ThrottlingMiddleware(redis)(handler, event, {})

    assert result is None
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_auth_middleware_passes_existing_user(monkeypatch) -> None:
    db_user = SimpleNamespace(id=1, tg_id=111, is_banned=False)
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=db_user))
    handler = AsyncMock(return_value="handled")

    data = {"session": AsyncMock(), "event_from_user": make_user(user_id=111), "bot": AsyncMock()}
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result == "handled"
    assert data["db_user"] is db_user


@pytest.mark.asyncio
async def test_auth_middleware_ignores_banned_user(monkeypatch) -> None:
    db_user = SimpleNamespace(id=1, tg_id=111, is_banned=True)
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=db_user))
    handler = AsyncMock()

    data = {"session": AsyncMock(), "event_from_user": make_user(user_id=111), "bot": AsyncMock()}
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result is None
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_auth_middleware_creates_user_with_referral(monkeypatch) -> None:
    referrer = SimpleNamespace(id=10, tg_id=1000, referrer_id=None)
    created = SimpleNamespace(id=2, tg_id=222, is_banned=False)
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=None))
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_referral_code", AsyncMock(return_value=referrer))
    monkeypatch.setattr("bot.middlewares.auth.repo.create_user", AsyncMock(return_value=created))
    monkeypatch.setattr("bot.middlewares.auth.repo.add_credits", AsyncMock(return_value=35))
    handler = AsyncMock(return_value="handled")

    data = {
        "session": AsyncMock(),
        "event_from_user": make_user(user_id=222),
        "event_update": make_update_with_start_payload("REFCODE"),
        "bot": AsyncMock(),
    }
    result = await AuthMiddleware()(handler, make_message(user_id=222), data)

    assert result == "handled"
    assert data["db_user"] is created

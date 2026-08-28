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
    assert redis.set.await_args.kwargs["px"] == 1500
    assert redis.set.await_args.kwargs["nx"] is True


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
    db_user = SimpleNamespace(id=1, tg_id=111, is_banned=False, language="ru")
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=db_user))
    handler = AsyncMock(return_value="handled")

    data = {"session": AsyncMock(), "event_from_user": make_user(user_id=111), "bot": AsyncMock()}
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result == "handled"
    assert data["db_user"] is db_user


@pytest.mark.asyncio
async def test_auth_middleware_ignores_banned_user(monkeypatch) -> None:
    db_user = SimpleNamespace(id=1, tg_id=111, is_banned=True, language="ru")
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=db_user))
    handler = AsyncMock()

    data = {"session": AsyncMock(), "event_from_user": make_user(user_id=111), "bot": AsyncMock()}
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result is None
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_auth_middleware_blocks_non_admin_during_maintenance(monkeypatch) -> None:
    monkeypatch.setattr("bot.middlewares.auth.is_maintenance_mode", lambda: True)
    monkeypatch.setattr("bot.middlewares.auth.settings.ADMIN_IDS", [999])
    handler = AsyncMock()
    bot = AsyncMock()

    data = {"session": AsyncMock(), "event_from_user": make_user(user_id=111), "bot": bot}
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result is None
    handler.assert_not_called()
    bot.send_message.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_auth_middleware_late_binds_referral_for_existing_user_without_referrer(monkeypatch) -> None:
    db_user = SimpleNamespace(
        id=2,
        tg_id=222,
        is_banned=False,
        language="ru",
        referrer_id=None,
        referrer_l2_id=None,
        referrer_l3_id=None,
    )
    rebound_user = SimpleNamespace(
        id=2,
        tg_id=222,
        is_banned=False,
        language="ru",
        referrer_id=10,
        referrer_l2_id=None,
        referrer_l3_id=None,
    )
    referrer = SimpleNamespace(id=10, tg_id=1000, referrer_id=None)
    get_user_by_tg_id = AsyncMock(side_effect=[db_user, rebound_user])
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", get_user_by_tg_id)
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_referral_code", AsyncMock(return_value=referrer))
    monkeypatch.setattr("bot.middlewares.auth.repo.bind_user_referrer_once", AsyncMock(return_value=True))
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
    assert data["db_user"] is rebound_user


@pytest.mark.asyncio
async def test_auth_middleware_late_bind_rejects_descendant_referrer(monkeypatch) -> None:
    db_user = SimpleNamespace(
        id=1,
        tg_id=111,
        is_banned=False,
        language="ru",
        referrer_id=None,
        referrer_l2_id=None,
        referrer_l3_id=None,
    )
    descendant_referrer = SimpleNamespace(id=9, tg_id=999, referrer_id=1)
    get_user_by_tg_id = AsyncMock(return_value=db_user)
    bind_user_referrer_once = AsyncMock(return_value=True)
    add_credits = AsyncMock()

    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", get_user_by_tg_id)
    monkeypatch.setattr(
        "bot.middlewares.auth.repo.get_user_by_referral_code",
        AsyncMock(return_value=descendant_referrer),
    )
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_id", AsyncMock(return_value=db_user))
    monkeypatch.setattr(
        "bot.middlewares.auth.repo.bind_user_referrer_once",
        bind_user_referrer_once,
    )
    monkeypatch.setattr("bot.middlewares.auth.repo.add_credits", add_credits)
    handler = AsyncMock(return_value="handled")

    data = {
        "session": AsyncMock(),
        "event_from_user": make_user(user_id=111),
        "event_update": make_update_with_start_payload("DESCENDANT"),
        "bot": AsyncMock(),
    }
    result = await AuthMiddleware()(handler, make_message(user_id=111), data)

    assert result == "handled"
    assert data["db_user"] is db_user
    bind_user_referrer_once.assert_not_awaited()
    add_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_middleware_ignores_self_referral_payload(monkeypatch) -> None:
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_tg_id", AsyncMock(return_value=None))
    self_user = SimpleNamespace(id=10, tg_id=222, referrer_id=None)
    monkeypatch.setattr("bot.middlewares.auth.repo.get_user_by_referral_code", AsyncMock(return_value=self_user))
    create_user = AsyncMock(return_value=SimpleNamespace(id=2, tg_id=222, is_banned=False))
    monkeypatch.setattr("bot.middlewares.auth.repo.create_user", create_user)
    monkeypatch.setattr("bot.middlewares.auth.repo.add_credits", AsyncMock())
    handler = AsyncMock(return_value="handled")

    data = {
        "session": AsyncMock(),
        "event_from_user": make_user(user_id=222),
        "event_update": make_update_with_start_payload("SELFREF"),
        "bot": AsyncMock(),
    }
    result = await AuthMiddleware()(handler, make_message(user_id=222), data)

    assert result == "handled"
    assert create_user.await_args.kwargs["referrer"] is None

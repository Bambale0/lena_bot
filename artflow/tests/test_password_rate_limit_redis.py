from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from api.web.auth_rate_limit_guard import install_password_rate_limit
from core.password_rate_limit import (
    RateLimiterUnavailable,
    RedisEventRateLimiter,
    RedisPasswordRateLimiter,
)


class FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}

    def pipeline(self, transaction: bool = True):
        assert transaction is True
        return FakePipeline(self)

    async def delete(self, key: str) -> int:
        return 1 if self.zsets.pop(key, None) is not None else 0


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple] = []

    def zremrangebyscore(self, key: str, minimum: float, maximum: float):
        self.ops.append(("zremrangebyscore", key, float(minimum), float(maximum)))
        return self

    def zcard(self, key: str):
        self.ops.append(("zcard", key))
        return self

    def zrange(self, key: str, start: int, end: int, *, withscores: bool = False):
        self.ops.append(("zrange", key, start, end, withscores))
        return self

    def pexpire(self, key: str, ttl_ms: int):
        self.ops.append(("pexpire", key, ttl_ms))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        self.ops.append(("zadd", key, mapping))
        return self

    async def execute(self) -> list[object]:
        results: list[object] = []
        for op in self.ops:
            name, *args = op
            if name == "zremrangebyscore":
                key, minimum, maximum = args
                zset = self.redis.zsets.setdefault(key, {})
                removed = [member for member, score in zset.items() if minimum <= score <= maximum]
                for member in removed:
                    zset.pop(member, None)
                results.append(len(removed))
            elif name == "zcard":
                (key,) = args
                results.append(len(self.redis.zsets.get(key, {})))
            elif name == "zrange":
                key, start, end, withscores = args
                ordered = sorted(self.redis.zsets.get(key, {}).items(), key=lambda item: item[1])
                stop = None if end == -1 else end + 1
                selected = ordered[start:stop]
                results.append(selected if withscores else [member for member, _ in selected])
            elif name == "pexpire":
                key, _ttl_ms = args
                results.append(key in self.redis.zsets)
            elif name == "zadd":
                key, mapping = args
                zset = self.redis.zsets.setdefault(key, {})
                before = len(zset)
                zset.update({str(member): float(score) for member, score in mapping.items()})
                results.append(len(zset) - before)
            else:  # pragma: no cover - protects the fake itself
                raise AssertionError(f"Unknown fake Redis operation: {name}")
        return results


@pytest.mark.asyncio
async def test_failed_login_window_survives_new_limiter_instance() -> None:
    redis = FakeRedis()
    now = [1_000.0]

    first_process = RedisPasswordRateLimiter(
        window_seconds=900,
        max_failures=8,
        redis_client=redis,
        clock=lambda: now[0],
    )
    for _ in range(8):
        await first_process.record_failure("User@Example.com")

    restarted_process = RedisPasswordRateLimiter(
        window_seconds=900,
        max_failures=8,
        redis_client=redis,
        clock=lambda: now[0],
    )
    assert await restarted_process.retry_after("user@example.com") == 900
    assert all("user@example.com" not in key for key in redis.zsets)

    now[0] += 901
    assert await restarted_process.retry_after("USER@example.com") == 0


@pytest.mark.asyncio
async def test_contact_request_window_survives_new_limiter_instance() -> None:
    redis = FakeRedis()
    now = [2_000.0]
    first_process = RedisEventRateLimiter(
        namespace="auth:contact-request:contact",
        window_seconds=900,
        max_events=5,
        redis_client=redis,
        clock=lambda: now[0],
    )
    for _ in range(5):
        await first_process.record("email:creator@example.com")

    restarted_process = RedisEventRateLimiter(
        namespace="auth:contact-request:contact",
        window_seconds=900,
        max_events=5,
        redis_client=redis,
        clock=lambda: now[0],
    )
    assert await restarted_process.retry_after("email:creator@example.com") == 900


@pytest.mark.asyncio
async def test_successful_login_clears_durable_failure_window() -> None:
    redis = FakeRedis()
    limiter = RedisPasswordRateLimiter(
        window_seconds=900,
        max_failures=2,
        redis_client=redis,
        clock=lambda: 1_000.0,
    )
    await limiter.record_failure("creator@example.com")
    await limiter.record_failure("creator@example.com")
    assert await limiter.retry_after("creator@example.com") == 900

    await limiter.clear("creator@example.com")
    assert await limiter.retry_after("creator@example.com") == 0


@pytest.mark.asyncio
async def test_redis_failure_fails_closed_instead_of_disabling_rate_limit() -> None:
    class BrokenRedis:
        def pipeline(self, transaction: bool = True):
            raise RedisError("redis unavailable")

    limiter = RedisPasswordRateLimiter(
        window_seconds=900,
        max_failures=8,
        redis_client=BrokenRedis(),
    )

    with pytest.raises(RateLimiterUnavailable):
        await limiter.retry_after("creator@example.com")


@pytest.mark.asyncio
async def test_password_login_route_records_failures_through_installed_limiter() -> None:
    async def original_password_login(body, response, session):  # pragma: no cover - must be replaced
        raise AssertionError("legacy in-memory route was called")

    route = SimpleNamespace(
        path="/auth/password-login",
        endpoint=original_password_login,
        dependant=SimpleNamespace(call=original_password_login),
    )
    auth = SimpleNamespace(
        PASSWORD_LOGIN_WINDOW_SECONDS=900,
        PASSWORD_LOGIN_MAX_FAILURES=8,
        password_login=original_password_login,
        router=SimpleNamespace(routes=[route]),
        error_response=lambda status, message: {"status": status, "message": message},
        _user_by_login=AsyncMock(return_value=None),
        verify_password=lambda password, encoded: False,
        ok=lambda payload: {"ok": True, "data": payload},
        _auth_payload=lambda user, response=None: {"user": user},
    )
    limiter = SimpleNamespace(
        retry_after=AsyncMock(return_value=0),
        record_failure=AsyncMock(),
        clear=AsyncMock(),
    )

    install_password_rate_limit(auth, limiter=limiter)
    body = SimpleNamespace(login="creator@example.com", password="wrong-password")
    result = await auth.password_login(body, object(), object())

    assert result["status"] == 401
    limiter.retry_after.assert_awaited_once_with("creator@example.com")
    limiter.record_failure.assert_awaited_once_with("creator@example.com")
    assert route.dependant.call is auth.password_login


@pytest.mark.asyncio
async def test_contact_auth_routes_use_redis_limiters_not_process_dicts() -> None:
    async def original_password_login(body, response, session):
        return {"ok": True}

    async def original_contact_request(body, request, session):
        return {"ok": True, "data": {"message": "sent"}}

    async def original_contact_verify(body, response, request, session):
        if getattr(body, "code", "") == "bad":
            return SimpleNamespace(status_code=401)
        return {"ok": True, "data": {"user": "creator"}}

    password_route = SimpleNamespace(
        path="/auth/password-login",
        endpoint=original_password_login,
        dependant=SimpleNamespace(call=original_password_login),
    )
    request_route = SimpleNamespace(
        path="/auth/contact/request",
        endpoint=original_contact_request,
        dependant=SimpleNamespace(call=original_contact_request),
    )
    verify_route = SimpleNamespace(
        path="/auth/contact/verify",
        endpoint=original_contact_verify,
        dependant=SimpleNamespace(call=original_contact_verify),
    )
    auth = SimpleNamespace(
        PASSWORD_LOGIN_WINDOW_SECONDS=900,
        PASSWORD_LOGIN_MAX_FAILURES=8,
        CONTACT_AUTH_WINDOW_SECONDS=900,
        CONTACT_AUTH_REQUESTS_PER_IP=20,
        CONTACT_AUTH_REQUESTS_PER_CONTACT=5,
        CONTACT_AUTH_VERIFY_FAILURES_MAX=10,
        password_login=original_password_login,
        contact_auth_request=original_contact_request,
        contact_auth_verify=original_contact_verify,
        router=SimpleNamespace(routes=[password_route, request_route, verify_route]),
        error_response=lambda status, message: {"status": status, "message": message},
        _user_by_login=AsyncMock(return_value=None),
        verify_password=lambda password, encoded: False,
        ok=lambda payload: {"ok": True, "data": payload},
        _auth_payload=lambda user, response=None: {"user": user},
        _normalize_contact=lambda contact: ("email", contact.strip().lower()),
        _request_remote_ip=lambda request: "203.0.113.10",
        _CONTACT_AUTH_REQUESTS={"legacy": [1.0]},
        _CONTACT_AUTH_VERIFY_FAILURES={"legacy": [1.0]},
    )
    password_limiter = SimpleNamespace(
        retry_after=AsyncMock(return_value=0),
        record_failure=AsyncMock(),
        clear=AsyncMock(),
    )
    contact_limiters = {
        name: SimpleNamespace(
            retry_after=AsyncMock(return_value=0),
            record=AsyncMock(),
            clear=AsyncMock(),
        )
        for name in ("request_contact", "request_ip", "verify_contact", "verify_ip")
    }

    install_password_rate_limit(
        auth,
        limiter=password_limiter,
        contact_limiters=contact_limiters,
    )

    request = object()
    request_body = SimpleNamespace(contact="Creator@Example.com")
    result = await auth.contact_auth_request(request_body, request, object())
    assert result["ok"] is True
    contact_limiters["request_contact"].record.assert_awaited_once_with(
        "email:creator@example.com"
    )
    contact_limiters["request_ip"].record.assert_awaited_once_with("203.0.113.10")

    invalid_body = SimpleNamespace(contact="Creator@Example.com", code="bad")
    invalid = await auth.contact_auth_verify(invalid_body, object(), request, object())
    assert invalid.status_code == 401
    contact_limiters["verify_contact"].record.assert_awaited_once_with(
        "email:creator@example.com"
    )
    contact_limiters["verify_ip"].record.assert_awaited_once_with("203.0.113.10")
    contact_limiters["verify_contact"].clear.assert_not_awaited()

    valid_body = SimpleNamespace(contact="Creator@Example.com", code="good")
    verified = await auth.contact_auth_verify(valid_body, object(), request, object())
    assert verified["ok"] is True
    contact_limiters["verify_contact"].clear.assert_awaited_once_with(
        "email:creator@example.com"
    )
    contact_limiters["verify_ip"].clear.assert_awaited_once_with("203.0.113.10")

    assert auth._CONTACT_AUTH_REQUESTS == {}
    assert auth._CONTACT_AUTH_VERIFY_FAILURES == {}
    assert auth._contact_auth_request_retry_after() == 0
    assert auth._contact_auth_verify_retry_after() == 0
    assert request_route.dependant.call is auth.contact_auth_request
    assert verify_route.dependant.call is auth.contact_auth_verify

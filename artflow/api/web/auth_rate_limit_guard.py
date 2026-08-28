from __future__ import annotations

import logging
from typing import Any

from core.password_rate_limit import RateLimiterUnavailable, RedisPasswordRateLimiter

logger = logging.getLogger(__name__)


_UNAVAILABLE_MESSAGE = "Вход временно недоступен. Попробуйте ещё раз через минуту."


def install_password_rate_limit(auth_module: Any, *, limiter: Any | None = None) -> None:
    """Replace the password-login call with a Redis-backed failure window.

    The existing FastAPI route/dependency graph is preserved; only its callable
    is swapped. This keeps the public API contract unchanged while removing the
    process-local failure dictionary from the runtime path.
    """
    if getattr(auth_module, "_redis_password_rate_limit_installed", False):
        return

    if limiter is None:
        limiter = RedisPasswordRateLimiter(
            window_seconds=int(auth_module.PASSWORD_LOGIN_WINDOW_SECONDS),
            max_failures=int(auth_module.PASSWORD_LOGIN_MAX_FAILURES),
        )

    async def password_login(body, response, session):
        try:
            retry_after = await limiter.retry_after(body.login)
        except RateLimiterUnavailable:
            return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)

        if retry_after > 0:
            return auth_module.error_response(
                429,
                f"Слишком много попыток. Повторите через {retry_after} сек.",
            )

        user = await auth_module._user_by_login(session, body.login)
        if not user or getattr(user, "is_banned", False):
            try:
                await limiter.record_failure(body.login)
            except RateLimiterUnavailable:
                return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)
            return auth_module.error_response(401, "Неверный логин или пароль")

        if not auth_module.verify_password(body.password, getattr(user, "password_hash", None)):
            try:
                await limiter.record_failure(body.login)
            except RateLimiterUnavailable:
                return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)
            return auth_module.error_response(401, "Неверный логин или пароль")

        try:
            await limiter.clear(body.login)
        except RateLimiterUnavailable:
            return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)
        return auth_module.ok(auth_module._auth_payload(user, response=response))

    original = auth_module.password_login
    password_login.__name__ = original.__name__
    password_login.__qualname__ = original.__qualname__
    password_login.__doc__ = original.__doc__

    patched = False
    for route in auth_module.router.routes:
        if getattr(route, "path", None) != "/auth/password-login":
            continue
        route.endpoint = password_login
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = password_login
        patched = True

    if not patched:
        raise RuntimeError("Password login route not found while installing Redis rate limiter")

    auth_module.password_login = password_login
    auth_module._password_rate_limiter = limiter
    auth_module._redis_password_rate_limit_installed = True
    logger.info("Redis password rate limiter installed")

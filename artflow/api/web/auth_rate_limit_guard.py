from __future__ import annotations

import logging
from typing import Any

from core.password_rate_limit import (
    RateLimiterUnavailable,
    RedisEventRateLimiter,
    RedisPasswordRateLimiter,
)

logger = logging.getLogger(__name__)

_UNAVAILABLE_MESSAGE = "Вход временно недоступен. Попробуйте ещё раз через минуту."


def _patch_route(auth_module: Any, path: str, endpoint: Any) -> bool:
    patched = False
    for route in auth_module.router.routes:
        if getattr(route, "path", None) != path:
            continue
        route.endpoint = endpoint
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = endpoint
        patched = True
    return patched


def _copy_endpoint_metadata(endpoint: Any, original: Any) -> None:
    endpoint.__name__ = original.__name__
    endpoint.__qualname__ = original.__qualname__
    endpoint.__doc__ = original.__doc__


def _contact_limiters(auth_module: Any) -> dict[str, RedisEventRateLimiter]:
    window = int(auth_module.CONTACT_AUTH_WINDOW_SECONDS)
    return {
        "request_contact": RedisEventRateLimiter(
            namespace="auth:contact-request:contact",
            window_seconds=window,
            max_events=int(auth_module.CONTACT_AUTH_REQUESTS_PER_CONTACT),
        ),
        "request_ip": RedisEventRateLimiter(
            namespace="auth:contact-request:ip",
            window_seconds=window,
            max_events=int(auth_module.CONTACT_AUTH_REQUESTS_PER_IP),
        ),
        "verify_contact": RedisEventRateLimiter(
            namespace="auth:contact-verify:contact",
            window_seconds=window,
            max_events=int(auth_module.CONTACT_AUTH_VERIFY_FAILURES_MAX),
        ),
        "verify_ip": RedisEventRateLimiter(
            namespace="auth:contact-verify:ip",
            window_seconds=window,
            max_events=int(auth_module.CONTACT_AUTH_VERIFY_FAILURES_MAX),
        ),
    }


async def _retry_after_for_subjects(
    pairs: list[tuple[Any, str | None]],
) -> int:
    retry_after = 0
    for limiter, subject in pairs:
        if not subject:
            continue
        retry_after = max(retry_after, await limiter.retry_after(subject))
    return retry_after


async def _record_subjects(pairs: list[tuple[Any, str | None]]) -> None:
    for limiter, subject in pairs:
        if subject:
            await limiter.record(subject)


async def _clear_subjects(pairs: list[tuple[Any, str | None]]) -> None:
    for limiter, subject in pairs:
        if subject:
            await limiter.clear(subject)


def install_password_rate_limit(
    auth_module: Any,
    *,
    limiter: Any | None = None,
    contact_limiters: dict[str, Any] | None = None,
) -> None:
    """Install durable Redis auth limits without changing public API routes.

    Password failures and, when present, contact-code request/verification
    windows are moved off process-local dictionaries. Existing FastAPI route
    dependency graphs are preserved by replacing their call targets in place.
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

    original_password_login = auth_module.password_login
    _copy_endpoint_metadata(password_login, original_password_login)
    if not _patch_route(auth_module, "/auth/password-login", password_login):
        raise RuntimeError("Password login route not found while installing Redis rate limiter")
    auth_module.password_login = password_login
    auth_module._password_rate_limiter = limiter

    contact_enabled = all(
        hasattr(auth_module, name)
        for name in (
            "CONTACT_AUTH_WINDOW_SECONDS",
            "CONTACT_AUTH_REQUESTS_PER_IP",
            "CONTACT_AUTH_REQUESTS_PER_CONTACT",
            "CONTACT_AUTH_VERIFY_FAILURES_MAX",
            "contact_auth_request",
            "contact_auth_verify",
        )
    )
    if contact_enabled:
        contact_limiters = contact_limiters or _contact_limiters(auth_module)
        original_contact_request = auth_module.contact_auth_request
        original_contact_verify = auth_module.contact_auth_verify

        # Disable the legacy process-local stores. The wrappers below enforce
        # the same public limits durably around the original endpoint logic.
        if hasattr(auth_module, "_CONTACT_AUTH_REQUESTS"):
            auth_module._CONTACT_AUTH_REQUESTS.clear()
        if hasattr(auth_module, "_CONTACT_AUTH_VERIFY_FAILURES"):
            auth_module._CONTACT_AUTH_VERIFY_FAILURES.clear()
        auth_module._contact_auth_request_retry_after = lambda **_kwargs: 0
        auth_module._record_contact_auth_request = lambda **_kwargs: None
        auth_module._contact_auth_verify_retry_after = lambda **_kwargs: 0
        auth_module._record_contact_auth_verify_failure = lambda **_kwargs: None
        auth_module._clear_contact_auth_verify_failures = lambda **_kwargs: None

        async def contact_auth_request(body, request, session):
            try:
                contact_type, contact = auth_module._normalize_contact(body.contact)
            except ValueError:
                return await original_contact_request(body, request, session)

            remote_ip = auth_module._request_remote_ip(request)
            pairs = [
                (contact_limiters["request_contact"], f"{contact_type}:{contact}"),
                (contact_limiters["request_ip"], remote_ip),
            ]
            try:
                retry_after = await _retry_after_for_subjects(pairs)
            except RateLimiterUnavailable:
                return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)

            if retry_after > 0:
                return auth_module.error_response(
                    429,
                    f"Слишком много запросов кода. Повторите через {retry_after} сек.",
                )

            result = await original_contact_request(body, request, session)
            data = result.get("data") if isinstance(result, dict) and result.get("ok") is True else None
            should_record = isinstance(data, dict) and not data.get("retry_after")
            if should_record:
                try:
                    await _record_subjects(pairs)
                except RateLimiterUnavailable:
                    return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)
            return result

        async def contact_auth_verify(body, response, request, session):
            try:
                contact_type, contact = auth_module._normalize_contact(body.contact)
            except ValueError:
                return await original_contact_verify(body, response, request, session)

            remote_ip = auth_module._request_remote_ip(request)
            pairs = [
                (contact_limiters["verify_contact"], f"{contact_type}:{contact}"),
                (contact_limiters["verify_ip"], remote_ip),
            ]
            try:
                retry_after = await _retry_after_for_subjects(pairs)
            except RateLimiterUnavailable:
                return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)

            if retry_after > 0:
                return auth_module.error_response(
                    429,
                    f"Слишком много попыток. Повторите через {retry_after} сек.",
                )

            result = await original_contact_verify(body, response, request, session)
            try:
                if isinstance(result, dict) and result.get("ok") is True:
                    await _clear_subjects(pairs)
                elif getattr(result, "status_code", None) == 401:
                    await _record_subjects(pairs)
            except RateLimiterUnavailable:
                return auth_module.error_response(503, _UNAVAILABLE_MESSAGE)
            return result

        _copy_endpoint_metadata(contact_auth_request, original_contact_request)
        _copy_endpoint_metadata(contact_auth_verify, original_contact_verify)
        if not _patch_route(auth_module, "/auth/contact/request", contact_auth_request):
            raise RuntimeError("Contact auth request route not found while installing Redis rate limiter")
        if not _patch_route(auth_module, "/auth/contact/verify", contact_auth_verify):
            raise RuntimeError("Contact auth verify route not found while installing Redis rate limiter")
        auth_module.contact_auth_request = contact_auth_request
        auth_module.contact_auth_verify = contact_auth_verify
        auth_module._contact_auth_rate_limiters = contact_limiters

    auth_module._redis_password_rate_limit_installed = True
    logger.info("Redis auth rate limits installed")

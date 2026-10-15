"""Document existing custom auth without changing runtime dependency behavior."""
from __future__ import annotations

from collections.abc import Iterator
from functools import wraps

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from api.web_auth_constants import WEB_AUTH_COOKIE_NAME

MINIAPP_DEPENDENCY = ("api.miniapp_auth", "get_miniapp_user")
WEB_DEPENDENCY = ("api.web.deps", "get_web_user_or_none")
# These two routes can serve approved public prompts anonymously. source=my
# and access to unpublished owner prompts still require authentication.
OPTIONAL_WEB_ENDPOINTS = {
    ("api.web.prompts", "prompts"),
    ("api.web.prompts", "prompt_detail"),
}


def _dependencies(dependant: Dependant) -> Iterator[tuple[str, str]]:
    call = dependant.call
    yield (getattr(call, "__module__", ""), getattr(call, "__name__", ""))
    for child in dependant.dependencies:
        yield from _dependencies(child)


def install_openapi_security(app: FastAPI) -> None:
    if getattr(app.state, "openapi_security_installed", False):
        return
    original = app.openapi

    @wraps(original)
    def openapi():
        schema = original()
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes.update({
            "TelegramInitData": {
                "type": "apiKey", "in": "header", "name": "X-Telegram-Init-Data",
                "description": "Telegram WebApp initData, verified server-side with HMAC and expiry. Takes precedence over web credentials.",
            },
            "WebAuthToken": {
                "type": "apiKey", "in": "header", "name": "X-Web-Auth-Token",
                "description": "Signed APIX web session token. Header takes precedence over the cookie.",
            },
            "WebAuthCookie": {
                "type": "apiKey", "in": "cookie", "name": WEB_AUTH_COOKIE_NAME,
                "description": "Signed APIX web session cookie; accepted by website routes only.",
            },
        })
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            deps = set(_dependencies(route.dependant))
            if MINIAPP_DEPENDENCY not in deps and WEB_DEPENDENCY not in deps:
                continue
            security = [{"TelegramInitData": []}, {"WebAuthToken": []}]
            if WEB_DEPENDENCY in deps:
                security.append({"WebAuthCookie": []})
                endpoint = (route.endpoint.__module__, route.endpoint.__name__)
                if endpoint in OPTIONAL_WEB_ENDPOINTS:
                    security.append({})
            for method in route.methods:
                operation = schema.get("paths", {}).get(route.path_format, {}).get(method.lower())
                if operation is None:
                    continue
                operation["security"] = [dict(requirement) for requirement in security]
                if "/admin/" in route.path_format:
                    operation["x-required-role"] = "admin"
                    operation.setdefault("responses", {}).setdefault("403", {"description": "Authenticated user is not an administrator"})
                if {} not in security:
                    operation.setdefault("responses", {}).setdefault("401", {"description": "Missing, invalid or expired user credentials"})
        return schema

    app.openapi = openapi
    app.state.openapi_security_installed = True

"""The exported API schema must support deterministic client generation."""

from main import app


def test_openapi_operation_ids_are_unique() -> None:
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"get", "head", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert schema["paths"]["/health"]["get"]["operationId"] == "public_health_get"
    assert schema["paths"]["/health"]["head"]["operationId"] == "public_health_head"
    assert schema["paths"]["/api/v1/health"]["get"]["operationId"] == "miniapp_health_get"
    assert schema["paths"]["/api/v1/health"]["head"]["operationId"] == "miniapp_health_head"


def test_openapi_user_auth_matches_header_or_cookie_contract():
    schema = app.openapi()
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [
        {"TelegramInitData": []}, {"WebAuthToken": []},
    ]
    assert schema["paths"]["/api/web/me"]["get"]["security"] == [
        {"TelegramInitData": []}, {"WebAuthToken": []}, {"WebAuthCookie": []},
    ]
    schemes = schema["components"]["securitySchemes"]
    assert schemes["TelegramInitData"]["name"] == "X-Telegram-Init-Data"
    assert schemes["WebAuthToken"]["name"] == "X-Web-Auth-Token"
    assert schemes["WebAuthCookie"]["in"] == "cookie"
    assert "X-Dev-Tg-Id" not in str(schemes)


def test_openapi_public_and_optional_auth_are_not_mislabeled_private():
    schema = app.openapi()
    for path in ("/health", "/api/v1/health", "/api/web/health", "/api/web/feed"):
        assert not schema["paths"][path]["get"].get("security")
    for path in ("/api/web/prompts", "/api/web/prompts/{prompt_id}"):
        assert {} in schema["paths"][path]["get"]["security"]


def test_openapi_admin_auth_is_explicit_without_publishing_admin_ids():
    schema = app.openapi()
    for path in ("/api/web/admin/overview", "/api/v1/admin/trends"):
        operation = schema["paths"][path]["get"]
        assert operation["security"] and {} not in operation["security"]
        assert operation["x-required-role"] == "admin"
        assert "403" in operation["responses"]

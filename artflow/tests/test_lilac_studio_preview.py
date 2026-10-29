from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import miniapp_auth, miniapp_routes
from bot.ui.main_menu import build_main_menu_keyboard
from db.session import get_session


@pytest.fixture
def preview_client(monkeypatch):
    async def session_override():
        yield object()

    user = SimpleNamespace(
        id=7, tg_id=123, username="test", full_name="Test", credits=0,
        referral_code="test", referral_balance=0, is_banned=False, is_admin=True,
    )
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    monkeypatch.setattr(miniapp_auth, "_verify_init_data", lambda value: {"id": user.tg_id})
    monkeypatch.setattr(miniapp_auth.repo, "get_user_by_tg_id", AsyncMock(side_effect=lambda *_: user))
    app = FastAPI()
    app.include_router(miniapp_routes.router)
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client, user


def _auth_headers(user, auth_method):
    if auth_method == "web":
        return {"X-Web-Auth-Token": miniapp_auth.create_web_auth_token(user.tg_id)}
    return {"X-Telegram-Init-Data": "signed-fixture"}


@pytest.mark.parametrize("tg_id", [123, 456])
@pytest.mark.parametrize("auth_method", ["telegram", "web"])
def test_authenticated_user_can_enter_studio_without_caching_identity(
    preview_client, tg_id, auth_method,
):
    client, user = preview_client
    user.tg_id = tg_id
    response = client.get("/api/v1/studio/preview", headers=_auth_headers(user, auth_method))
    assert response.status_code == 200
    assert response.json() == {"allowed": True, "ui_version": 3}
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "X-Telegram-Init-Data, X-Web-Auth-Token"


@pytest.mark.parametrize(("tg_id", "expected_admin"), [(123, True), (456, False)])
@pytest.mark.parametrize("auth_method", ["telegram", "web"])
def test_current_profile_keeps_server_role_separate_from_studio_access(
    preview_client, tg_id, expected_admin, auth_method,
):
    client, user = preview_client
    user.tg_id = tg_id
    response = client.get("/api/v1/me?admin=1&ux=3", headers=_auth_headers(user, auth_method))
    assert response.status_code == 200
    assert response.json()["miniapp_ux2_available"] is True
    assert response.json()["is_admin"] is expected_admin


@pytest.mark.parametrize("endpoint", ["/api/v1/studio/preview", "/api/v1/me"])
def test_studio_and_profile_require_signed_identity(preview_client, endpoint):
    client, _ = preview_client
    assert client.get(f"{endpoint}?admin=1&ux=3").status_code == 401


@pytest.mark.parametrize("tg_id", [123, 456])
@pytest.mark.parametrize("auth_method", ["telegram", "web"])
def test_banned_user_cannot_enter_studio(preview_client, tg_id, auth_method):
    client, user = preview_client
    user.tg_id = tg_id
    user.is_banned = True
    response = client.get("/api/v1/studio/preview", headers=_auth_headers(user, auth_method))
    assert response.status_code == 403
    assert response.json() == {"detail": "User is banned"}


@pytest.mark.parametrize("auth_method", ["telegram", "web"])
@pytest.mark.parametrize(
    ("method", "endpoint", "body"),
    [
        ("GET", "/api/v1/admin/overview", None),
        ("POST", "/api/v1/admin/users/8/credits", {"amount": 10, "note": "fixture"}),
    ],
)
def test_ordinary_user_cannot_access_admin_apis_with_client_admin_marker(
    preview_client, auth_method, method, endpoint, body,
):
    client, user = preview_client
    user.tg_id = 456
    response = client.request(
        method, f"{endpoint}?admin=1&ux=3", headers=_auth_headers(user, auth_method), json=body,
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}


@pytest.mark.parametrize("language", ["ru", "en"])
def test_new_studio_entry_is_an_extra_admin_webapp_button(language):
    admin = build_main_menu_keyboard(has_active_image_session=False, is_admin=True, lang=language)
    regular = build_main_menu_keyboard(has_active_image_session=False, is_admin=False, lang=language)
    admin_links = [button for row in admin.inline_keyboard for button in row if button.web_app]
    regular_links = [button for row in regular.inline_keyboard for button in row if button.web_app]
    assert len(admin_links) == 2
    assert len(regular_links) == 1
    assert admin_links[0].web_app.url == regular_links[0].web_app.url
    assert admin_links[1].web_app.url.endswith("/app?ux=3")
    assert "APIX" in admin_links[1].text

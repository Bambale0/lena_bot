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

    user = SimpleNamespace(id=7, tg_id=123, is_banned=False, is_admin=True)
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    monkeypatch.setattr(miniapp_auth, "_verify_init_data", lambda value: {"id": user.tg_id})
    monkeypatch.setattr(miniapp_auth.repo, "get_user_by_tg_id", AsyncMock(side_effect=lambda *_: user))
    app = FastAPI()
    app.include_router(miniapp_routes.router)
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client, user


def test_admin_can_admit_preview_without_caching_identity(preview_client):
    client, _ = preview_client
    response = client.get("/api/v1/studio/preview", headers={"X-Telegram-Init-Data": "signed-fixture"})
    assert response.status_code == 200
    assert response.json()["allowed"] is True
    assert response.json()["ui_version"] == 3
    assert "no-store" in response.headers["cache-control"]


def test_preview_does_not_trust_client_admin_marker(preview_client):
    client, user = preview_client
    user.tg_id = 456
    response = client.get("/api/v1/studio/preview?admin=1&ux=3", headers={"X-Telegram-Init-Data": "signed-fixture"})
    assert response.status_code == 403


def test_preview_requires_signed_identity(preview_client):
    client, _ = preview_client
    assert client.get("/api/v1/studio/preview?ux=3").status_code == 401


def test_banned_admin_cannot_enter_preview(preview_client):
    client, user = preview_client
    user.is_banned = True
    response = client.get("/api/v1/studio/preview", headers={"X-Telegram-Init-Data": "signed-fixture"})
    assert response.status_code == 403


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

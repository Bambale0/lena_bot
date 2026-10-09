from types import SimpleNamespace

import pytest

from api import miniapp_routes


@pytest.mark.parametrize(("tg_id", "expected"), [(123, True), (456, False), (None, False)])
def test_ux2_capability_uses_server_admin_membership(monkeypatch, tg_id, expected):
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    monkeypatch.setattr(miniapp_routes, "_telegram_start_link", lambda value: "https://t.me/test_bot?start=test")
    user = SimpleNamespace(id=1, tg_id=tg_id or 0, username="test", full_name="Test",
                           credits=0, referral_code="test", referral_balance=0, is_admin=True)
    profile = miniapp_routes._user_profile(user).model_dump()
    assert profile.get("miniapp_ux2_available") is expected

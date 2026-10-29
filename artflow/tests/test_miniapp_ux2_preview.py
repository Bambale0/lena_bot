from types import SimpleNamespace

import pytest

from api import miniapp_routes


@pytest.mark.parametrize(
    ("tg_id", "claimed_admin", "expected_admin"),
    [(123, False, True), (456, True, False)],
)
def test_studio_capability_is_separate_from_server_admin_membership(
    monkeypatch, tg_id, claimed_admin, expected_admin,
):
    monkeypatch.setattr(miniapp_routes.settings, "ADMIN_IDS", [123])
    user = SimpleNamespace(
        id=1, tg_id=tg_id, username="test", full_name="Test", credits=0,
        referral_code="test", referral_balance=0, is_admin=claimed_admin,
    )
    profile = miniapp_routes._user_profile(user).model_dump()
    assert profile["miniapp_ux2_available"] is True
    assert profile["is_admin"] is expected_admin

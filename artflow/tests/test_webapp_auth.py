from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from api.miniapp_auth import (
    _verify_init_data,
    create_web_auth_token,
    verify_telegram_login_data,
    verify_web_auth_token,
)


BOT_TOKEN = "123456:test-token"


def make_init_data(*, user_id: int = 42, auth_date: int | None = None, token: str = BOT_TOKEN) -> str:
    payload = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "test-query",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)


def make_login_data(*, user_id: int = 42, auth_date: int | None = None, token: str = BOT_TOKEN) -> dict:
    payload = {
        "id": user_id,
        "first_name": "Test",
        "last_name": "User",
        "username": "tester",
        "auth_date": auth_date or int(time.time()),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted((key, str(value)) for key, value in payload.items()))
    secret = hashlib.sha256(token.encode()).digest()
    payload["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return payload


def test__verify_init_data_accepts_valid_hash() -> None:
    data = _verify_init_data(make_init_data(user_id=777), bot_token=BOT_TOKEN)
    assert data["id"] == 777


def test__verify_init_data_rejects_tampered_payload() -> None:
    init_data = make_init_data(user_id=777).replace("777", "778")
    with pytest.raises(HTTPException) as exc:
        _verify_init_data(init_data, bot_token=BOT_TOKEN)
    assert exc.value.status_code == 401


def test__verify_init_data_rejects_expired_auth_date() -> None:
    expired = int(time.time()) - 8 * 24 * 60 * 60
    with pytest.raises(HTTPException) as exc:
        _verify_init_data(make_init_data(auth_date=expired), bot_token=BOT_TOKEN)
    assert exc.value.status_code == 401


def test_verify_telegram_login_data_accepts_valid_widget_hash() -> None:
    data = verify_telegram_login_data(make_login_data(user_id=888), bot_token=BOT_TOKEN)
    assert data["id"] == 888
    assert data["username"] == "tester"


def test_verify_telegram_login_data_rejects_tampered_widget_payload() -> None:
    payload = make_login_data(user_id=888)
    payload["username"] = "attacker"
    with pytest.raises(HTTPException) as exc:
        verify_telegram_login_data(payload, bot_token=BOT_TOKEN)
    assert exc.value.status_code == 401


def test_web_auth_token_roundtrip() -> None:
    token = create_web_auth_token(777, now=int(time.time()))
    assert verify_web_auth_token(token) == 777

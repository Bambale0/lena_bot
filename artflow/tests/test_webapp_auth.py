from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from api.webapp_auth import verify_telegram_init_data


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


def test_verify_telegram_init_data_accepts_valid_hash() -> None:
    data = verify_telegram_init_data(make_init_data(user_id=777), BOT_TOKEN)
    assert data["user"]["id"] == 777


def test_verify_telegram_init_data_rejects_tampered_payload() -> None:
    init_data = make_init_data(user_id=777).replace("777", "778")
    with pytest.raises(HTTPException) as exc:
        verify_telegram_init_data(init_data, BOT_TOKEN)
    assert exc.value.status_code == 401


def test_verify_telegram_init_data_rejects_expired_auth_date() -> None:
    expired = int(time.time()) - 8 * 24 * 60 * 60
    with pytest.raises(HTTPException) as exc:
        verify_telegram_init_data(make_init_data(auth_date=expired), BOT_TOKEN)
    assert exc.value.status_code == 401

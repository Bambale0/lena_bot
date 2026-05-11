#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx


def build_init_data(*, bot_token: str, user_id: int, username: str, first_name: str = "Smoke") -> str:
    payload = {
        "auth_date": str(int(time.time())),
        "query_id": "stars-smoke",
        "user": json.dumps(
            {"id": user_id, "first_name": first_name, "username": username},
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Telegram Stars topup endpoint")
    parser.add_argument("--base-url", required=True, help="Example: https://apix.chillcreative.ru")
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--username", required=True)
    parser.add_argument("--plan-key", default="credits_15")
    args = parser.parse_args()

    init_data = build_init_data(
        bot_token=args.bot_token,
        user_id=args.user_id,
        username=args.username,
    )
    headers = {"X-Telegram-Init-Data": init_data}

    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30.0) as client:
        me = client.get("/api/v1/me")
        me.raise_for_status()
        print("/api/v1/me", me.status_code, me.json().get("username"), me.json().get("credits"))

        first = client.post("/api/v1/topup/stars", json={"plan_key": args.plan_key})
        first.raise_for_status()
        first_data = first.json()
        print("first", first.status_code, first_data.get("transaction_id"), bool(first_data.get("invoice_link")))

        second = client.post("/api/v1/topup/stars", json={"plan_key": args.plan_key})
        second.raise_for_status()
        second_data = second.json()
        print("second", second.status_code, second_data.get("transaction_id"), bool(second_data.get("invoice_link")))

        same_tx = first_data.get("transaction_id") == second_data.get("transaction_id")
        print("same_pending_transaction=", same_tx)
        return 0 if same_tx else 1


if __name__ == "__main__":
    raise SystemExit(main())

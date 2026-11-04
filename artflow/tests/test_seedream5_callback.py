import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

import main
from api import kieai_client
from api import neironych_image_adapter as adapter
from core.kie_seedance_callback import callback_url_for_generation
from db.models import CreditLedgerEntry, Generation, GenerationStatus, GenerationType, User
from tests import test_kie_seedance_callback as callback_fixtures

LocalAsyncSession = callback_fixtures.LocalAsyncSession
kie_transaction_db = callback_fixtures.kie_transaction_db


async def test_http_signed_seedream_recovery_and_duplicate_are_atomic(kie_transaction_db, monkeypatch):
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_HMAC_KEY", "synthetic-seedream-hmac")
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "synthetic-secret")
    monkeypatch.setattr(main, "mirror_url", AsyncMock(side_effect=lambda url: url))
    with Session(kie_transaction_db, expire_on_commit=False) as session:
        row = session.get(Generation, 73)
        row.model = "seedream/5-pro-text-to-image"
        row.gen_type = GenerationType.image
        marker = "web:" + adapter.encode_kie_handoff_id(adapter.client_request_id_for_generation(73))
        row.task_id = marker
        session.commit()
        db = LocalAsyncSession(session)
        class SessionContext:
            async def __aenter__(self):
                return db
            async def __aexit__(self, *_args):
                return False
        monkeypatch.setattr(main, "AsyncSessionLocal", SessionContext)
        canonical = AsyncMock(return_value={"code": 200, "data": {
            "model": row.model, "taskId": "kie-seedream-result", "state": "success",
            "resultJson": json.dumps({"resultUrls": ["https://example.test/canonical.png"]}),
        }})
        monkeypatch.setattr(kieai_client, "get_task_status", canonical)
        url = callback_url_for_generation("http://test/webhook/kie?secret=synthetic-secret", 73)
        sig = parse_qs(urlparse(url).query)["apix_generation_sig"][0]
        body = {"task_id": "kie-seedream-result", "data": {"state": "failed", "failMsg": "untrusted callback body"}}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            invalid = await client.post(url.replace(sig, "invalid"), json=body)
            assert invalid.status_code == 403
            assert session.get(Generation, 73).task_id == marker
            canonical.assert_not_awaited()
            valid = await client.post(url, json=body)
            assert valid.status_code == 200, valid.text
            assert session.get(Generation, 73).status == GenerationStatus.done
            assert session.get(Generation, 73).result_url == "https://example.test/canonical.png"
            duplicate = await client.post(url, json=body)
            assert duplicate.status_code == 200
        assert session.get(User, 42).credits == 100
        assert list(session.scalars(select(CreditLedgerEntry))) == []
        assert main.mirror_url.await_count == 1

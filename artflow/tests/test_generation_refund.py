"""Regression tests: provider failures must refund credits atomically and honestly.

Reported production incident: the bot wrote "Кредиты возвращены" while the refund
could be skipped (lost race, crash between the fail commit and the refund commit).
These tests pin the contract:

* `repo.fail_generation_and_refund` fails the generation and credits the user in
  one commit, at most once, with an auditable ledger row;
* provider callbacks claim a refund only when a refund really happened, and a
  duplicate callback stays silent.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import main
from db import repository as repo
from db.models import CreditLedgerEntry, GenerationStatus


class _FakeSessionContext:
    async def __aenter__(self):
        return _FAKE_SESSION

    async def __aexit__(self, exc_type, exc, tb):
        return False


_FAKE_SESSION = object()


def _scalar_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


class _SessionStub:
    def __init__(self, *execute_results):
        self.execute = AsyncMock(side_effect=[_scalar_result(value) for value in execute_results])
        self.commit = AsyncMock()
        self.flush = AsyncMock()
        self.added: list = []

    def add(self, item) -> None:
        self.added.append(item)


@pytest.mark.asyncio
async def test_fail_generation_and_refund_credits_generation_once(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=77,
        user_id=42,
        status=GenerationStatus.processing,
        credits_spent=28,
        input_params=json.dumps({"model_key": "veo3"}),
        error_msg=None,
        finished_at=None,
    )
    session = _SessionStub(generation, 53.0)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())

    failed, refunded = await repo.fail_generation_and_refund(
        session, 77, "public error unsafe image upload"
    )

    assert (failed, refunded) == (True, 28.0)
    assert generation.status == GenerationStatus.failed
    assert generation.error_msg == "public error unsafe image upload"
    assert generation.finished_at is not None
    params = json.loads(generation.input_params)
    assert params["model_key"] == "veo3"
    assert params["refund_applied"] is True
    ledger = [item for item in session.added if isinstance(item, CreditLedgerEntry)]
    assert len(ledger) == 1
    entry = ledger[0]
    assert (entry.user_id, entry.delta, entry.balance_after) == (42, 28.0, 53.0)
    assert entry.entry_type == "generation_refund"
    assert (entry.source_type, entry.source_id) == ("generation", "77")
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_generation_and_refund_is_idempotent_for_final_generation(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=77,
        user_id=42,
        status=GenerationStatus.failed,
        credits_spent=28,
        input_params=None,
        error_msg="provider error",
        finished_at=None,
    )
    session = _SessionStub(generation)
    publish = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", publish)

    failed, refunded = await repo.fail_generation_and_refund(session, 77, "duplicate callback")

    assert (failed, refunded) == (False, 0.0)
    assert session.added == []
    session.commit.assert_not_awaited()
    publish.assert_not_awaited()
    assert generation.status == GenerationStatus.failed


@pytest.mark.asyncio
async def test_fail_generation_and_refund_skips_credit_when_nothing_was_charged(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=88,
        user_id=42,
        status=GenerationStatus.pending,
        credits_spent=0,
        input_params=None,
        error_msg=None,
        finished_at=None,
    )
    session = _SessionStub(generation)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())

    failed, refunded = await repo.fail_generation_and_refund(session, 88, "provider unavailable")

    assert (failed, refunded) == (True, 0.0)
    assert session.added == []
    session.commit.assert_awaited_once()
    assert json.loads(generation.input_params)["refund_applied"] is False
    assert session.execute.await_count == 1


def _pending_video_generation(**overrides):
    payload = {
        "id": 77,
        "user_id": 42,
        "status": SimpleNamespace(value="processing"),
        "gen_type": main.GenerationType.video,
        "image_session_id": None,
        "model": "veo3",
        "prompt": "scene",
        "credits_spent": 28,
        "source_feed_gen_id": None,
        "action_type": None,
        "task_id": "ff554d5a20bb31f390bee57171950ae9",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _failed_payload() -> dict:
    return {
        "code": 500,
        "data": {
            "taskId": "ff554d5a20bb31f390bee57171950ae9",
            "state": "failed",
            "failMsg": "public error unsafe image upload",
        },
    }


def _patch_kie_failure_webhook(monkeypatch, refund_result, bot):
    fail_generation_and_refund = AsyncMock(return_value=refund_result)
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(
        main.repo, "get_generation_by_task_id", AsyncMock(return_value=_pending_video_generation())
    )
    monkeypatch.setattr(
        main.repo,
        "get_user_by_id",
        AsyncMock(return_value=SimpleNamespace(id=42, tg_id=555111)),
    )
    monkeypatch.setattr(main.repo, "fail_generation_and_refund", fail_generation_and_refund)
    monkeypatch.setattr(main, "bot", bot)
    return fail_generation_and_refund


@pytest.mark.asyncio
async def test_kie_failure_callback_refunds_and_reports_returned_credits(monkeypatch) -> None:
    bot = AsyncMock()
    fail_generation_and_refund = _patch_kie_failure_webhook(monkeypatch, (True, 28.0), bot)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie", json=_failed_payload())

    assert response.status_code == 200
    fail_generation_and_refund.assert_awaited_once()
    assert fail_generation_and_refund.await_args.args[1:] == (
        77,
        "public error unsafe image upload",
    )
    assert fail_generation_and_refund.await_args.kwargs["refund_note"].startswith("kie_webhook:")
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.args[1]
    assert "Генерация не удалась." in text
    assert "Кредиты возвращены." in text


@pytest.mark.asyncio
async def test_kie_failure_callback_without_refund_does_not_promise_credits(monkeypatch) -> None:
    bot = AsyncMock()
    _patch_kie_failure_webhook(monkeypatch, (True, 0.0), bot)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie", json=_failed_payload())

    assert response.status_code == 200
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.args[1]
    assert "Генерация не удалась." in text
    assert "Кредиты возвращены" not in text


@pytest.mark.asyncio
async def test_kie_duplicate_failure_callback_stays_silent(monkeypatch) -> None:
    bot = AsyncMock()
    fail_generation_and_refund = _patch_kie_failure_webhook(monkeypatch, (False, 0.0), bot)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie", json=_failed_payload())

    assert response.status_code == 200
    fail_generation_and_refund.assert_awaited_once()
    bot.send_message.assert_not_awaited()

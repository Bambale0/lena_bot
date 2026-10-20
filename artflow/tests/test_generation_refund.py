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
async def test_missing_identity_refund_does_not_race_new_provider_binding(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=78, user_id=42, status=GenerationStatus.processing,
        task_id="neironych:new-provider-id", credits_spent=70,
        input_params="{}", error_msg=None, finished_at=None,
    )
    session = _SessionStub(generation)
    publish = AsyncMock()
    monkeypatch.setattr(repo, "_publish_generation_update", publish)

    result = await repo.fail_generation_and_refund(
        session, 78, "timeout", require_missing_task_id=True,
    )
    assert result == (False, 0.0)
    assert generation.status == GenerationStatus.processing
    assert session.added == []
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_identity_refund_does_not_race_submission_marker(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=79, user_id=42, status=GenerationStatus.processing,
        task_id=None, credits_spent=70,
        input_params=json.dumps({repo.SEEDANCE_SUBMISSION_KEY: {"client_request_id": "persisted"}}),
        error_msg=None, finished_at=None,
    )
    session = _SessionStub(generation)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    assert await repo.fail_generation_and_refund(
        session, 79, "timeout", require_missing_task_id=True,
    ) == (False, 0.0)
    assert generation.status == GenerationStatus.processing
    assert session.added == []


@pytest.mark.asyncio
async def test_kie_callback_refund_preserves_virtual_identity_under_lock(monkeypatch) -> None:
    generation = SimpleNamespace(
        id=80, user_id=42, status=GenerationStatus.processing,
        task_id=None, credits_spent=70,
        input_params=json.dumps({repo.KIE_VIDEO_CALLBACK_KEY: {
            "generation_id": 80, "surface": "web",
        }}), error_msg=None, finished_at=None,
    )
    session = _SessionStub(generation, 170.0)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    changed, amount = await repo.fail_generation_and_refund(
        session, 80, "timeout", require_missing_task_id=True,
        recovery_task_id="web:kie-submit:80",
        provider_review={"state": "pending", "original_task_id": "web:kie-submit:80"},
    )
    assert (changed, amount) == (True, 70.0)
    assert generation.task_id == "web:kie-submit:80"
    assert json.loads(generation.input_params)[repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY]["state"] == "pending"


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
@pytest.mark.parametrize("raw, expected", [
    ("The request failed because the output image may be related to copyright restrictions.", "авторских прав"),
    ("Image fetch failed. Check access settings or use our File Upload API instead.", "Загрузи фото заново"),
])
async def test_kie_image_rejection_notice_keeps_safe_reason_and_guarded_refund(monkeypatch, raw, expected):
    bot = AsyncMock()
    refund = _patch_kie_failure_webhook(monkeypatch, (True, 2.0), bot)
    generation = _pending_video_generation(
        gen_type=main.GenerationType.image, model="seedream/5-pro-text-to-image",
        source_feed_gen_id=3,
    )
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", AsyncMock(return_value=generation))
    payload = _failed_payload()
    payload["data"]["failMsg"] = raw + " private-recipe-must-not-leak"
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie", json=payload)
    assert response.status_code == 200
    refund.assert_awaited_once()
    assert refund.await_args.args[2] == payload["data"]["failMsg"]
    text = bot.send_message.await_args.args[1]
    assert expected in text
    assert "private-recipe-must-not-leak" not in text
    assert "Кредиты возвращены" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("refunded", [1.5, 0.0])
async def test_nexus_image_failure_uses_short_honest_message(monkeypatch, refunded) -> None:
    provider_error = (
        "⚠️ Не удалось сгенерировать контент. Попробуйте изменить параметры "
        "(сид, промпт) и повторить попытку."
    )
    bot = AsyncMock()
    _patch_kie_failure_webhook(monkeypatch, (True, refunded), bot)
    image = _pending_video_generation(
        id=42,
        gen_type=main.GenerationType.image,
        model="nano-banana-pro",
        task_id="nexus:ff554d5a20bb31f390bee57171950ae9",
    )
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", AsyncMock(return_value=image))
    monkeypatch.setattr(
        main.nexus_image_adapter,
        "get_nexus_task_payload",
        AsyncMock(return_value={
            "task_id": "ff554d5a20bb31f390bee57171950ae9",
            "status": "failed",
            "error": provider_error,
        }),
    )

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie?provider=nexus", json=_failed_payload())

    assert response.status_code == 200
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.args[1]
    assert "Изображение не создано" in text
    if refunded:
        assert "1,5 💋 вернулись на баланс" in text
    else:
        assert "вернулись на баланс" not in text
    assert "Задача #42" in text
    assert "сид" not in text
    assert "ff554d5a" not in text
    assert "<code>" not in text


@pytest.mark.asyncio
async def test_nexus_failure_notice_bounds_long_provider_error(monkeypatch) -> None:
    bot = AsyncMock()
    _patch_kie_failure_webhook(monkeypatch, (True, 1.5), bot)
    image = _pending_video_generation(
        gen_type=main.GenerationType.image,
        model="nano-banana-pro",
        task_id="nexus:ff554d5a20bb31f390bee57171950ae9",
    )
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", AsyncMock(return_value=image))
    monkeypatch.setattr(
        main.nexus_image_adapter,
        "get_nexus_task_payload",
        AsyncMock(return_value={
            "task_id": "ff554d5a20bb31f390bee57171950ae9",
            "status": "failed",
            "error": "&" * 5000,
        }),
    )

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie?provider=nexus", json=_failed_payload())

    assert response.status_code == 200
    notice = bot.send_message.await_args.args[1]
    assert len(notice) < 4096
    assert "вернулись на баланс" in notice


@pytest.mark.asyncio
async def test_kie_duplicate_failure_callback_stays_silent(monkeypatch) -> None:
    bot = AsyncMock()
    fail_generation_and_refund = _patch_kie_failure_webhook(monkeypatch, (False, 0.0), bot)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/kie", json=_failed_payload())

    assert response.status_code == 200
    fail_generation_and_refund.assert_awaited_once()
    bot.send_message.assert_not_awaited()

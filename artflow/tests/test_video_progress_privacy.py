"""Consumer status policy: internal recovery is silent; terminal events still deliver."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api import miniapp_routes
from db import repository as repo
from db.models import GenerationStatus
from tests.test_neironych_video_notice_outbox import FakeSession
from tests.test_seedance_uncertain_submission import generation


@pytest.mark.asyncio
async def test_new_review_marker_is_internal_and_no_credit_change(monkeypatch):
    gen = generation()
    db = FakeSession(gen)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    assert await repo.mark_neironych_video_reconciliation(db, gen.id, expected_task_id=gen.task_id)
    meta = json.loads(gen.input_params)
    assert meta["neironych_video_reconciliation"]["required"] is True
    assert meta[repo.NEIRONYCH_VIDEO_NOTICE_KEY]["state"] == "suppressed"
    assert meta[repo.NEIRONYCH_VIDEO_NOTICE_KEY]["attempts"] == 0
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    assert gen.status == GenerationStatus.processing and gen.credits_spent == 70
    assert "refund_applied" not in meta


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "sending"])
async def test_queued_legacy_review_is_suppressed_not_sent_or_retried(state):
    gen = generation()
    gen.input_params = json.dumps({
        repo.NEIRONYCH_VIDEO_NOTICE_KEY: {
            "kind": "reconciliation", "state": state, "attempts": 1,
            "token": "legacy-claim", "claimed_at": "2000-01-01T00:00:00+00:00",
        },
        "neironych_video_reconciliation": {"required": True},
    })
    db = FakeSession(gen)
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    notice = json.loads(gen.input_params)[repo.NEIRONYCH_VIDEO_NOTICE_KEY]
    assert notice["state"] == "suppressed"
    assert notice["attempts"] == 1
    assert "sent_at" not in notice and "token" not in notice
    assert await repo.claim_neironych_video_notice(db, gen.id) is None
    assert gen.status == GenerationStatus.processing and gen.credits_spent == 70


@pytest.mark.asyncio
async def test_legacy_review_sender_never_contacts_telegram(monkeypatch):
    factory = Mock(return_value=SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=123)),
        session=SimpleNamespace(close=AsyncMock()),
    ))
    monkeypatch.setattr(miniapp_routes, "Bot", factory)
    assert await miniapp_routes._notify_neironych_video_reconciliation_in_bot(
        user=SimpleNamespace(tg_id=42), gen=generation(),
    ) is False
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_already_claimed_review_is_suppressed_before_user_io(monkeypatch):
    gen = generation()
    gen.input_params = json.dumps({repo.NEIRONYCH_VIDEO_NOTICE_KEY: {
        "kind": "reconciliation", "state": "sending", "token": "old-token", "attempts": 1,
    }})
    claim = SimpleNamespace(generation=gen, kind="reconciliation", token="old-token", attempt=1)
    monkeypatch.setattr(repo, "claim_neironych_video_notice", AsyncMock(return_value=claim))
    user_lookup = AsyncMock()
    monkeypatch.setattr(repo, "get_user_by_id", user_lookup)
    factory = Mock(return_value=SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=123)),
        session=SimpleNamespace(close=AsyncMock()),
    ))
    monkeypatch.setattr(miniapp_routes, "Bot", factory)
    assert not await miniapp_routes._deliver_pending_neironych_video_notice(FakeSession(gen), gen.id)
    user_lookup.assert_not_awaited()
    factory.assert_not_called()
    assert json.loads(gen.input_params)[repo.NEIRONYCH_VIDEO_NOTICE_KEY]["state"] == "suppressed"


@pytest.mark.asyncio
async def test_final_error_is_simple_and_reports_only_confirmed_refund(monkeypatch):
    gen = generation()
    gen.status = GenerationStatus.failed
    gen.input_params = json.dumps({"refund_applied": True})
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)),
                          session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(miniapp_routes, "Bot", lambda **kwargs: bot)
    assert await miniapp_routes._notify_reconciled_video_failure_in_bot(user=SimpleNamespace(tg_id=42), gen=gen)
    text = bot.send_message.await_args.kwargs["text"]
    assert "Видео не удалось создать" in text and "70 кредитов" in text
    assert not re.search(r"поставщик|провайдер|reconcil|удержан", text, re.I)


def test_site_status_remains_active_with_neutral_consumer_copy():
    script = Path("landing/js/prototype-premium.js").read_text()
    functions = [re.search(r"function " + name + r"\([^\n]*\) \{.*?\n\}", script, re.S).group(0)
                 for name in ("generationIsActive", "generationStatusCopy", "statusLabel")]
    check = """
    const status='reconciliation_required';
    if (!generationIsActive(status)) process.exit(1);
    if (generationIsActive('done') || generationIsActive('failed')) process.exit(2);
    if (statusLabel(status) !== statusLabel('processing')) process.exit(3);
    if (/поставщик|провайдер|удержан|уточняем|проверка/i.test(generationStatusCopy(status))) process.exit(4);
    """
    result = subprocess.run(["node", "-e", "\n".join(functions) + check], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_old_suppression_token_cannot_consume_ready_video():
    gen = generation()
    gen.status = GenerationStatus.done
    gen.input_params = json.dumps({repo.NEIRONYCH_VIDEO_NOTICE_KEY: {
        "kind": "done", "state": "pending", "attempts": 0,
    }})
    db = FakeSession(gen)
    assert not await repo.suppress_claimed_neironych_review_notice(db, gen.id, "old-token")
    new = await repo.claim_neironych_video_notice(db, gen.id)
    assert new and new.kind == "done"


@pytest.mark.parametrize("notice_state", ["pending", "sending"])
@pytest.mark.asyncio
async def test_terminal_error_delivery_is_not_suppressed_by_new_review_policy(notice_state):
    gen = generation()
    gen.status = GenerationStatus.failed
    gen.input_params = json.dumps({repo.NEIRONYCH_VIDEO_NOTICE_KEY: {
        "kind": "failed", "state": notice_state, "attempts": 0,
        "claimed_at": "2000-01-01T00:00:00+00:00",
    }})
    claim = await repo.claim_neironych_video_notice(FakeSession(gen), gen.id)
    assert claim and claim.kind == "failed"


def test_active_frontends_contain_no_intermediate_supplier_copy():
    targets = [
        "webapp/src/main.jsx", "webapp/src/apix/AppV4.jsx",
        "webapp/src/lib/utils.ts", "webapp/src/features/works-screen.tsx",
        "webapp/src/components/task-detail-sheet.tsx", "landing/js/prototype-premium.js",
    ]
    for path in targets:
        text = Path(path).read_text()
        assert not re.search(r"Уточняем статус|уточняем статус|Кредиты пока удержаны|Under provider review", text), path

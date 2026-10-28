"""Crash-safe KIE submission journal: no extra paid work on fallback."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes  # noqa: F401 - initializes dependencies
from db import repository as repo
from db.models import GenerationStatus, GenerationType

UUID = "d4496f2e-37d8-4b87-bba2-330374892b49"


def generation(*, started_primary=False, unknown_primary=False):
    metadata = {"kie_video_callback": {"generation_id": 703, "surface": "telegram_bot"}}
    if started_primary:
        metadata[repo.SEEDANCE_SUBMISSION_KEY] = {
            "client_request_id": UUID,
            "product_model": "wan/3-0-video",
            "state": "submission_unknown" if unknown_primary else "submitting",
        }
    return SimpleNamespace(
        id=703, model="wan/3-0-video", gen_type=GenerationType.video,
        status=GenerationStatus.processing,
        task_id=f"neironych-submit:{UUID}" if started_primary else None,
        input_params=json.dumps(metadata),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("from_primary", [True, False])
async def test_kie_admission_persisted_before_paid_post(monkeypatch, from_primary):
    row = generation(started_primary=from_primary)
    session = AsyncMock()
    monkeypatch.setattr(repo, "_locked_seedance_generation", AsyncMock(return_value=row))
    assert await repo.begin_kie_video_submission(session, row.id, UUID) is True
    assert row.task_id == "kie-submit:703"
    metadata = repo.parse_input_params(row.input_params)
    assert metadata[repo.KIE_VIDEO_SUBMISSION_KEY]["state"] == "submitting"
    assert metadata[repo.KIE_VIDEO_SUBMISSION_KEY]["correlation_id"] == 703
    if from_primary:
        assert metadata[repo.SEEDANCE_SUBMISSION_KEY]["state"] == "definite_rejected_fallback_kie"
    session.commit.assert_awaited_once()
    # A second handler never purchases another job using the same row.
    assert await repo.begin_kie_video_submission(session, row.id, UUID) is False


@pytest.mark.asyncio
async def test_ambiguous_neironych_submission_never_admits_kie(monkeypatch):
    row = generation(started_primary=True, unknown_primary=True)
    session = AsyncMock()
    monkeypatch.setattr(repo, "_locked_seedance_generation", AsyncMock(return_value=row))
    assert await repo.begin_kie_video_submission(session, row.id, UUID) is False
    assert row.task_id == f"neironych-submit:{UUID}"


@pytest.mark.asyncio
async def test_context_persists_kie_journal_and_marks_provider_specific_state(monkeypatch):
    from core import seedance_reconciliation as admission
    db = AsyncMock()
    start = AsyncMock(return_value=True)
    reject = AsyncMock(return_value=True)
    monkeypatch.setattr(repo, "begin_kie_video_submission", start)
    monkeypatch.setattr(repo, "mark_kie_video_definite_rejection", reject)
    ctx = admission.make_submission_context(db, 703, "wan/3-0-video", surface="telegram_bot")
    assert ctx.before_kie_submit is not None
    await ctx.before_kie_submit()
    assert ctx.kie_started is True
    start.assert_awaited_once_with(db, 703, ctx.client_request_id)
    assert ctx.after_kie_definite_rejection is not None
    await ctx.after_kie_definite_rejection()
    assert ctx.kie_definitely_rejected is True
    reject.assert_awaited_once_with(db, 703)
    with pytest.raises(Exception):
        await ctx.before_kie_submit()
    assert start.await_count == 1


@pytest.mark.asyncio
async def test_kie_fallback_result_binds_kie_journal_not_old_neironych_marker(monkeypatch):
    from api.neironych_seedance_runtime import SubmissionContext
    from core import seedance_reconciliation as admission

    context = SubmissionContext(
        client_request_id=UUID, before_submit=AsyncMock(),
        started=True, kie_started=True, before_kie_submit=AsyncMock(),
    )
    bind_kie = AsyncMock(return_value=SimpleNamespace(id=703))
    bind_neironych = AsyncMock()
    monkeypatch.setattr(repo, "bind_kie_video_callback", bind_kie)
    monkeypatch.setattr(repo, "bind_seedance_submission_task", bind_neironych)
    db = AsyncMock()
    success = await admission.persist_submission_result(
        db, 703, context, "kie_paid_777", surface="telegram_bot",
    )
    assert success is True
    bind_kie.assert_awaited_once_with(db, 703, "kie_paid_777")
    bind_neironych.assert_not_awaited()


def test_paid_submission_uses_journal_for_kie_even_without_primary_neironych():
    from api.neironych_seedance_runtime import SubmissionContext
    from core.seedance_reconciliation import has_paid_submission_journal

    context = SubmissionContext(
        client_request_id=UUID,
        before_submit=AsyncMock(),
        before_kie_submit=AsyncMock(),
        kie_started=True,
        started=False,
    )
    assert has_paid_submission_journal(context) is True
    context.kie_started = False
    assert has_paid_submission_journal(context) is False
    context.started = True
    assert has_paid_submission_journal(context) is True

@pytest.mark.asyncio
async def test_web_kie_binding_receives_raw_provider_id_not_double_web_prefix(monkeypatch):
    from api.neironych_seedance_runtime import SubmissionContext
    from core.seedance_reconciliation import persist_submission_result

    context = SubmissionContext(
        client_request_id=UUID, before_submit=AsyncMock(),
        before_kie_submit=AsyncMock(), kie_started=True,
    )
    bind=AsyncMock(return_value=SimpleNamespace(id=703))
    monkeypatch.setattr(repo, "bind_kie_video_callback", bind)
    accepted=await persist_submission_result(
        AsyncMock(), 703, context, "kie_provider_123", surface="web",
    )
    assert accepted is True
    assert bind.await_count == 1
    assert bind.await_args.args[1:] == (703, "kie_provider_123")

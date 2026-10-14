"""Regression coverage for provider jobs that stayed active after their result was known."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from api import image_service, miniapp_routes, neironych_image_adapter, nexus_image_adapter
from core import neironych_image_reconcile_scheduler as image_scheduler
from db import repository as repo
from db.models import GenerationStatus, GenerationType


def test_image_scheduler_selects_all_nexus_image_models():
    compiled = image_scheduler._eligible_query().compile(dialect=postgresql.dialect())
    values = list(compiled.params.values())
    model_values = {item for value in values for item in (
        value if isinstance(value, (list, tuple, set)) else (value,)
    ) if isinstance(item, str)}
    assert {"nano-banana-pro", "nano-banana-2", "gpt-image-2-vip", "nano-banana-2.1"} <= model_values
    assert "%nexus:%" in model_values


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["nano-banana-pro", "nano-banana-2", "gpt-image-2-vip"])
async def test_nexus_image_models_use_identity_checked_poll(monkeypatch, model):
    poll = AsyncMock(return_value=None)
    monkeypatch.setattr(image_service, "poll_image_result_urls", poll)
    monkeypatch.setattr(nexus_image_adapter, "submission_scope_matches", lambda _: True)
    gen = SimpleNamespace(
        id=10, task_id="nexus:provider-task", model=model,
        gen_type=GenerationType.image, status=GenerationStatus.processing,
        created_at=datetime.now(timezone.utc), input_params="{}",
    )
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    poll.assert_awaited_once_with("nexus:provider-task", strict_nexus=True)


@pytest.mark.asyncio
async def test_stale_neironych_unknown_refunds_once_without_resubmission(monkeypatch):
    gen = SimpleNamespace(
        id=20, task_id="neironych-image:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        model="nano-banana-2.1", gen_type=GenerationType.image,
        status=GenerationStatus.processing,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    fetch = AsyncMock(return_value={"status": "not_found", "result_url": None})
    refund = AsyncMock(return_value=(True, 1.0))
    final = SimpleNamespace(status=GenerationStatus.failed)
    monkeypatch.setattr(neironych_image_adapter, "fetch_nano_banana21_status", fetch)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=final))
    assert await miniapp_routes._reconcile_neironych_image_generation(
        object(), gen, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    ) is final
    refund.assert_awaited_once()
    assert refund.await_args.kwargs["expected_task_id"] == gen.task_id


@pytest.mark.asyncio
async def test_stale_nexus_pending_refunds_once_without_resubmission(monkeypatch):
    gen = SimpleNamespace(
        id=21, task_id="nexus:provider-task", model="nano-banana-pro",
        gen_type=GenerationType.image, status=GenerationStatus.processing,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        input_params="{}",
    )
    monkeypatch.setattr(image_service, "poll_image_result_urls", AsyncMock(return_value=None))
    monkeypatch.setattr(nexus_image_adapter, "submission_scope_matches", lambda _: True)
    refund = AsyncMock(return_value=(True, 1.5))
    final = SimpleNamespace(status=GenerationStatus.failed)
    monkeypatch.setattr(repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(repo, "get_generation_by_id", AsyncMock(return_value=final))
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is final
    refund.assert_awaited_once()
    assert refund.await_args.kwargs["expected_task_id"] == gen.task_id

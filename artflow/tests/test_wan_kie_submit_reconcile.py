"""A durable KIE submission marker must not be sent to the provider poller."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from api import miniapp_routes
from db.models import GenerationStatus, GenerationType

@pytest.mark.asyncio
@pytest.mark.parametrize('task_id', ['kie-submit:61578', 'web:kie-submit:61578'])
async def test_pending_kie_submission_is_not_pollable(monkeypatch, task_id):
    poll = AsyncMock(side_effect=AssertionError('must not poll submission marker'))
    monkeypatch.setattr(miniapp_routes.video_service, 'poll_kieai_status', poll)
    gen = SimpleNamespace(id=61578, task_id=task_id, status=GenerationStatus.processing,
        gen_type=GenerationType.video, model='wan/3-0-video', created_at=datetime.now(timezone.utc))
    result = await miniapp_routes._reconcile_generation_status(AsyncMock(), gen)
    assert result is gen
    poll.assert_not_awaited()

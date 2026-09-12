from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from api.video_prompt_limits import video_prompt_max_chars
from bot.handlers import image_gen
from bot.utils.dispatcher import create_dispatcher


@pytest.mark.asyncio
async def test_image_session_recovers_model_from_active_session_when_fsm_lost_model_key() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"image_session_id": 11})
    existing = SimpleNamespace(
        id=11,
        model="nano-banana-pro",
        aspect_ratio="1:1",
        count=1,
        quality="2K",
        mode="text",
        reference_file_id=None,
        reference_file_ids=None,
    )
    repo_stub = SimpleNamespace(
        get_active_image_session=AsyncMock(return_value=existing),
        create_image_session=AsyncMock(),
    )

    with patch("bot.handlers.image_gen.repo", new=repo_stub):
        result = await image_gen._ensure_active_image_session_from_state(
            session=AsyncMock(),
            state=state,
            db_user=SimpleNamespace(id=42),
        )

    assert result is existing
    repo_stub.create_image_session.assert_not_awaited()
    state.update_data.assert_awaited()
    assert state.update_data.await_args.kwargs["model_key"] == "nano-banana-pro"




@pytest.mark.asyncio
async def test_image_session_uses_default_model_when_fsm_and_db_have_no_model() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    created = SimpleNamespace(id=12)
    repo_stub = SimpleNamespace(
        get_active_image_session=AsyncMock(return_value=None),
        create_image_session=AsyncMock(return_value=created),
    )

    with patch("bot.handlers.image_gen.repo", new=repo_stub):
        result = await image_gen._ensure_active_image_session_from_state(
            session=AsyncMock(),
            state=state,
            db_user=SimpleNamespace(id=42),
        )

    assert result is created
    assert repo_stub.create_image_session.await_args.kwargs["model"] == image_gen.NANA_BANANO_DEFAULT_MODEL
    state.update_data.assert_any_await(model_key=image_gen.NANA_BANANO_DEFAULT_MODEL)


def test_kling_30_prompt_limit_matches_provider_contract() -> None:
    assert video_prompt_max_chars("kling-3.0/video") == 2500
    assert video_prompt_max_chars("kling/v3-turbo-text-to-video") == 2500
    assert video_prompt_max_chars("kling/v3-turbo-image-to-video") == 2500

    frontend = Path("webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")
    assert 'KLING_3_MODELS' in frontend
    assert 'return 2500' in frontend


class _RedisLikeStorage(MemoryStorage):
    def __init__(self) -> None:
        super().__init__()
        self.isolation_kwargs = None

    def create_isolation(self, **kwargs):
        self.isolation_kwargs = kwargs
        return SimpleEventIsolation()


def test_dispatcher_extends_redis_fsm_lock_for_long_updates() -> None:
    storage = _RedisLikeStorage()
    create_dispatcher(storage)

    assert storage.isolation_kwargs == {"lock_kwargs": {"timeout": 300}}


def test_video_failure_paths_do_not_read_expired_generation_after_rollback() -> None:
    source = Path("api/miniapp_routes.py").read_text(encoding="utf-8")

    assert source.count("failed_generation_id = gen.id") >= 2
    assert source.count("failed_user_id = user.id") >= 2
    assert "await repo.fail_generation(session, failed_generation_id, str(exc))" in source
    assert "await repo.add_credits(session, failed_user_id, total_credits)" in source


def test_artflow_nginx_uses_real_compose_backend() -> None:
    nginx = Path("nginx.conf").read_text(encoding="utf-8")

    marker = "# BEGIN ARHIBOT MANAGED"
    managed = nginx.split(marker, 1)[0] if marker in nginx else nginx
    assert "proxy_pass http://artflow-app-1:8000;" in managed
    assert "proxy_pass http://api:8080;" not in managed

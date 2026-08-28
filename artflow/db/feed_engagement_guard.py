from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.config import settings
from core.request_identity import bind_current_user, current_user_id
from db.feed_engagement import FeedEngagementResult, record_feed_engagement

logger = logging.getLogger(__name__)

EngagementRecorder = Callable[..., Awaitable[FeedEngagementResult]]


def _is_production() -> bool:
    return str(getattr(settings, "ENV", "") or "").strip().lower() in {"prod", "production"}


def install_feed_engagement_guard(
    repository_module: Any,
    *,
    recorder: EngagementRecorder = record_feed_engagement,
) -> None:
    """Install user-level idempotency around the legacy aggregate counters.

    Public callers keep the existing repository interface. The authenticated
    user is captured when auth resolves the first Telegram-backed user in the
    request/update context, then like/share writes are routed through the
    unique feed_engagements table.
    """
    if getattr(repository_module, "_feed_engagement_guard_installed", False):
        return

    original_get_user_by_tg_id = repository_module.get_user_by_tg_id
    original_like = repository_module.like_feed_generation
    original_share = repository_module.increment_feed_share

    async def contextual_get_user_by_tg_id(session, tg_id: int):
        user = await original_get_user_by_tg_id(session, tg_id)
        if user is not None and current_user_id() is None:
            bind_current_user(int(user.id))
        return user

    async def _record_or_legacy(session, gen_id: int, action: str, legacy):
        user_id = current_user_id()
        if user_id is None:
            logger.warning(
                "Feed engagement without request identity: action=%s generation_id=%s",
                action,
                gen_id,
            )
            if _is_production():
                return await repository_module.get_public_feed_generation(session, int(gen_id))
            return await legacy(session, int(gen_id))

        result = await recorder(
            session,
            generation_id=int(gen_id),
            user_id=int(user_id),
            action=action,
        )
        return result.generation

    async def like_feed_generation(session, gen_id: int):
        return await _record_or_legacy(session, gen_id, "like", original_like)

    async def increment_feed_share(session, gen_id: int):
        return await _record_or_legacy(session, gen_id, "share", original_share)

    repository_module.get_user_by_tg_id = contextual_get_user_by_tg_id
    repository_module.like_feed_generation = like_feed_generation
    repository_module.increment_feed_share = increment_feed_share
    repository_module._feed_engagement_guard_installed = True

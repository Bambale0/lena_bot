from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from core.request_identity import clear_current_user, current_user_id, reset_current_user
from db.feed_engagement import FeedEngagementResult, record_feed_engagement
from db.feed_engagement_guard import install_feed_engagement_guard


@pytest.mark.asyncio
async def test_like_engagement_uses_unique_database_insert_before_counter_update() -> None:
    session = AsyncMock()
    generation = MagicMock(id=42)

    current = MagicMock()
    current.scalar_one_or_none.return_value = generation
    inserted = MagicMock()
    inserted.scalar_one_or_none.return_value = 101
    updated = MagicMock()
    session.execute = AsyncMock(side_effect=[current, inserted, updated])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await record_feed_engagement(
        session,
        generation_id=42,
        user_id=7,
        action="like",
    )

    insert_statement = session.execute.await_args_list[1].args[0]
    insert_sql = str(
        insert_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ON CONFLICT ON CONSTRAINT uq_feed_engagement_user_generation_action DO NOTHING" in insert_sql

    update_statement = session.execute.await_args_list[2].args[0]
    update_sql = str(update_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "likes_count" in update_sql
    assert result.created is True
    assert result.generation is generation
    session.refresh.assert_awaited_once_with(generation)


@pytest.mark.asyncio
async def test_duplicate_engagement_does_not_increment_aggregate_counter() -> None:
    session = AsyncMock()
    generation = MagicMock(id=42)

    current = MagicMock()
    current.scalar_one_or_none.return_value = generation
    duplicate = MagicMock()
    duplicate.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[current, duplicate])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await record_feed_engagement(
        session,
        generation_id=42,
        user_id=7,
        action="share",
    )

    assert result.created is False
    assert result.generation is generation
    assert session.execute.await_count == 2
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_repository_guard_routes_like_and_share_through_authenticated_user() -> None:
    user = SimpleNamespace(id=7)
    generation = SimpleNamespace(id=42)
    original_get_user = AsyncMock(return_value=user)
    original_like = AsyncMock(return_value=generation)
    original_share = AsyncMock(return_value=generation)
    repository = SimpleNamespace(
        get_user_by_tg_id=original_get_user,
        like_feed_generation=original_like,
        increment_feed_share=original_share,
        get_public_feed_generation=AsyncMock(return_value=generation),
    )
    recorder = AsyncMock(return_value=FeedEngagementResult(generation=generation, created=True))

    install_feed_engagement_guard(repository, recorder=recorder)

    token = clear_current_user()
    try:
        resolved = await repository.get_user_by_tg_id(AsyncMock(), 100500)
        assert resolved is user
        assert current_user_id() == 7

        await repository.like_feed_generation(AsyncMock(), 42)
        await repository.increment_feed_share(AsyncMock(), 42)
    finally:
        reset_current_user(token)

    actions = [call.kwargs["action"] for call in recorder.await_args_list]
    assert actions == ["like", "share"]
    assert all(call.kwargs["user_id"] == 7 for call in recorder.await_args_list)
    original_like.assert_not_awaited()
    original_share.assert_not_awaited()

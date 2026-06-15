from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from db import repository


@pytest.mark.asyncio
async def test_like_feed_generation_updates_only_public_posts(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(repository, "get_generation_by_id", AsyncMock(return_value=None))

    await repository.like_feed_generation(session, gen_id=42)

    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "is_public_feed IS true" in compiled


@pytest.mark.asyncio
async def test_increment_feed_share_updates_only_public_posts(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(repository, "get_generation_by_id", AsyncMock(return_value=None))

    await repository.increment_feed_share(session, gen_id=42)

    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "is_public_feed IS true" in compiled


@pytest.mark.asyncio
async def test_share_to_feed_blocks_feed_derivatives(monkeypatch) -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    get_generation_by_id = AsyncMock()
    monkeypatch.setattr(repository, "get_generation_by_id", get_generation_by_id)

    shared = await repository.share_to_feed(session, gen_id=42, user_id=7)

    assert shared is None
    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "source_feed_gen_id IS NULL" in compiled
    assert "source_feed_gen_id IN" in compiled
    assert "user_id = 7" in compiled
    get_generation_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_share_to_library_blocks_feed_derivatives(monkeypatch) -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    get_generation_by_id = AsyncMock()
    monkeypatch.setattr(repository, "get_generation_by_id", get_generation_by_id)

    shared = await repository.share_to_library(session, gen_id=42, user_id=7)

    assert shared is None
    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "source_feed_gen_id IS NULL" in compiled
    assert "source_feed_gen_id IN" in compiled
    assert "user_id = 7" in compiled
    get_generation_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_user_feed_remix_reward_rub_limits_by_available_balance() -> None:
    session = AsyncMock()

    earned_result = MagicMock()
    earned_result.scalar_one.return_value = 125.5
    balance_result = MagicMock()
    balance_result.scalar_one.return_value = 90.0
    pending_result = MagicMock()
    pending_result.scalar_one.return_value = 4.5
    session.execute = AsyncMock(side_effect=[earned_result, balance_result, pending_result])

    amount = await repository.get_user_feed_remix_reward_rub(session, user_id=7)

    assert amount == 85.5


@pytest.mark.asyncio
async def test_get_user_feed_remix_reward_rub_never_exceeds_earned_total() -> None:
    session = AsyncMock()

    earned_result = MagicMock()
    earned_result.scalar_one.return_value = 10.0
    balance_result = MagicMock()
    balance_result.scalar_one.return_value = 25.0
    pending_result = MagicMock()
    pending_result.scalar_one.return_value = 0.0
    session.execute = AsyncMock(side_effect=[earned_result, balance_result, pending_result])

    amount = await repository.get_user_feed_remix_reward_rub(session, user_id=7)

    assert amount == 10.0


@pytest.mark.asyncio
async def test_get_user_feed_remix_reward_rub_never_goes_below_zero() -> None:
    session = AsyncMock()

    earned_result = MagicMock()
    earned_result.scalar_one.return_value = 10.0
    balance_result = MagicMock()
    balance_result.scalar_one.return_value = 5.0
    pending_result = MagicMock()
    pending_result.scalar_one.return_value = 25.0
    session.execute = AsyncMock(side_effect=[earned_result, balance_result, pending_result])

    amount = await repository.get_user_feed_remix_reward_rub(session, user_id=7)

    assert amount == 0.0


@pytest.mark.asyncio
async def test_get_feed_generations_includes_video_posts(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(repository, "_feed_cards_from_stmt", AsyncMock(return_value=[]))

    await repository.get_feed_generations(session, limit=10)

    statement = repository._feed_cards_from_stmt.await_args.args[1]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "generations.gen_type IN ('image', 'video')" in compiled


@pytest.mark.asyncio
async def test_get_top_day_generations_includes_video_posts(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(repository, "_feed_cards_from_stmt", AsyncMock(return_value=[]))

    await repository.get_top_day_generations(session, limit=10)

    statement = repository._feed_cards_from_stmt.await_args.args[1]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "generations.gen_type IN ('image', 'video')" in compiled

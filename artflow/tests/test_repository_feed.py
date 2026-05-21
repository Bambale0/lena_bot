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
    get_generation_by_id.assert_not_awaited()

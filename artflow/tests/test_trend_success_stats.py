"""Trend demand counts reflect completed provider jobs, not button clicks."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from api import trends_routes
from bot.handlers import trends as trend_bot
from core.trends import TREND_TAG
from db import repository
from db.models import PromptStatus
from db.trend_metrics import trend_success_stats


def prompt(id_: int, uses: int = 9):
    return SimpleNamespace(
        id=id_, title=f"Trend {id_}", description="Simple",
        preview_url="https://example.test/trend.jpg", model="nano-banana-pro",
        prompt_text="SECRET CANONICAL PROMPT", tags=[TREND_TAG],
        created_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        uses_count=uses, likes=0, author_id=22,
        status=PromptStatus.approved, is_public=True,
        trend_user_fields=[],
    )


@pytest.mark.asyncio
async def test_trend_stats_one_query_count_only_done_and_split_last_7d():
    session = AsyncMock()
    row = SimpleNamespace(
        trend_id=50, total_runs=7, successful_runs=3,
        successful_runs_7d=2, failed_runs=2, active_runs=2, unique_users=2,
    )
    result = MagicMock()
    result.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)
    stats = await trend_success_stats(session, [50, 51])
    assert stats[50]["successful_runs"] == 3
    assert stats[50]["successful_runs_7d"] == 2
    assert stats[50]["unique_users"] == 2
    assert stats[50]["active_runs"] == 2
    assert stats[50]["failed_runs"] == 2
    assert 51 not in stats
    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))
    assert "trend_id" in sql and "prompt_id" in sql
    assert "coalesce(" in sql.lower()
    assert "'done'" in sql
    assert "'failed'" in sql
    assert "distinct" in sql.lower()
    assert "finished_at" in sql
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_empty_trend_metrics_skips_database():
    session = AsyncMock()
    assert await trend_success_stats(session, []) == {}
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_trends_include_completed_runs_even_when_old_uses_zero(monkeypatch):
    prompts = [prompt(50, uses=0), prompt(51, uses=17)]
    monkeypatch.setattr(
        trends_routes, "get_prompts_by_tag", AsyncMock(return_value=prompts),
    )
    measure = AsyncMock(return_value={
        50: {"successful_runs": 3, "successful_runs_7d": 2},
    })
    monkeypatch.setattr(trends_routes, "trend_success_stats", measure)
    cards = await trends_routes.list_trends(
        kind=None, limit=80, session=AsyncMock(), user=SimpleNamespace(),
    )
    assert cards[0]["successful_runs"] == 3
    assert cards[0]["successful_runs_7d"] == 2
    assert cards[1]["successful_runs"] == 0
    assert cards[1]["successful_runs_7d"] == 0
    assert cards[0]["uses_count"] == 0
    assert "prompt_template" not in cards[0]
    measure.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_trends_show_failed_pending_and_distinct_users(monkeypatch):
    prompts = [prompt(50)]
    monkeypatch.setattr(trends_routes, "_require_admin", lambda user: None)
    db = AsyncMock()
    response = MagicMock()
    response.scalars.return_value.all.return_value = prompts
    db.execute.return_value = response
    monkeypatch.setattr(
        trends_routes, "trend_success_stats",
        AsyncMock(return_value={
            50: {
                "total_runs": 6, "successful_runs": 3,
                "successful_runs_7d": 2, "failed_runs": 1,
                "active_runs": 2, "unique_users": 3,
            },
        }),
    )
    result = await trends_routes.admin_list_trends(
        session=db, user=SimpleNamespace(tg_id=11),
    )
    assert result[0]["successful_runs"] == 3
    assert result[0]["successful_runs_7d"] == 2
    assert result[0]["failed_runs"] == 1
    assert result[0]["active_runs"] == 2
    assert result[0]["unique_users"] == 3


def test_feed_remix_subquery_counts_source_feed_link_when_parent_absent():
    subquery = repository._feed_remix_counts_subquery()
    statement = str(subquery.select().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert "coalesce(generations.source_feed_gen_id, generations.parent_generation_id)" in statement.lower()
    assert "generations.status = 'done'" in statement.lower()


def test_bot_trend_caption_labels_completed_not_old_uses():
    value = trend_bot._caption(prompt(50, uses=999), index=0, total=1, successful_runs=3)
    assert "Успешных повторов" in value
    assert ">3<" in value
    assert ">999<" not in value


def test_all_three_user_surfaces_show_success_counter_even_at_zero():
    base = Path("webapp/src")
    for path in ("features/trends-screen.tsx", "features/feed-screen.tsx", "main.jsx"):
        source = (base/path).read_text(encoding="utf-8")
        assert "successful_runs" in source, path
        assert "successful_runs_7d" in source, path
        assert "Успешно" in source, path

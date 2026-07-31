from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from db.feed_relevance import feed_relevance_score


def _generation(*, age_hours: float, likes: int = 0, shares: int = 0):
    now = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        created_at=now - timedelta(hours=age_hours),
        likes_count=likes,
        shares_count=shares,
    ), now


def test_new_work_receives_a_freshness_opportunity():
    recent, now = _generation(age_hours=1)
    old, _ = _generation(age_hours=72)

    assert feed_relevance_score(recent, 0, now=now) > feed_relevance_score(old, 0, now=now)


def test_popularity_improves_rank_at_equal_age():
    plain, now = _generation(age_hours=12)
    popular, _ = _generation(age_hours=12, likes=20, shares=4)

    assert feed_relevance_score(popular, 0, now=now) > feed_relevance_score(plain, 0, now=now)


def test_repeats_are_a_strong_relevance_signal():
    item, now = _generation(age_hours=12)

    assert feed_relevance_score(item, 8, now=now) > feed_relevance_score(item, 0, now=now)


def test_old_engagement_decays_instead_of_staying_first_forever():
    fresh, now = _generation(age_hours=2, likes=7, shares=1)
    old_viral, _ = _generation(age_hours=24 * 45, likes=100, shares=20)

    assert feed_relevance_score(fresh, 2, now=now) > feed_relevance_score(old_viral, 5, now=now)


def test_front_v2_opens_feed_first_and_keeps_core_navigation():
    main = Path("webapp/src/main.jsx").read_text(encoding="utf-8")
    app = Path("webapp/src/v2/VelvetApp.jsx").read_text(encoding="utf-8")

    assert 'useState("feed")' in app
    assert '["feed", "home", "Лента"]' in app
    assert '["create", "sparkle", "Создать"]' in app
    assert '["prompts", "prompt", "Промпты"]' in app
    assert '["profile", "user", "Профиль"]' in app
    assert 'source=recent&limit=60' in app
    assert "20260801-velvet-neon-front-v2" in main

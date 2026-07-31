"""Relevance ranking for public feed generations."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from types import ModuleType
from typing import Any


def feed_relevance_score(
    generation: Any,
    remix_count: int,
    *,
    now: datetime | None = None,
) -> float:
    """Combine freshness, popularity and repeat intent into one stable score.

    Engagement uses logarithmic growth, so a single viral publication does not
    occupy the first position forever. Its contribution gradually decays with
    age, while every new publication receives a temporary freshness window.
    """
    ranking_now = now or datetime.now(timezone.utc)
    created_at = getattr(generation, "created_at", None) or ranking_now
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_hours = max(0.0, (ranking_now - created_at).total_seconds() / 3600)
    likes = max(0, int(getattr(generation, "likes_count", 0) or 0))
    shares = max(0, int(getattr(generation, "shares_count", 0) or 0))
    repeats = max(0, int(remix_count or 0))

    freshness = 12.0 / ((age_hours + 2.0) ** 0.72)
    popularity = math.log1p(likes) * 2.2 + math.log1p(shares) * 3.0
    repeat_intent = math.log1p(repeats) * 5.0
    engagement_decay = 1.0 / (((age_hours / 24.0) + 1.0) ** 0.55)

    return float(freshness + (popularity + repeat_intent) * engagement_decay)


def install_feed_relevance(repository: ModuleType) -> None:
    """Install the relevance scorer without duplicating repository queries."""
    repository._feed_score = feed_relevance_score

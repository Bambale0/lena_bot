from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base, Generation

FeedEngagementAction = Literal["like", "share"]
_VALID_ACTIONS: frozenset[str] = frozenset({"like", "share"})


class FeedEngagement(Base):
    __tablename__ = "feed_engagements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "generation_id",
            "action",
            name="uq_feed_engagement_user_generation_action",
        ),
        CheckConstraint("action IN ('like', 'share')", name="ck_feed_engagement_action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("generations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


@dataclass(frozen=True)
class FeedEngagementResult:
    generation: Generation | None
    created: bool


async def record_feed_engagement(
    session: AsyncSession,
    *,
    generation_id: int,
    user_id: int,
    action: FeedEngagementAction,
) -> FeedEngagementResult:
    """Record one user/action pair and update the aggregate counter exactly once.

    The database unique constraint is the source of truth. Concurrent requests
    from the same user can race safely: only the first insert wins and only that
    request increments the denormalized feed counter.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Unsupported feed engagement action: {action}")

    current = await session.execute(
        select(Generation).where(
            Generation.id == int(generation_id),
            Generation.is_public_feed.is_(True),
        )
    )
    generation = current.scalar_one_or_none()
    if generation is None:
        return FeedEngagementResult(generation=None, created=False)

    inserted = await session.execute(
        insert(FeedEngagement)
        .values(
            user_id=int(user_id),
            generation_id=int(generation_id),
            action=action,
        )
        .on_conflict_do_nothing(constraint="uq_feed_engagement_user_generation_action")
        .returning(FeedEngagement.id)
    )
    created = inserted.scalar_one_or_none() is not None

    if created:
        counter = Generation.likes_count if action == "like" else Generation.shares_count
        await session.execute(
            update(Generation)
            .where(
                Generation.id == int(generation_id),
                Generation.is_public_feed.is_(True),
            )
            .values({counter.key: counter + 1})
        )

    await session.commit()
    if created:
        await session.refresh(generation)
    return FeedEngagementResult(generation=generation, created=created)

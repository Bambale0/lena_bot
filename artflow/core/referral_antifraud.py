from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.admin_alerts import send_admin_alert_once
from core.config import settings
from db.models import Generation, Transaction, TransactionStatus, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferralAntifraudSnapshot:
    total_refs: int
    refs_with_generations: int
    refs_with_paid_transactions: int
    window_started_at: datetime

    @property
    def engaged_refs(self) -> int:
        return max(self.refs_with_generations, self.refs_with_paid_transactions)

    @property
    def inactive_ratio(self) -> float:
        if self.total_refs <= 0:
            return 0.0
        inactive = max(0, self.total_refs - self.engaged_refs)
        return inactive / self.total_refs


def should_flag_referral_burst(snapshot: ReferralAntifraudSnapshot) -> bool:
    if not settings.REFERRAL_ANTIFRAUD_ENABLED:
        return False
    if snapshot.total_refs < int(settings.REFERRAL_ANTIFRAUD_MIN_L1_REFS or 0):
        return False
    if snapshot.refs_with_paid_transactions > 0:
        return False
    return snapshot.inactive_ratio >= float(settings.REFERRAL_ANTIFRAUD_MIN_INACTIVE_RATIO or 1.0)


async def _referral_antifraud_snapshot(
    session: AsyncSession,
    *,
    referrer_id: int,
) -> ReferralAntifraudSnapshot:
    window_minutes = max(1, int(settings.REFERRAL_ANTIFRAUD_WINDOW_MINUTES or 60))
    window_started_at = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    recent_refs = (
        select(User.id.label("user_id"))
        .where(
            User.referrer_id == referrer_id,
            User.created_at >= window_started_at,
        )
        .subquery()
    )
    generation_users = (
        select(Generation.user_id.label("user_id"))
        .group_by(Generation.user_id)
        .subquery()
    )
    paid_users = (
        select(Transaction.user_id.label("user_id"))
        .where(
            Transaction.status == TransactionStatus.paid,
            Transaction.amount_rub > 0,
            Transaction.credits > 0,
        )
        .group_by(Transaction.user_id)
        .subquery()
    )

    row = (
        await session.execute(
            select(
                func.count(recent_refs.c.user_id),
                func.count(func.distinct(generation_users.c.user_id)),
                func.count(func.distinct(paid_users.c.user_id)),
            )
            .select_from(recent_refs)
            .outerjoin(generation_users, generation_users.c.user_id == recent_refs.c.user_id)
            .outerjoin(paid_users, paid_users.c.user_id == recent_refs.c.user_id)
        )
    ).one()

    return ReferralAntifraudSnapshot(
        total_refs=int(row[0] or 0),
        refs_with_generations=int(row[1] or 0),
        refs_with_paid_transactions=int(row[2] or 0),
        window_started_at=window_started_at,
    )


async def ensure_referrer_allowed(
    session: AsyncSession,
    *,
    referrer: User | None,
    candidate_label: str,
) -> bool:
    if not settings.REFERRAL_ANTIFRAUD_ENABLED or referrer is None:
        return True
    if int(getattr(referrer, "tg_id", 0) or 0) in set(settings.ADMIN_IDS or []):
        return True
    if bool(getattr(referrer, "is_banned", False)):
        return False

    snapshot = await _referral_antifraud_snapshot(session, referrer_id=int(referrer.id))
    if not should_flag_referral_burst(snapshot):
        return True

    await session.execute(
        update(User)
        .where(User.id == int(referrer.id), User.is_banned.is_(False))
        .values(is_banned=True)
    )
    await session.commit()

    await send_admin_alert_once(
        alert_key=f"referral-antifraud:{getattr(referrer, 'id', 0)}",
        title="Referral antifraud triggered",
        message=(
            f"Referrer tg_id={getattr(referrer, 'tg_id', 0)} user_id={getattr(referrer, 'id', 0)} "
            f"auto-banned after {snapshot.total_refs} L1 referrals in "
            f"{settings.REFERRAL_ANTIFRAUD_WINDOW_MINUTES} min. "
            f"Refs with generations: {snapshot.refs_with_generations}. "
            f"Refs with paid transactions: {snapshot.refs_with_paid_transactions}. "
            f"Inactive ratio: {snapshot.inactive_ratio:.2%}. "
            f"Blocked candidate: {candidate_label}."
        ),
        cooldown_seconds=6 * 3600,
    )
    logger.warning(
        "Referral antifraud banned referrer_id=%s tg_id=%s total_refs=%s generations=%s paid=%s candidate=%s",
        getattr(referrer, "id", None),
        getattr(referrer, "tg_id", None),
        snapshot.total_refs,
        snapshot.refs_with_generations,
        snapshot.refs_with_paid_transactions,
        candidate_label,
    )
    return False

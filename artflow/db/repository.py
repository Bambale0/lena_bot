# db/repository.py
from __future__ import annotations

import json
import secrets
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Date, cast, select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.model_pricing import image_pricing_keys, video_pricing_keys
from db.models import (
    Generation,
    ImageGenerationAction,
    ImageSession,
    ImageSessionStatus,
    GenerationStatus,
    GenerationType,
    ModelCost,
    PaymentProvider,
    PricePlan,
    ReferralWithdrawalRequest,
    Transaction,
    TransactionStatus,
    User,
    WithdrawalStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedGenerationCard:
    generation: Generation
    username: str | None
    full_name: str | None
    aspect_ratio: str | None
    quality: str | None
    count: int | None
    reference_url: str | None
    remix_count: int
    score: float


@dataclass(frozen=True)
class ReferralLeader:
    user: User
    l1_count: int
    l2_count: int
    l3_count: int

    @property
    def total_count(self) -> float:
        return self.l1_count + self.l2_count + self.l3_count


@dataclass(frozen=True)
class ReferralChildStats:
    user: User
    generations_count: int
    paid_rub: float


@dataclass(frozen=True)
class WithdrawalRequestView:
    request: ReferralWithdrawalRequest
    user: User


# ─── User ────────────────────────────────────────────────────────────────────

async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    result = await session.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None,
    full_name: str | None,
    welcome_credits: float,
    referrer: User | None = None,
    referrer_l2: User | None = None,
    referrer_l3: User | None = None,
    language: str = "ru",
) -> User:
    user = User(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        credits=welcome_credits,
        referral_code=secrets.token_urlsafe(8),
        referrer_id=referrer.id if referrer else None,
        referrer_l2_id=referrer_l2.id if referrer_l2 else None,
        referrer_l3_id=referrer_l3.id if referrer_l3 else None,
        language=language,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("User created: tg_id=%s", tg_id)
    return user


async def set_user_language(session: AsyncSession, user_id: int, language: str) -> None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(language=language)
    )
    await session.commit()


async def add_credits(session: AsyncSession, user_id: int, amount: float) -> float:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(credits=User.credits + amount)
        .returning(User.credits)
    )
    await session.commit()
    return result.scalar_one()


async def add_referral_balance(session: AsyncSession, user_id: int, amount_rub: float) -> float:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(referral_balance=User.referral_balance + amount_rub)
        .returning(User.referral_balance)
    )
    await session.commit()
    return result.scalar_one()


async def spend_credits(session: AsyncSession, user_id: int, amount: float) -> bool:
    """Atomically deduct credits. Returns False if not enough credits."""
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.credits >= amount)
        .values(credits=User.credits - amount)
        .returning(User.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def count_users(session: AsyncSession) -> float:
    from sqlalchemy import func
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.tg_id).where(User.is_banned == False))
    return list(result.scalars().all())


async def get_referral_leaders(session: AsyncSession, limit: int = 20) -> list[ReferralLeader]:
    l1 = (
        select(User.referrer_id.label("user_id"), func.count(User.id).label("count"))
        .where(User.referrer_id.is_not(None))
        .group_by(User.referrer_id)
        .subquery()
    )
    l2 = (
        select(User.referrer_l2_id.label("user_id"), func.count(User.id).label("count"))
        .where(User.referrer_l2_id.is_not(None))
        .group_by(User.referrer_l2_id)
        .subquery()
    )
    l3 = (
        select(User.referrer_l3_id.label("user_id"), func.count(User.id).label("count"))
        .where(User.referrer_l3_id.is_not(None))
        .group_by(User.referrer_l3_id)
        .subquery()
    )
    total = func.coalesce(l1.c.count, 0) + func.coalesce(l2.c.count, 0) + func.coalesce(l3.c.count, 0)
    result = await session.execute(
        select(
            User,
            func.coalesce(l1.c.count, 0),
            func.coalesce(l2.c.count, 0),
            func.coalesce(l3.c.count, 0),
        )
        .outerjoin(l1, l1.c.user_id == User.id)
        .outerjoin(l2, l2.c.user_id == User.id)
        .outerjoin(l3, l3.c.user_id == User.id)
        .where(total > 0)
        .order_by(desc(total), desc(User.created_at))
        .limit(limit)
    )
    return [
        ReferralLeader(user=user, l1_count=int(l1_count or 0), l2_count=int(l2_count or 0), l3_count=int(l3_count or 0))
        for user, l1_count, l2_count, l3_count in result.all()
    ]


async def count_user_referrals(session: AsyncSession, user_id: int) -> tuple[int, int, int]:
    result = await session.execute(
        select(
            select(func.count()).select_from(User).where(User.referrer_id == user_id).scalar_subquery(),
            select(func.count()).select_from(User).where(User.referrer_l2_id == user_id).scalar_subquery(),
            select(func.count()).select_from(User).where(User.referrer_l3_id == user_id).scalar_subquery(),
        )
    )
    l1, l2, l3 = result.one()
    return int(l1 or 0), int(l2 or 0), int(l3 or 0)


async def get_referral_children(
    session: AsyncSession,
    user_id: int,
    *,
    level: int = 1,
    limit: int = 20,
) -> list[ReferralChildStats]:
    ref_column = {
        1: User.referrer_id,
        2: User.referrer_l2_id,
        3: User.referrer_l3_id,
    }.get(level, User.referrer_id)
    gens = (
        select(Generation.user_id.label("user_id"), func.count(Generation.id).label("count"))
        .group_by(Generation.user_id)
        .subquery()
    )
    revenue = (
        select(Transaction.user_id.label("user_id"), func.coalesce(func.sum(Transaction.amount_rub), 0).label("rub"))
        .where(Transaction.status == TransactionStatus.paid)
        .group_by(Transaction.user_id)
        .subquery()
    )
    result = await session.execute(
        select(
            User,
            func.coalesce(gens.c.count, 0),
            func.coalesce(revenue.c.rub, 0),
        )
        .outerjoin(gens, gens.c.user_id == User.id)
        .outerjoin(revenue, revenue.c.user_id == User.id)
        .where(ref_column == user_id)
        .order_by(desc(User.created_at))
        .limit(limit)
    )
    return [
        ReferralChildStats(user=user, generations_count=int(gens_count or 0), paid_rub=float(paid_rub or 0))
        for user, gens_count, paid_rub in result.all()
    ]


async def ban_user(session: AsyncSession, tg_id: int) -> bool:
    result = await session.execute(
        update(User).where(User.tg_id == tg_id).values(is_banned=True).returning(User.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def unban_user(session: AsyncSession, tg_id: int) -> bool:
    result = await session.execute(
        update(User).where(User.tg_id == tg_id).values(is_banned=False).returning(User.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


# ─── Generations ─────────────────────────────────────────────────────────────

async def create_generation(
    session: AsyncSession,
    user_id: int,
    model: str,
    gen_type: GenerationType,
    prompt: str,
    credits_spent: int,
    image_session_id: int | None = None,
    parent_generation_id: int | None = None,
    action_type: ImageGenerationAction | None = None,
    source_feed_gen_id: int | None = None,
) -> Generation:
    gen = Generation(
        user_id=user_id,
        model=model,
        gen_type=gen_type,
        prompt=prompt,
        credits_spent=credits_spent,
        image_session_id=image_session_id,
        parent_generation_id=parent_generation_id,
        action_type=action_type,
        source_feed_gen_id=source_feed_gen_id,
        status=GenerationStatus.pending,
    )
    session.add(gen)
    await session.commit()
    await session.refresh(gen)
    return gen


async def update_generation_task(
    session: AsyncSession, gen_id: int, task_id: str
) -> None:
    await session.execute(
        update(Generation)
        .where(Generation.id == gen_id)
        .values(task_id=task_id, status=GenerationStatus.processing)
    )
    await session.commit()


async def finish_generation(
    session: AsyncSession,
    gen_id: int,
    result_url: str,
) -> None:
    await session.execute(
        update(Generation)
        .where(Generation.id == gen_id)
        .values(
            status=GenerationStatus.done,
            result_url=result_url,
            finished_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    # Pay 5% royalty to the author of the source feed post (if remixed from feed)
    gen = await get_generation_by_id(session, gen_id)
    if gen and gen.source_feed_gen_id:
        source = await get_generation_by_id(session, gen.source_feed_gen_id)
        if source and source.user_id != gen.user_id and gen.credits_spent > 0:
            royalty = max(1, round(gen.credits_spent * 0.05))
            await add_credits(session, source.user_id, royalty)


async def fail_generation(
    session: AsyncSession, gen_id: int, error: str
) -> None:
    await session.execute(
        update(Generation)
        .where(Generation.id == gen_id)
        .values(
            status=GenerationStatus.failed,
            error_msg=error,
            finished_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

async def get_generation_by_id(session: AsyncSession, gen_id: int) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.id == gen_id))
    return result.scalar_one_or_none()


async def get_generation_by_task_id(session: AsyncSession, task_id: str) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.task_id == task_id))
    return result.scalar_one_or_none()


def _feed_score(gen: Generation, remix_count: int) -> float:
    generation_count = 1 + remix_count
    score = (
        gen.likes_count * 1
        + remix_count * 3
        + gen.shares_count * 5
        + generation_count * 4
    )
    created_at = gen.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if created_at and (datetime.now(timezone.utc) - created_at).total_seconds() <= 2 * 60 * 60:
        score *= 1.5
    return float(score)


async def _feed_cards_from_stmt(session: AsyncSession, stmt) -> list[FeedGenerationCard]:
    remix_counts = (
        select(
            Generation.parent_generation_id.label("parent_id"),
            func.count(Generation.id).label("remix_count"),
        )
        .where(
            Generation.parent_generation_id.is_not(None),
            Generation.status == GenerationStatus.done,
        )
        .group_by(Generation.parent_generation_id)
        .subquery()
    )

    result = await session.execute(
        stmt.outerjoin(User, Generation.user_id == User.id)
        .outerjoin(ImageSession, Generation.image_session_id == ImageSession.id)
        .outerjoin(remix_counts, remix_counts.c.parent_id == Generation.id)
        .add_columns(
            User.username,
            User.full_name,
            ImageSession.aspect_ratio,
            ImageSession.quality,
            ImageSession.count,
            ImageSession.reference_url,
            func.coalesce(remix_counts.c.remix_count, 0).label("remix_count"),
        )
    )
    cards: list[FeedGenerationCard] = []
    for gen, username, full_name, aspect_ratio, quality, count, reference_url, remix_count in result.all():
        remix_total = int(remix_count or 0)
        cards.append(
            FeedGenerationCard(
                generation=gen,
                username=username,
                full_name=full_name,
                aspect_ratio=aspect_ratio,
                quality=quality,
                count=count,
                reference_url=reference_url,
                remix_count=remix_total,
                score=_feed_score(gen, remix_total),
            )
        )
    cards.sort(
        key=lambda card: (
            card.score,
            card.generation.created_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return cards


async def get_feed_generations(
    session: AsyncSession,
    *,
    limit: int = 30,
) -> list[FeedGenerationCard]:
    stmt = (
        select(Generation)
        .where(
            Generation.gen_type == GenerationType.image,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            Generation.is_public_feed.is_(True),
        )
        .order_by(desc(Generation.created_at))
        .limit(max(limit, 1) * 3)
    )
    cards = await _feed_cards_from_stmt(session, stmt)
    return cards[:limit]


async def get_top_day_generations(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[FeedGenerationCard]:
    today = datetime.now(timezone.utc).date()
    stmt = (
        select(Generation)
        .where(
            Generation.gen_type == GenerationType.image,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            Generation.is_public_feed.is_(True),
            cast(Generation.created_at, Date) == today,
        )
        .order_by(desc(Generation.created_at))
        .limit(max(limit, 1) * 5)
    )
    cards = await _feed_cards_from_stmt(session, stmt)
    return cards[:limit]


async def get_feed_generation_card(
    session: AsyncSession,
    gen_id: int,
) -> FeedGenerationCard | None:
    stmt = (
        select(Generation)
        .where(
            Generation.id == gen_id,
            Generation.gen_type == GenerationType.image,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            Generation.is_public_feed.is_(True),
        )
        .limit(1)
    )
    cards = await _feed_cards_from_stmt(session, stmt)
    return cards[0] if cards else None


async def share_to_feed(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
        )
        .values(is_public_feed=True)
    )
    await session.commit()
    return await get_generation_by_id(session, gen_id)


async def share_to_library(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
        )
        .values(is_prompt_library=True)
    )
    await session.commit()
    return await get_generation_by_id(session, gen_id)


async def get_public_feed_generation(session: AsyncSession, gen_id: int) -> Generation | None:
    """Return a generation only if it is publicly shared to the feed."""
    result = await session.execute(
        select(Generation).where(
            Generation.id == gen_id,
            Generation.is_public_feed.is_(True),
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
        )
    )
    return result.scalar_one_or_none()


async def like_feed_generation(session: AsyncSession, gen_id: int) -> Generation | None:
    await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
        )
        .values(likes_count=Generation.likes_count + 1)
    )
    await session.commit()
    return await get_generation_by_id(session, gen_id)


async def increment_feed_share(session: AsyncSession, gen_id: int) -> Generation | None:
    await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
        )
        .values(shares_count=Generation.shares_count + 1)
    )
    await session.commit()
    return await get_generation_by_id(session, gen_id)


# ─── Image Sessions ──────────────────────────────────────────────────────────

async def archive_active_image_sessions(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(ImageSession)
        .where(
            ImageSession.user_id == user_id,
            ImageSession.status == ImageSessionStatus.active,
        )
        .values(status=ImageSessionStatus.archived, updated_at=func.now())
    )
    await session.commit()


async def create_image_session(
    session: AsyncSession,
    user_id: int,
    model: str,
    mode: str,
    aspect_ratio: str | None,
    quality: str,
    count: int,
    base_prompt: str | None,
    reference_file_id: str | None = None,
    reference_file_ids: list[str] | None = None,
    reference_url: str | None = None,
) -> ImageSession:
    await archive_active_image_sessions(session, user_id)

    normalized_reference_file_ids = [item for item in (reference_file_ids or []) if item]
    if reference_file_id and reference_file_id not in normalized_reference_file_ids:
        normalized_reference_file_ids.insert(0, reference_file_id)

    image_session = ImageSession(
        user_id=user_id,
        model=model,
        mode=mode,
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=base_prompt,
        last_prompt=base_prompt,
        reference_file_id=reference_file_id,
        reference_file_ids=json.dumps(normalized_reference_file_ids, ensure_ascii=True) if normalized_reference_file_ids else None,
        reference_url=reference_url,
        status=ImageSessionStatus.active,
    )
    session.add(image_session)
    await session.commit()
    await session.refresh(image_session)
    return image_session


async def get_image_session(
    session: AsyncSession,
    image_session_id: int,
    user_id: int | None = None,
) -> ImageSession | None:
    stmt = select(ImageSession).where(ImageSession.id == image_session_id)
    if user_id is not None:
        stmt = stmt.where(ImageSession.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_image_session(session: AsyncSession, user_id: int) -> ImageSession | None:
    result = await session.execute(
        select(ImageSession)
        .where(
            ImageSession.user_id == user_id,
            ImageSession.status == ImageSessionStatus.active,
        )
        .order_by(desc(ImageSession.updated_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_image_session_reference(
    session: AsyncSession,
    image_session_id: int,
    reference_file_id: str | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(reference_file_id=reference_file_id, updated_at=func.now())
    )
    await session.commit()


async def update_image_session_references(
    session: AsyncSession,
    image_session_id: int,
    reference_file_ids: list[str],
) -> None:
    normalized_reference_file_ids = [item for item in reference_file_ids if item]
    lead_reference_file_id = normalized_reference_file_ids[0] if normalized_reference_file_ids else None
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(
            reference_file_id=lead_reference_file_id,
            reference_file_ids=json.dumps(normalized_reference_file_ids, ensure_ascii=True) if normalized_reference_file_ids else None,
            updated_at=func.now(),
        )
    )
    await session.commit()


async def update_image_session_base_prompt(
    session: AsyncSession,
    image_session_id: int,
    base_prompt: str | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(base_prompt=base_prompt, updated_at=func.now())
    )
    await session.commit()


async def update_image_session_last_prompt(
    session: AsyncSession,
    image_session_id: int,
    last_prompt: str | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(last_prompt=last_prompt, updated_at=func.now())
    )
    await session.commit()


async def update_image_session_last_result(
    session: AsyncSession,
    image_session_id: int,
    result_url: str | None,
    generation_id: int | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(
            last_result_url=result_url,
            last_generation_id=generation_id,
            updated_at=func.now(),
        )
    )
    await session.commit()


async def get_last_session_generation(
    session: AsyncSession,
    image_session_id: int,
) -> Generation | None:
    result = await session.execute(
        select(Generation)
        .where(Generation.image_session_id == image_session_id)
        .order_by(desc(Generation.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_user_history(
    session: AsyncSession, user_id: int, limit: int = 20
) -> list[Generation]:
    result = await session.execute(
        select(Generation)
        .where(Generation.user_id == user_id)
        .order_by(desc(Generation.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_user_active_generations(session: AsyncSession, user_id: int) -> float:
    result = await session.execute(
        select(func.count())
        .select_from(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]),
        )
    )
    return result.scalar_one()


async def count_generations_today(session: AsyncSession) -> float:
    from sqlalchemy import func, cast, Date
    today = datetime.now(timezone.utc).date()
    result = await session.execute(
        select(func.count())
        .select_from(Generation)
        .where(cast(Generation.created_at, Date) == today)
    )
    return result.scalar_one()


# ─── Transactions ─────────────────────────────────────────────────────────────

async def create_transaction(
    session: AsyncSession,
    user_id: int,
    amount_rub: float,
    credits: float,
    provider: PaymentProvider,
    external_id: str | None = None,
) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        amount_rub=amount_rub,
        credits=credits,
        provider=provider,
        external_id=external_id,
        status=TransactionStatus.pending,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


async def confirm_transaction(
    session: AsyncSession, external_id: str
) -> Transaction | None:
    # Atomically confirm a payment only once. Repeated provider webhooks
    # should not be able to re-mark an already processed transaction as paid.
    result = await session.execute(
        update(Transaction)
        .where(
            Transaction.external_id == external_id,
            Transaction.status == TransactionStatus.pending,
        )
        .values(status=TransactionStatus.paid)
        .returning(Transaction)
    )
    tx = result.scalar_one_or_none()
    await session.commit()
    return tx


async def get_last_tbank_transaction(
    session: AsyncSession,
    user_id: int,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.provider == PaymentProvider.tbank,
        )
        .order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_last_cancellable_tbank_transaction(
    session: AsyncSession,
    user_id: int,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.provider == PaymentProvider.tbank,
            Transaction.status.in_((TransactionStatus.pending, TransactionStatus.paid)),
        )
        .order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def set_transaction_status(
    session: AsyncSession,
    external_id: str,
    status: TransactionStatus,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction).where(Transaction.external_id == external_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        return None
    await session.execute(
        update(Transaction)
        .where(Transaction.id == tx.id)
        .values(status=status)
    )
    await session.commit()
    return tx


# ─── Referral Withdrawals ────────────────────────────────────────────────────

async def create_withdrawal_request(
    session: AsyncSession,
    *,
    user_id: int,
    amount_rub: float,
    payout_details: str,
) -> ReferralWithdrawalRequest:
    request = ReferralWithdrawalRequest(
        user_id=user_id,
        amount_rub=amount_rub,
        payout_details=payout_details,
        status=WithdrawalStatus.pending,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def get_withdrawal_request(
    session: AsyncSession,
    request_id: int,
) -> WithdrawalRequestView | None:
    result = await session.execute(
        select(ReferralWithdrawalRequest, User)
        .join(User, ReferralWithdrawalRequest.user_id == User.id)
        .where(ReferralWithdrawalRequest.id == request_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    request, user = row
    return WithdrawalRequestView(request=request, user=user)


async def get_pending_withdrawal_requests(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> list[WithdrawalRequestView]:
    result = await session.execute(
        select(ReferralWithdrawalRequest, User)
        .join(User, ReferralWithdrawalRequest.user_id == User.id)
        .where(ReferralWithdrawalRequest.status == WithdrawalStatus.pending)
        .order_by(desc(ReferralWithdrawalRequest.created_at))
        .limit(limit)
    )
    return [WithdrawalRequestView(request=request, user=user) for request, user in result.all()]


async def get_user_withdrawal_requests(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 5,
) -> list[ReferralWithdrawalRequest]:
    result = await session.execute(
        select(ReferralWithdrawalRequest)
        .where(ReferralWithdrawalRequest.user_id == user_id)
        .order_by(desc(ReferralWithdrawalRequest.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def set_withdrawal_status(
    session: AsyncSession,
    request_id: int,
    *,
    status: WithdrawalStatus,
    admin_tg_id: int,
    admin_note: str | None = None,
) -> WithdrawalRequestView | None:
    result = await session.execute(
        update(ReferralWithdrawalRequest)
        .where(
            ReferralWithdrawalRequest.id == request_id,
            ReferralWithdrawalRequest.status == WithdrawalStatus.pending,
        )
        .values(
            status=status,
            admin_tg_id=admin_tg_id,
            admin_note=admin_note,
            reviewed_at=datetime.now(timezone.utc),
        )
        .returning(ReferralWithdrawalRequest.id)
    )
    changed_id = result.scalar_one_or_none()
    await session.commit()
    if changed_id is None:
        return None
    return await get_withdrawal_request(session, request_id)


async def get_revenue_today(session: AsyncSession) -> float:
    from sqlalchemy import func, cast, Date
    today = datetime.now(timezone.utc).date()
    result = await session.execute(
        select(func.coalesce(func.sum(Transaction.amount_rub), 0))
        .where(
            Transaction.status == TransactionStatus.paid,
            cast(Transaction.created_at, Date) == today,
        )
    )
    return float(result.scalar_one())


# ─── Price Plans ─────────────────────────────────────────────────────────────

async def get_active_price_plans(session: AsyncSession) -> list[PricePlan]:
    result = await session.execute(
        select(PricePlan)
        .where(PricePlan.is_active == True)
        .order_by(PricePlan.sort_order)
    )
    return list(result.scalars().all())


async def get_price_plan_by_key(session: AsyncSession, key: str) -> PricePlan | None:
    result = await session.execute(select(PricePlan).where(PricePlan.key == key))
    return result.scalar_one_or_none()


async def upsert_price_plan(
    session: AsyncSession,
    key: str,
    label: str,
    credits: float,
    price_rub: float,
    sort_order: int = 0,
) -> PricePlan:
    plan = await get_price_plan_by_key(session, key)
    if plan:
        plan.label = label
        plan.credits = credits
        plan.price_rub = price_rub
        plan.sort_order = sort_order
    else:
        plan = PricePlan(key=key, label=label, credits=credits, price_rub=price_rub, sort_order=sort_order)
        session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


async def toggle_price_plan(session: AsyncSession, key: str) -> bool | None:
    plan = await get_price_plan_by_key(session, key)
    if not plan:
        return None
    plan.is_active = not plan.is_active
    await session.commit()
    return plan.is_active


# ─── Model Costs ─────────────────────────────────────────────────────────────

async def get_all_model_costs(session: AsyncSession) -> list[ModelCost]:
    result = await session.execute(
        select(ModelCost)
        .where(ModelCost.is_active == True)
        .order_by(ModelCost.gen_type, ModelCost.display_name, ModelCost.model_key)
    )
    return list(result.scalars().all())


async def get_model_cost(session: AsyncSession, model_key: str) -> ModelCost | None:
    result = await session.execute(
        select(ModelCost).where(ModelCost.model_key == model_key)
    )
    return result.scalar_one_or_none()


async def get_first_active_model_cost(session: AsyncSession, keys: list[str]) -> ModelCost | None:
    result = await session.execute(
        select(ModelCost)
        .where(ModelCost.is_active == True, ModelCost.model_key.in_(keys))
    )
    costs = {cost.model_key: cost for cost in result.scalars().all()}
    for key in keys:
        if key in costs:
            return costs[key]
    return None


async def resolve_image_model_cost(
    session: AsyncSession,
    model_key: str,
    *,
    quality: str | None = None,
) -> ModelCost | None:
    return await get_first_active_model_cost(session, image_pricing_keys(model_key, quality))


async def resolve_video_model_cost(
    session: AsyncSession,
    model_key: str,
    *,
    duration: int | None = None,
    resolution: str | None = None,
) -> ModelCost | None:
    return await get_first_active_model_cost(
        session,
        video_pricing_keys(model_key, duration=duration, resolution=resolution),
    )


async def set_model_cost(session: AsyncSession, model_key: str, credits: float) -> bool:
    result = await session.execute(
        update(ModelCost)
        .where(ModelCost.model_key == model_key)
        .values(credits=credits)
        .returning(ModelCost.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None

async def get_generation_by_id(session, generation_id: int):
    result = await session.execute(
        select(Generation).where(Generation.id == generation_id)
    )
    return result.scalar_one_or_none()

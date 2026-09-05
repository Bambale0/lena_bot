# db/repository.py
from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from inspect import isawaitable
from urllib.parse import urlparse

from sqlalchemy import Date, cast, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from api.public_files import mirror_url, public_url_is_available
from core.config import settings
from core.model_pricing import image_pricing_keys, pricing_variant_key, video_pricing_keys
from db.models import (
    CreditLedgerEntry,
    FeedRemixPayout,
    Generation,
    GenerationStatus,
    GenerationType,
    ImageGenerationAction,
    ImageSession,
    ImageSessionStatus,
    ModelCost,
    PaymentProvider,
    PricePlan,
    PromoCode,
    PromoRedemption,
    PromoRewardType,
    ReferralWithdrawalRequest,
    SunoVoice,
    Transaction,
    TransactionStatus,
    User,
    WebAuthCode,
    WithdrawalStatus,
)

logger = logging.getLogger(__name__)

ACTIVE_GENERATION_WINDOW = timedelta(minutes=45)
EXPIRED_FEED_MEDIA_HOSTS = {"tempfile.aiquickdraw.com"}


def _feed_media_url_is_available(url: str | None) -> bool:
    if not public_url_is_available(url):
        return False
    if url and urlparse(url).netloc.lower() in EXPIRED_FEED_MEDIA_HOSTS:
        return False
    return True


async def _publish_generation_update(gen: Generation | None) -> None:
    if not gen:
        return
    try:
        from api.realtime import publish_generation_event

        await publish_generation_event(gen)
    except Exception as exc:
        logger.warning("Failed to publish realtime generation event gen=%s: %s", getattr(gen, "id", None), exc)


def feed_remix_royalty_credits(credits_spent: float | int) -> float:
    value = Decimal(str(credits_spent or 0))
    if value <= 0:
        return 0.0
    royalty = (value * Decimal("0.05")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return float(royalty)


async def credit_feed_remix_payout(
    session: AsyncSession,
    *,
    generation: Generation,
    source_generation: Generation,
) -> float:
    existing = await session.execute(
        select(FeedRemixPayout.id).where(FeedRemixPayout.generation_id == generation.id)
    )
    if existing.scalar_one_or_none() is not None:
        return 0.0

    rub_per_credit = await _active_price_plan_rub_per_credit(session)
    amount_rub = feed_remix_royalty_rub(generation.credits_spent, rub_per_credit)
    if amount_rub <= 0:
        return 0.0

    payout = FeedRemixPayout(
        generation_id=generation.id,
        source_generation_id=source_generation.id,
        source_user_id=source_generation.user_id,
        remixer_user_id=generation.user_id,
        credits_spent=float(generation.credits_spent or 0.0),
        amount_rub=amount_rub,
    )
    session.add(payout)
    await session.execute(
        update(User)
        .where(User.id == source_generation.user_id)
        .values(referral_balance=User.referral_balance + amount_rub)
    )
    await session.commit()
    return amount_rub


@dataclass(frozen=True)
class FeedGenerationCard:
    generation: Generation
    username: str | None
    full_name: str | None
    author_photo_url: str | None
    aspect_ratio: str | None
    quality: str | None
    count: int | None
    reference_url: str | None
    reference_urls: str | None
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
class ReferralBindingView:
    user: User
    referrer: User | None
    referrer_l2: User | None
    referrer_l3: User | None
    generations_count: int
    paid_rub: float


@dataclass(frozen=True)
class WithdrawalRequestView:
    request: ReferralWithdrawalRequest
    user: User


@dataclass(frozen=True)
class ReferralBalanceSnapshot:
    user: User
    total_earned: float
    pending_withdrawals: float
    available_to_withdraw: float


class InsufficientReferralBalanceError(ValueError):
    def __init__(self, available_amount: float):
        super().__init__(f"Insufficient referral balance: available={available_amount:.2f}")
        self.available_amount = available_amount


@dataclass(frozen=True)
class PromoRedeemResult:
    promo: PromoCode
    redemption: PromoRedemption
    credits_added: float
    discount_reserved: bool
    balance_after: float | None = None


# ─── User ────────────────────────────────────────────────────────────────────

async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    cleaned = username.strip().lstrip("@")
    if not cleaned:
        return None
    result = await session.execute(
        select(User).where(func.lower(User.username) == cleaned.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    result = await session.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()


async def _insert_credit_ledger(
    session: AsyncSession,
    *,
    user_id: int,
    delta: float,
    balance_after: float,
    entry_type: str,
    source_type: str | None = None,
    source_id: str | None = None,
    note: str | None = None,
) -> None:
    session.add(CreditLedgerEntry(
        user_id=user_id,
        delta=delta,
        balance_after=balance_after,
        entry_type=entry_type,
        source_type=source_type,
        source_id=source_id,
        note=note,
    ))


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
    try:
        await session.flush()
        if welcome_credits:
            await _insert_credit_ledger(
                session,
                user_id=user.id,
                delta=welcome_credits,
                balance_after=welcome_credits,
                entry_type="welcome_bonus",
                source_type="user",
                source_id=str(tg_id),
                note="Welcome bonus credits on signup",
            )
        await session.commit()
        await session.refresh(user)
        logger.info("User created: tg_id=%s", tg_id)
        return user
    except IntegrityError as exc:
        await session.rollback()
        existing = await get_user_by_tg_id(session, tg_id)
        if existing is None:
            raise
        logger.warning("create_user race handled: tg_id=%s err=%s", tg_id, exc.__class__.__name__)
        return existing


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_phone(session: AsyncSession, phone: str) -> User | None:
    result = await session.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def create_contact_user(
    session: AsyncSession,
    *,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
    welcome_credits: float = 0,
    referrer: User | None = None,
    referrer_l2: User | None = None,
    referrer_l3: User | None = None,
    language: str = "ru",
) -> User:
    for _ in range(8):
        pseudo_tg_id = -secrets.randbelow(9_000_000_000_000) - 1
        if await get_user_by_tg_id(session, pseudo_tg_id) is None:
            break
    else:
        raise RuntimeError("Could not allocate web user id")

    user = User(
        tg_id=pseudo_tg_id,
        email=email.lower() if email else None,
        phone=phone,
        full_name=full_name,
        credits=welcome_credits,
        referral_code=secrets.token_urlsafe(8),
        referrer_id=referrer.id if referrer else None,
        referrer_l2_id=referrer_l2.id if referrer_l2 else None,
        referrer_l3_id=referrer_l3.id if referrer_l3 else None,
        language=language,
    )
    session.add(user)
    await session.flush()
    if welcome_credits:
        await _insert_credit_ledger(
            session,
            user_id=user.id,
            delta=welcome_credits,
            balance_after=welcome_credits,
            entry_type="welcome_bonus",
            source_type="web_contact",
            source_id=email or phone or str(pseudo_tg_id),
            note="Welcome bonus credits on web signup",
        )
    await session.commit()
    await session.refresh(user)
    logger.info("Web contact user created: user_id=%s", user.id)
    return user


async def update_user_profile(
    session: AsyncSession,
    user_id: int,
    **values,
) -> User | None:
    allowed = {"username", "full_name", "email", "phone", "photo_url", "language"}
    clean_values = {key: value for key, value in values.items() if key in allowed}
    if not clean_values:
        return await get_user_by_id(session, user_id)
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(**clean_values)
    )
    await session.commit()
    return await get_user_by_id(session, user_id)


async def set_user_password_hash(
    session: AsyncSession,
    user_id: int,
    password_hash: str,
) -> User | None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(password_hash=password_hash, password_set_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return await get_user_by_id(session, user_id)


async def create_web_auth_code(
    session: AsyncSession,
    *,
    contact_type: str,
    contact: str,
    code_hash: str,
    expires_at: datetime,
) -> WebAuthCode:
    code = WebAuthCode(
        contact_type=contact_type,
        contact=contact,
        code_hash=code_hash,
        expires_at=expires_at,
    )
    session.add(code)
    await session.commit()
    await session.refresh(code)
    return code


async def get_recent_web_auth_code(
    session: AsyncSession,
    *,
    contact_type: str,
    contact: str,
    now: datetime,
) -> WebAuthCode | None:
    result = await session.execute(
        select(WebAuthCode)
        .where(
            WebAuthCode.contact_type == contact_type,
            WebAuthCode.contact == contact,
            WebAuthCode.consumed_at.is_(None),
            WebAuthCode.expires_at > now,
        )
        .order_by(desc(WebAuthCode.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def consume_active_web_auth_codes(
    session: AsyncSession,
    *,
    contact_type: str,
    contact: str,
    now: datetime,
) -> None:
    await session.execute(
        update(WebAuthCode)
        .where(
            WebAuthCode.contact_type == contact_type,
            WebAuthCode.contact == contact,
            WebAuthCode.consumed_at.is_(None),
            WebAuthCode.expires_at > now,
        )
        .values(consumed_at=now)
    )
    await session.commit()


async def get_active_web_auth_code(
    session: AsyncSession,
    *,
    contact_type: str,
    contact: str,
    code_hash: str,
    now: datetime,
) -> WebAuthCode | None:
    result = await session.execute(
        select(WebAuthCode)
        .where(
            WebAuthCode.contact_type == contact_type,
            WebAuthCode.contact == contact,
            WebAuthCode.code_hash == code_hash,
            WebAuthCode.consumed_at.is_(None),
            WebAuthCode.expires_at > now,
            WebAuthCode.attempts < 5,
        )
        .order_by(desc(WebAuthCode.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def consume_web_auth_code(session: AsyncSession, code_id: int, *, now: datetime) -> None:
    await session.execute(
        update(WebAuthCode)
        .where(WebAuthCode.id == code_id, WebAuthCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    await session.commit()


async def increment_web_auth_attempts(
    session: AsyncSession,
    *,
    contact_type: str,
    contact: str,
    now: datetime,
) -> None:
    await session.execute(
        update(WebAuthCode)
        .where(
            WebAuthCode.contact_type == contact_type,
            WebAuthCode.contact == contact,
            WebAuthCode.consumed_at.is_(None),
            WebAuthCode.expires_at > now,
        )
        .values(attempts=WebAuthCode.attempts + 1)
    )
    await session.commit()


async def bind_user_telegram(
    session: AsyncSession,
    *,
    user_id: int,
    tg_id: int,
    username: str | None = None,
    full_name: str | None = None,
    photo_url: str | None = None,
) -> User | None:
    tg_is_free = ~select(User.id).where(User.tg_id == tg_id, User.id != user_id).exists()
    try:
        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .where(or_(User.tg_id == tg_id, tg_is_free))
            .values(
                tg_id=tg_id,
                username=username,
                full_name=full_name,
                photo_url=photo_url,
            )
            .returning(User)
        )
        user = result.scalar_one_or_none()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    if user:
        await session.refresh(user)
    return user


async def bind_user_referrer_once(
    session: AsyncSession,
    user_id: int,
    *,
    referrer: User,
    referrer_l2: User | None = None,
    referrer_l3: User | None = None,
) -> bool:
    result = await session.execute(
        update(User)
        .where(
            User.id == user_id,
            User.referrer_id.is_(None),
            User.referrer_l2_id.is_(None),
            User.referrer_l3_id.is_(None),
        )
        .values(
            referrer_id=referrer.id,
            referrer_l2_id=referrer_l2.id if referrer_l2 else None,
            referrer_l3_id=referrer_l3.id if referrer_l3 else None,
        )
        .returning(User.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def set_user_language(session: AsyncSession, user_id: int, language: str) -> None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(language=language)
    )
    await session.commit()


async def set_user_photo_url(session: AsyncSession, user_id: int, photo_url: str | None) -> User | None:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(photo_url=photo_url)
        .returning(User)
    )
    user = result.scalar_one_or_none()
    await session.commit()
    if user:
        await session.refresh(user)
    return user


async def add_credits(
    session: AsyncSession,
    user_id: int,
    amount: float,
    *,
    entry_type: str = "adjustment",
    source_type: str | None = None,
    source_id: str | None = None,
    note: str | None = None,
) -> float:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(credits=User.credits + amount)
        .returning(User.credits)
    )
    new_balance = result.scalar_one()
    await _insert_credit_ledger(
        session,
        user_id=user_id,
        delta=amount,
        balance_after=new_balance,
        entry_type=entry_type,
        source_type=source_type,
        source_id=source_id,
        note=note,
    )
    await session.commit()
    return new_balance


async def add_referral_balance(session: AsyncSession, user_id: int, amount_rub: float) -> float:
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(referral_balance=User.referral_balance + amount_rub)
        .returning(User.referral_balance)
    )
    await session.commit()
    return result.scalar_one()


async def spend_credits(
    session: AsyncSession,
    user_id: int,
    amount: float,
    *,
    entry_type: str = "spend",
    source_type: str | None = None,
    source_id: str | None = None,
    note: str | None = None,
) -> bool:
    """Atomically deduct credits. Returns False if not enough credits."""
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.credits >= amount)
        .values(credits=User.credits - amount)
        .returning(User.credits)
    )
    new_balance = result.scalar_one_or_none()
    if new_balance is None:
        await session.commit()
        return False
    await _insert_credit_ledger(
        session,
        user_id=user_id,
        delta=-amount,
        balance_after=new_balance,
        entry_type=entry_type,
        source_type=source_type,
        source_id=source_id,
        note=note,
    )
    await session.commit()
    return True


# ─── Promo codes ─────────────────────────────────────────────────────────────

def normalize_promo_code(code: str) -> str:
    return (code or "").strip().upper()


async def get_promo_code(session: AsyncSession, code: str) -> PromoCode | None:
    normalized = normalize_promo_code(code)
    if not normalized:
        return None
    result = await session.execute(select(PromoCode).where(PromoCode.code == normalized))
    return result.scalar_one_or_none()


async def upsert_promo_code(
    session: AsyncSession,
    *,
    code: str,
    reward_type: PromoRewardType,
    value: float,
    max_uses: int | None = None,
    per_user_limit: int = 1,
    is_active: bool = True,
    note: str | None = None,
    expires_at: datetime | None = None,
) -> PromoCode:
    normalized = normalize_promo_code(code)
    promo = await get_promo_code(session, normalized)
    if promo:
        promo.reward_type = reward_type
        promo.value = value
        promo.credits = value if reward_type in {PromoRewardType.credits, PromoRewardType.free_generation} else 0.0
        promo.max_uses = max_uses
        promo.max_redemptions = max_uses
        promo.per_user_limit = max(1, int(per_user_limit or 1))
        promo.is_active = is_active
        promo.note = note
        promo.expires_at = expires_at
        promo.valid_until = expires_at
    else:
        promo = PromoCode(
            code=normalized,
            reward_type=reward_type,
            value=value,
            credits=value if reward_type in {PromoRewardType.credits, PromoRewardType.free_generation} else 0.0,
            max_uses=max_uses,
            max_redemptions=max_uses,
            per_user_limit=max(1, int(per_user_limit or 1)),
            is_active=is_active,
            note=note,
            expires_at=expires_at,
            valid_until=expires_at,
        )
        session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def get_active_discount_redemption(session: AsyncSession, user_id: int) -> PromoRedemption | None:
    result = await session.execute(
        select(PromoRedemption)
        .where(
            PromoRedemption.user_id == user_id,
            PromoRedemption.consumed_at.is_(None),
            PromoRedemption.reward_type.in_(
                (PromoRewardType.discount_percent, PromoRewardType.discount_amount)
            ),
        )
        .order_by(PromoRedemption.created_at.desc(), PromoRedemption.id.desc())
    )
    return result.scalars().first()


async def mark_promo_discount_consumed(
    session: AsyncSession,
    redemption_id: int,
    *,
    transaction_id: int,
) -> PromoRedemption | None:
    result = await session.execute(
        update(PromoRedemption)
        .where(
            PromoRedemption.id == redemption_id,
            PromoRedemption.consumed_at.is_(None),
        )
        .values(transaction_id=transaction_id, consumed_at=datetime.now(timezone.utc))
        .returning(PromoRedemption)
    )
    redemption = result.scalar_one_or_none()
    await session.commit()
    return redemption


async def redeem_promo_code(
    session: AsyncSession,
    *,
    user_id: int,
    code: str,
) -> PromoRedeemResult:
    normalized = normalize_promo_code(code)
    promo_result = await session.execute(
        select(PromoCode).where(PromoCode.code == normalized).with_for_update()
    )
    promo = promo_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not promo or not promo.is_active:
        raise ValueError("Промокод не найден или выключен.")
    expires_at = promo.expires_at or promo.valid_until
    if expires_at and expires_at <= now:
        raise ValueError("Срок действия промокода истёк.")
    max_uses = promo.max_uses if promo.max_uses is not None else promo.max_redemptions
    uses_count = max(promo.uses_count or 0, promo.redeemed_count or 0)
    if max_uses is not None and uses_count >= max_uses:
        raise ValueError("Лимит использований промокода уже закончился.")

    existing_result = await session.execute(
        select(func.count())
        .select_from(PromoRedemption)
        .where(PromoRedemption.promo_code_id == promo.id, PromoRedemption.user_id == user_id)
    )
    if int(existing_result.scalar_one() or 0) >= promo.per_user_limit:
        raise ValueError("Ты уже использовал(а) этот промокод.")

    reward_type = promo.reward_type
    credits_added = 0.0
    discount_reserved = reward_type in {PromoRewardType.discount_percent, PromoRewardType.discount_amount}
    consumed_at = None if discount_reserved else now

    if reward_type in {PromoRewardType.credits, PromoRewardType.free_generation}:
        credits_added = float(promo.value or promo.credits or 0)
        if credits_added <= 0:
            raise ValueError("Промокод настроен некорректно.")

    redemption = PromoRedemption(
        promo_code_id=promo.id,
        user_id=user_id,
        reward_type=reward_type,
        value=float(promo.value or 0),
        consumed_at=consumed_at,
    )
    session.add(redemption)
    promo.uses_count += 1
    promo.redeemed_count += 1

    balance_after: float | None = None
    if credits_added:
        balance_result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(credits=User.credits + credits_added)
            .returning(User.credits)
        )
        balance_after = balance_result.scalar_one()
        await _insert_credit_ledger(
            session,
            user_id=user_id,
            delta=credits_added,
            balance_after=balance_after,
            entry_type="promo_credit",
            source_type="promo_code",
            source_id=promo.code,
            note=f"Promo {promo.code}: {reward_type.value}",
        )

    await session.commit()
    await session.refresh(redemption)
    await session.refresh(promo)
    return PromoRedeemResult(
        promo=promo,
        redemption=redemption,
        credits_added=credits_added,
        discount_reserved=discount_reserved,
        balance_after=balance_after,
    )


async def count_users(session: AsyncSession) -> float:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.tg_id).where(User.is_banned.is_(False)))
    return list(result.scalars().all())


async def get_broadcast_recipient_ids(session: AsyncSession, segment: str = "all") -> list[int]:
    base = select(User.tg_id).where(User.is_banned.is_(False))

    if segment == "all":
        result = await session.execute(base)
        return list(result.scalars().all())

    if segment == "paid":
        stmt = (
            select(User.tg_id)
            .join(Transaction, Transaction.user_id == User.id)
            .where(
                User.is_banned.is_(False),
                Transaction.status == TransactionStatus.paid,
            )
            .distinct()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    if segment == "new":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = base.where(User.created_at >= cutoff)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    if segment == "active":
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        recent_generation_users = select(Generation.user_id).where(Generation.created_at >= cutoff)
        recent_paid_users = select(Transaction.user_id).where(
            Transaction.created_at >= cutoff,
            Transaction.status == TransactionStatus.paid,
        )
        stmt = base.where(
            (User.id.in_(recent_generation_users))
            | (User.id.in_(recent_paid_users))
            | (User.created_at >= cutoff)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    result = await session.execute(base)
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


async def get_all_referral_bindings(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[ReferralBindingView]:
    ref1 = aliased(User)
    ref2 = aliased(User)
    ref3 = aliased(User)
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
            ref1,
            ref2,
            ref3,
            func.coalesce(gens.c.count, 0),
            func.coalesce(revenue.c.rub, 0),
        )
        .outerjoin(ref1, ref1.id == User.referrer_id)
        .outerjoin(ref2, ref2.id == User.referrer_l2_id)
        .outerjoin(ref3, ref3.id == User.referrer_l3_id)
        .outerjoin(gens, gens.c.user_id == User.id)
        .outerjoin(revenue, revenue.c.user_id == User.id)
        .where(
            (User.referrer_id.is_not(None))
            | (User.referrer_l2_id.is_not(None))
            | (User.referrer_l3_id.is_not(None))
        )
        .order_by(desc(User.created_at))
        .limit(limit)
    )
    return [
        ReferralBindingView(
            user=user,
            referrer=referrer,
            referrer_l2=referrer_l2,
            referrer_l3=referrer_l3,
            generations_count=int(gens_count or 0),
            paid_rub=float(paid_rub or 0),
        )
        for user, referrer, referrer_l2, referrer_l3, gens_count, paid_rub in result.all()
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
    input_params: dict | list | str | None = None,
) -> Generation:
    if isinstance(input_params, (dict, list)):
        input_params_value = json.dumps(input_params, ensure_ascii=False)
    else:
        input_params_value = input_params
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
        input_params=input_params_value,
        status=GenerationStatus.pending,
    )
    session.add(gen)
    await session.commit()
    await session.refresh(gen)
    await _publish_generation_update(gen)
    return gen


async def update_generation_task(
    session: AsyncSession, gen_id: int, task_id: str
) -> None:
    result = await session.execute(
        update(Generation)
        .where(Generation.id == gen_id)
        .values(task_id=task_id, status=GenerationStatus.processing)
        .returning(Generation)
    )
    gen = result.scalar_one_or_none()
    await session.commit()
    await _publish_generation_update(gen)


async def finish_generation(
    session: AsyncSession,
    gen_id: int,
    result_url: str,
    result_urls: list[str] | None = None,
) -> Generation | None:
    original_urls = [url for url in (result_urls or [result_url]) if url]
    clean_urls: list[str] = []
    for url in original_urls:
        mirrored = await mirror_url(url)
        if mirrored:
            clean_urls.append(mirrored)
    if not clean_urls:
        clean_urls = original_urls
    result_url = clean_urls[0] if clean_urls else result_url
    result = await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        )
        .values(
            status=GenerationStatus.done,
            result_url=result_url,
            result_urls=json.dumps(clean_urls, ensure_ascii=False),
            finished_at=datetime.now(timezone.utc),
        )
        .returning(Generation)
    )
    gen = result.scalar_one_or_none()
    await session.commit()

    # Already finalized elsewhere; do not double-credit royalties.
    if not gen:
        return None

    await _publish_generation_update(gen)

    # Pay a fixed reward to the author of the source feed post (if remixed from feed).

    if not gen.source_feed_gen_id:
        return gen

    source = await get_generation_by_id(session, gen.source_feed_gen_id)
    if not source:
        logger.info(
            "Feed remix royalty skipped: reason=source_generation_not_found source_generation=%s generation=%s remixer=%s credits_spent=%s",
            gen.source_feed_gen_id,
            gen.id,
            gen.user_id,
            gen.credits_spent,
        )
        return gen

    if source.user_id == gen.user_id:
        logger.info(
            "Feed remix royalty skipped: reason=self_remix source_user=%s remixer=%s source_generation=%s generation=%s credits_spent=%s",
            source.user_id,
            gen.user_id,
            source.id,
            gen.id,
            gen.credits_spent,
        )
        return gen

    if gen.credits_spent <= 0:
        logger.info(
            "Feed remix royalty skipped: reason=non_positive_credits source_user=%s remixer=%s source_generation=%s generation=%s credits_spent=%s",
            source.user_id,
            gen.user_id,
            source.id,
            gen.id,
            gen.credits_spent,
        )
        return gen

    amount_rub = await credit_feed_remix_payout(
        session,
        generation=gen,
        source_generation=source,
    )
    if amount_rub <= 0:
        logger.info(
            "Feed remix royalty skipped: reason=zero_or_duplicate_rub_payout source_user=%s remixer=%s source_generation=%s generation=%s credits_spent=%s",
            source.user_id,
            gen.user_id,
            source.id,
            gen.id,
            gen.credits_spent,
        )
        return gen

    logger.info(
        "Feed remix royalty credited: source_user=%s remixer=%s credits_spent=%s amount_rub=%s source_generation=%s generation=%s",
        source.user_id,
        gen.user_id,
        gen.credits_spent,
        amount_rub,
        source.id,
        gen.id,
    )
    return gen


async def fail_generation(
    session: AsyncSession, gen_id: int, error: str
) -> bool:
    result = await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        )
        .values(
            status=GenerationStatus.failed,
            error_msg=error,
            finished_at=datetime.now(timezone.utc),
        )
        .returning(Generation)
    )
    gen = result.scalar_one_or_none()
    updated = gen is not None
    await session.commit()
    await _publish_generation_update(gen)
    return updated

async def get_generation_by_id(session: AsyncSession, gen_id: int) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.id == gen_id))
    return result.scalar_one_or_none()


async def get_generation_by_task_id(session: AsyncSession, task_id: str) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.task_id == task_id))
    return result.scalar_one_or_none()


# ─── Suno voices ─────────────────────────────────────────────────────────────

async def create_suno_voice(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    source_audio_url: str,
    validate_task_id: str,
    language: str = "en",
    vocal_start_s: float = 0.0,
    vocal_end_s: float = 10.0,
    description: str | None = None,
    style: str | None = None,
    singer_skill_level: str | None = None,
) -> SunoVoice:
    voice = SunoVoice(
        user_id=user_id,
        name=name,
        description=description,
        style=style,
        source_audio_url=source_audio_url,
        validate_task_id=validate_task_id,
        language=language,
        vocal_start_s=vocal_start_s,
        vocal_end_s=vocal_end_s,
        singer_skill_level=singer_skill_level,
        status="validating",
    )
    session.add(voice)
    await session.commit()
    await session.refresh(voice)
    return voice


async def list_suno_voices(session: AsyncSession, user_id: int) -> list[SunoVoice]:
    result = await session.execute(
        select(SunoVoice)
        .where(SunoVoice.user_id == user_id)
        .order_by(SunoVoice.created_at.desc(), SunoVoice.id.desc())
    )
    return list(result.scalars().all())


async def get_suno_voice(session: AsyncSession, user_id: int, voice_id: int) -> SunoVoice | None:
    result = await session.execute(
        select(SunoVoice).where(SunoVoice.id == voice_id, SunoVoice.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_suno_voice_by_validate_task_id(
    session: AsyncSession,
    validate_task_id: str,
) -> SunoVoice | None:
    result = await session.execute(
        select(SunoVoice).where(SunoVoice.validate_task_id == validate_task_id)
    )
    return result.scalar_one_or_none()


async def get_suno_voice_by_voice_task_id(
    session: AsyncSession,
    voice_task_id: str,
) -> SunoVoice | None:
    result = await session.execute(select(SunoVoice).where(SunoVoice.voice_task_id == voice_task_id))
    return result.scalar_one_or_none()


async def update_suno_voice(
    session: AsyncSession,
    voice_id: int,
    **values,
) -> SunoVoice | None:
    allowed = {
        "name",
        "description",
        "style",
        "source_audio_url",
        "verify_audio_url",
        "validate_task_id",
        "voice_task_id",
        "voice_id",
        "validate_phrase",
        "language",
        "vocal_start_s",
        "vocal_end_s",
        "singer_skill_level",
        "status",
        "error_msg",
    }
    clean_values = {key: value for key, value in values.items() if key in allowed}
    clean_values["updated_at"] = datetime.now(timezone.utc)
    result = await session.execute(
        update(SunoVoice)
        .where(SunoVoice.id == voice_id)
        .values(**clean_values)
        .returning(SunoVoice)
    )
    voice = result.scalar_one_or_none()
    await session.commit()
    return voice


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


async def _feed_cards_from_stmt(session: AsyncSession, stmt, *, require_media: bool = True) -> list[FeedGenerationCard]:
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
            User.photo_url,
            ImageSession.aspect_ratio,
            ImageSession.quality,
            ImageSession.count,
            ImageSession.reference_url,
            ImageSession.reference_urls,
            func.coalesce(remix_counts.c.remix_count, 0).label("remix_count"),
        )
    )
    cards: list[FeedGenerationCard] = []
    for gen, username, full_name, author_photo_url, aspect_ratio, quality, count, reference_url, reference_urls, remix_count in result.all():
        if require_media and not _feed_media_url_is_available(gen.result_url):
            continue
        remix_total = int(remix_count or 0)
        cards.append(
            FeedGenerationCard(
                generation=gen,
                username=username,
                full_name=full_name,
                author_photo_url=author_photo_url,
                aspect_ratio=aspect_ratio,
                quality=quality,
                count=count,
                reference_url=reference_url,
                reference_urls=reference_urls,
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
    limit: int = 100,
) -> list[FeedGenerationCard]:
    stmt = (
        select(Generation)
        .where(
            Generation.gen_type.in_((GenerationType.image, GenerationType.video)),
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            Generation.is_public_feed.is_(True),
        )
        .order_by(desc(Generation.created_at))
        .limit(max(limit, 1) * 3)
    )
    cards = await _feed_cards_from_stmt(session, stmt)
    return cards[:limit]


async def get_user_feed_generations(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 200,
) -> list[FeedGenerationCard]:
    stmt = (
        select(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.gen_type.in_((GenerationType.image, GenerationType.video)),
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
            Generation.gen_type.in_((GenerationType.image, GenerationType.video)),
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
    *,
    require_media: bool = True,
) -> FeedGenerationCard | None:
    stmt = (
        select(Generation)
        .where(
            Generation.id == gen_id,
            Generation.gen_type.in_((GenerationType.image, GenerationType.video)),
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            Generation.is_public_feed.is_(True),
        )
        .limit(1)
    )
    cards = await _feed_cards_from_stmt(session, stmt, require_media=require_media)
    return cards[0] if cards else None


def _own_or_empty_feed_source_clause(user_id: int):
    source_gen = aliased(Generation)
    return or_(
        Generation.source_feed_gen_id.is_(None),
        Generation.source_feed_gen_id.in_(
            select(source_gen.id).where(source_gen.user_id == user_id)
        ),
    )


async def share_to_feed(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    result = await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            _own_or_empty_feed_source_clause(user_id),
        )
        .values(
            is_public_feed=True,
        )
        .returning(Generation.id)
    )
    updated_id = result.scalar_one_or_none()
    await session.commit()
    if not updated_id:
        return None

    gen = await get_generation_by_id(session, gen_id)
    if not gen:
        return None

    # Mirror external URLs to local storage so feed images don't expire.
    original_urls = [gen.result_url] if gen.result_url else []
    if gen.result_urls:
        try:
            parsed = json.loads(gen.result_urls)
            if isinstance(parsed, list):
                original_urls = [str(u) for u in parsed if u] or original_urls
        except (json.JSONDecodeError, TypeError):
            pass

    clean_urls: list[str] = []
    for url in original_urls:
        mirrored = await mirror_url(url, subdir="feed")
        clean_urls.append(mirrored or url)

    if clean_urls:
        await session.execute(
            update(Generation)
            .where(Generation.id == updated_id)
            .values(
                result_url=clean_urls[0],
                result_urls=json.dumps(clean_urls, ensure_ascii=False),
            )
        )
        await session.commit()
        gen = await get_generation_by_id(session, gen_id)
    return gen


async def remove_from_feed(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.is_public_feed.is_(True),
        )
        .values(is_public_feed=False)
    )
    await session.commit()
    return await get_generation_by_id(session, gen_id)


async def share_to_library(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    result = await session.execute(
        update(Generation)
        .where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.status == GenerationStatus.done,
            Generation.result_url.is_not(None),
            _own_or_empty_feed_source_clause(user_id),
        )
        .values(is_prompt_library=True)
        .returning(Generation.id)
    )
    updated_id = result.scalar_one_or_none()
    await session.commit()
    return await get_generation_by_id(session, gen_id) if updated_id else None


async def remove_from_library(session: AsyncSession, gen_id: int, user_id: int) -> Generation | None:
    result = await session.execute(
        select(Generation).where(
            Generation.id == gen_id,
            Generation.user_id == user_id,
            Generation.is_prompt_library.is_(True),
        )
    )
    gen = result.scalar_one_or_none()
    if not gen:
        return None
    gen.is_prompt_library = False
    await session.commit()
    await session.refresh(gen)
    return gen


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
            Generation.is_public_feed.is_(True),
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
            Generation.is_public_feed.is_(True),
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
    reference_urls: list[str] | None = None,
) -> ImageSession:
    await archive_active_image_sessions(session, user_id)

    normalized_reference_file_ids = [item for item in (reference_file_ids or []) if item]
    if reference_file_id and reference_file_id not in normalized_reference_file_ids:
        normalized_reference_file_ids.insert(0, reference_file_id)

    if isinstance(reference_url, list):
        reference_urls = [str(item) for item in reference_url if item]
        reference_url = next(iter(reference_urls), None)

    normalized_reference_urls = [str(item) for item in (reference_urls or []) if item]
    if reference_url and reference_url not in normalized_reference_urls:
        normalized_reference_urls.insert(0, reference_url)
    if normalized_reference_urls:
        reference_url = normalized_reference_urls[0]

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
        reference_urls=json.dumps(normalized_reference_urls, ensure_ascii=False) if normalized_reference_urls else None,
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


async def get_image_sessions_by_ids(
    session: AsyncSession,
    image_session_ids: list[int],
) -> dict[int, ImageSession]:
    ids = sorted({int(item) for item in image_session_ids if item})
    if not ids:
        return {}
    result = await session.execute(select(ImageSession).where(ImageSession.id.in_(ids)))
    return {item.id: item for item in result.scalars().all()}


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
    mode: str | None = None,
) -> None:
    normalized_reference_file_ids = [item for item in reference_file_ids if item]
    lead_reference_file_id = normalized_reference_file_ids[0] if normalized_reference_file_ids else None
    values = {
        "reference_file_id": lead_reference_file_id,
        "reference_file_ids": json.dumps(normalized_reference_file_ids, ensure_ascii=True) if normalized_reference_file_ids else None,
        "reference_url": None,
        "updated_at": func.now(),
    }
    if mode:
        values["mode"] = mode
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(**values)
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


async def get_user_active_generations(session: AsyncSession, user_id: int) -> list[Generation]:
    result = await session.execute(
        select(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]),
        )
        .order_by(desc(Generation.created_at), desc(Generation.id))
    )
    items = result.scalars().all()
    if isawaitable(items):
        items = await items
    return list(items)


async def count_user_active_generations(session: AsyncSession, user_id: int) -> float:
    cutoff = datetime.now(timezone.utc) - ACTIVE_GENERATION_WINDOW
    result = await session.execute(
        select(func.count())
        .select_from(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]),
            Generation.created_at >= cutoff,
        )
    )
    return result.scalar_one()


async def count_generations_today(session: AsyncSession) -> float:
    today = datetime.now(timezone.utc).date()
    result = await session.execute(
        select(func.count())
        .select_from(Generation)
        .where(cast(Generation.created_at, Date) == today)
    )
    return result.scalar_one()


# ─── Transactions ─────────────────────────────────────────────────────────────

async def get_transaction_by_external_id(
    session: AsyncSession,
    external_id: str,
) -> Transaction | None:
    result = await session.execute(select(Transaction).where(Transaction.external_id == external_id))
    return result.scalar_one_or_none()


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


async def confirm_transaction_and_add_credits(
    session: AsyncSession,
    external_id: str,
    *,
    entry_type: str = "payment_credit",
    note: str | None = None,
) -> tuple[Transaction, float] | None:
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
    if not tx:
        await session.rollback()
        return None

    balance_result = await session.execute(
        update(User)
        .where(User.id == tx.user_id)
        .values(credits=User.credits + tx.credits)
        .returning(User.credits)
    )
    new_balance = balance_result.scalar_one()
    await _insert_credit_ledger(
        session,
        user_id=tx.user_id,
        delta=tx.credits,
        balance_after=new_balance,
        entry_type=entry_type,
        source_type="transaction",
        source_id=str(tx.id),
        note=note or f"Payment confirmed via {tx.provider}",
    )
    await session.commit()
    return tx, new_balance


async def confirm_transaction_by_id(
    session: AsyncSession,
    tx_id: int,
    *,
    external_id: str | None = None,
) -> Transaction | None:
    values: dict[str, object] = {"status": TransactionStatus.paid}
    if external_id is not None:
        values["external_id"] = external_id

    result = await session.execute(
        update(Transaction)
        .where(
            Transaction.id == tx_id,
            Transaction.status == TransactionStatus.pending,
        )
        .values(**values)
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

async def convert_referral_balance_to_credits(
    session: AsyncSession,
    *,
    user_id: int,
    amount_rub: float,
    rub_per_credit: float,
) -> ReferralWithdrawalRequest:
    snapshot = await get_user_referral_balance_snapshot(session, user_id, lock_user=True)
    if snapshot is None:
        raise ValueError(f"User {user_id} not found")
    if amount_rub > snapshot.available_to_withdraw + 1e-9:
        raise InsufficientReferralBalanceError(snapshot.available_to_withdraw)
    if rub_per_credit <= 0:
        raise ValueError("rub_per_credit must be greater than zero")

    user = snapshot.user
    available_balance = float(user.referral_balance or 0.0)
    credits_delta = float(
        (Decimal(str(amount_rub)) / Decimal(str(rub_per_credit))).quantize(
            Decimal("0.001"),
            rounding=ROUND_HALF_UP,
        )
    )
    if credits_delta <= 0:
        raise ValueError("Referral exchange rate must produce a positive credit amount")

    user.referral_balance = max(0.0, available_balance - amount_rub)
    user.credits = float(user.credits or 0.0) + credits_delta

    request = ReferralWithdrawalRequest(
        user_id=user_id,
        amount_rub=amount_rub,
        payout_details="AUTO_CREDITS",
        status=WithdrawalStatus.approved,
        admin_tg_id=0,
        admin_note=f"Auto-converted to kisses at {rub_per_credit:g} RUB per credit",
        reviewed_at=func.now(),
    )
    session.add(request)
    await session.flush()
    await _insert_credit_ledger(
        session,
        user_id=user_id,
        delta=credits_delta,
        balance_after=float(user.credits or 0.0),
        entry_type="referral_exchange",
        source_type="referral_withdrawal",
        source_id=str(request.id),
        note=f"Referral balance converted to kisses: {amount_rub:g} RUB -> {credits_delta:g} credits",
    )
    await session.commit()
    await session.refresh(request)
    setattr(request, "amount_credits", credits_delta)
    return request


async def create_withdrawal_request(
    session: AsyncSession,
    *,
    user_id: int,
    amount_rub: float,
    payout_details: str,
) -> ReferralWithdrawalRequest:
    snapshot = await get_user_referral_balance_snapshot(session, user_id, lock_user=True)
    if snapshot is None:
        raise ValueError(f"User {user_id} not found")
    if amount_rub > snapshot.available_to_withdraw + 1e-9:
        raise InsufficientReferralBalanceError(snapshot.available_to_withdraw)

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


async def get_user_pending_withdrawal_total(session: AsyncSession, user_id: int) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(ReferralWithdrawalRequest.amount_rub), 0.0))
        .where(
            ReferralWithdrawalRequest.user_id == user_id,
            ReferralWithdrawalRequest.status == WithdrawalStatus.pending,
        )
    )
    return float(result.scalar_one())


async def _active_price_plan_rub_per_credit(session: AsyncSession) -> float:
    result = await session.execute(
        select(PricePlan)
        .where(
            PricePlan.is_active.is_(True),
            PricePlan.credits > 0,
            PricePlan.price_rub > 0,
        )
        .order_by(desc(PricePlan.credits), desc(PricePlan.sort_order), desc(PricePlan.id))
    )
    plans = list(result.scalars().all())
    if not plans:
        return 0.0
    rub_per_credit = min(
        (Decimal(str(plan.price_rub)) / Decimal(str(plan.credits)))
        for plan in plans
        if float(plan.credits or 0) > 0 and float(plan.price_rub or 0) > 0
    )
    return float(rub_per_credit)


def feed_remix_royalty_rub(credits_spent: float | int, rub_per_credit: float | int) -> float:
    if Decimal(str(credits_spent or 0)) <= 0:
        return 0.0
    reward = Decimal(str(settings.FEED_REMIX_REWARD_RUB or 0))
    return float(reward.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if reward > 0 else 0.0


async def get_user_feed_remix_reward_rub(session: AsyncSession, user_id: int) -> float:
    earned_result = await session.execute(
        select(func.coalesce(func.sum(FeedRemixPayout.amount_rub), 0.0)).where(
            FeedRemixPayout.source_user_id == user_id,
        )
    )
    earned_total = float(earned_result.scalar_one() or 0.0)

    user_result = await session.execute(select(User.referral_balance).where(User.id == user_id))
    referral_balance = float(user_result.scalar_one() or 0.0)

    pending_result = await session.execute(
        select(func.coalesce(func.sum(ReferralWithdrawalRequest.amount_rub), 0.0)).where(
            ReferralWithdrawalRequest.user_id == user_id,
            ReferralWithdrawalRequest.status == WithdrawalStatus.pending,
        )
    )
    pending_total = float(pending_result.scalar_one() or 0.0)
    available_balance = max(0.0, referral_balance - pending_total)

    return max(0.0, min(earned_total, available_balance))


async def get_user_referral_balance_snapshot(
    session: AsyncSession,
    user_id: int,
    *,
    lock_user: bool = False,
) -> ReferralBalanceSnapshot | None:
    query = select(User).where(User.id == user_id)
    if lock_user:
        query = query.with_for_update()

    user = (await session.execute(query)).scalar_one_or_none()
    if user is None:
        return None

    pending_withdrawals = await get_user_pending_withdrawal_total(session, user_id)
    total_earned = float(user.referral_balance or 0.0)
    available_to_withdraw = max(0.0, total_earned - pending_withdrawals)
    return ReferralBalanceSnapshot(
        user=user,
        total_earned=total_earned,
        pending_withdrawals=pending_withdrawals,
        available_to_withdraw=available_to_withdraw,
    )


async def set_withdrawal_status(
    session: AsyncSession,
    request_id: int,
    *,
    status: WithdrawalStatus,
    admin_tg_id: int,
    admin_note: str | None = None,
) -> WithdrawalRequestView | None:
    request = (
        await session.execute(
            select(ReferralWithdrawalRequest)
            .where(
                ReferralWithdrawalRequest.id == request_id,
                ReferralWithdrawalRequest.status == WithdrawalStatus.pending,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if request is None:
        return None

    if status == WithdrawalStatus.approved:
        user = (
            await session.execute(
                select(User).where(User.id == request.user_id).with_for_update()
            )
        ).scalar_one()
        available_balance = float(user.referral_balance or 0.0)
        if request.amount_rub > available_balance + 1e-9:
            raise InsufficientReferralBalanceError(available_balance)
        user.referral_balance = available_balance - request.amount_rub

    request.status = status
    request.admin_tg_id = admin_tg_id
    request.admin_note = admin_note
    request.reviewed_at = datetime.now(timezone.utc)

    await session.commit()
    return await get_withdrawal_request(session, request_id)


async def get_revenue_today(session: AsyncSession) -> float:
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
        .where(PricePlan.is_active.is_(True))
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
        .where(ModelCost.is_active.is_(True))
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
        .where(ModelCost.is_active.is_(True), ModelCost.model_key.in_(keys))
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


async def set_model_family_costs(
    session: AsyncSession,
    model_roots: tuple[str, ...] | list[str],
    credits: float,
) -> int:
    """Set one commercial price across base, mode and quality variants.

    A root matches both the exact model key and pricing variants using the
    ``<root>__...`` convention. This keeps the admin's commercial model price
    authoritative even when ``resolve_image_model_cost`` prefers a quality
    variant over the base row.
    """
    roots = tuple(dict.fromkeys(str(root).strip() for root in model_roots if str(root).strip()))
    if not roots:
        return 0

    clauses = []
    for root in roots:
        clauses.append(ModelCost.model_key == root)
        clauses.append(ModelCost.model_key.startswith(f"{root}__"))

    result = await session.execute(
        update(ModelCost)
        .where(or_(*clauses))
        .values(credits=credits)
        .returning(ModelCost.id)
    )
    updated_ids = list(result.scalars().all())
    await session.commit()
    return len(updated_ids)


async def set_model_family_quality_costs(
    session: AsyncSession,
    model_roots: tuple[str, ...] | list[str],
    quality: str,
    credits: float,
    *,
    sync_base: bool = False,
) -> int:
    """Set one quality tier across all internal routes of a commercial model."""
    roots = tuple(dict.fromkeys(str(root).strip() for root in model_roots if str(root).strip()))
    quality = str(quality).strip()
    if not roots or not quality:
        return 0

    keys = [pricing_variant_key(root, quality=quality) for root in roots]
    clauses = [ModelCost.model_key.in_(keys)]
    if sync_base:
        clauses.append(ModelCost.model_key.in_(roots))

    result = await session.execute(
        update(ModelCost)
        .where(or_(*clauses))
        .values(credits=credits)
        .returning(ModelCost.id)
    )
    updated_ids = list(result.scalars().all())
    await session.commit()
    return len(updated_ids)

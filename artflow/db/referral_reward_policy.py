from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import CreditLedgerEntry, Transaction, TransactionStatus, User

logger = logging.getLogger(__name__)

REFERRAL_FIRST_TOPUP_ENTRY_TYPE = "referral_first_topup_bonus"
REFERRAL_FIRST_TOPUP_SOURCE_TYPE = "referral_user"
LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE = "referral_signup_bonus"


async def award_referral_first_topup(
    session: AsyncSession,
    transaction: Transaction,
) -> bool:
    """Award the L1 credit reward exactly once on the referred user's first paid top-up.

    The referred user row is locked while eligibility is checked and the balance/ledger
    write is made. A partial unique index on the ledger is the final idempotency guard.
    Existing legacy signup-bonus ledger rows are treated as already rewarded so users
    who received the old bonus cannot receive a second migration-era bonus.
    """
    if settings.REFERRAL_FREEZE:
        return False

    bonus = float(settings.REFERRAL_L1_CREDITS or 0)
    if bonus <= 0:
        return False
    if transaction.status != TransactionStatus.paid:
        return False
    if float(transaction.amount_rub or 0) <= 0 or float(transaction.credits or 0) <= 0:
        return False

    referred = (
        await session.execute(
            select(User).where(User.id == transaction.user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if referred is None or not referred.referrer_id or referred.referrer_id == referred.id:
        await session.commit()
        return False

    first_paid_id = (
        await session.execute(
            select(Transaction.id)
            .where(
                Transaction.user_id == referred.id,
                Transaction.status == TransactionStatus.paid,
                Transaction.amount_rub > 0,
                Transaction.credits > 0,
            )
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if first_paid_id != transaction.id:
        await session.commit()
        return False

    legacy_source_ids = {str(referred.id)}
    try:
        tg_id = int(getattr(referred, "tg_id", 0) or 0)
    except (TypeError, ValueError):
        tg_id = 0
    if tg_id > 0:
        legacy_source_ids.add(str(tg_id))

    existing_reward = (
        await session.execute(
            select(CreditLedgerEntry.id)
            .where(
                CreditLedgerEntry.user_id == referred.referrer_id,
                or_(
                    and_(
                        CreditLedgerEntry.entry_type == REFERRAL_FIRST_TOPUP_ENTRY_TYPE,
                        CreditLedgerEntry.source_type == REFERRAL_FIRST_TOPUP_SOURCE_TYPE,
                        CreditLedgerEntry.source_id == str(referred.id),
                    ),
                    and_(
                        CreditLedgerEntry.entry_type == LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE,
                        CreditLedgerEntry.source_id.in_(sorted(legacy_source_ids)),
                    ),
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_reward is not None:
        await session.commit()
        return False

    balance_result = await session.execute(
        update(User)
        .where(User.id == referred.referrer_id)
        .values(credits=User.credits + bonus)
        .returning(User.credits)
    )
    new_balance = balance_result.scalar_one_or_none()
    if new_balance is None:
        await session.rollback()
        return False

    session.add(
        CreditLedgerEntry(
            user_id=referred.referrer_id,
            delta=bonus,
            balance_after=float(new_balance),
            entry_type=REFERRAL_FIRST_TOPUP_ENTRY_TYPE,
            source_type=REFERRAL_FIRST_TOPUP_SOURCE_TYPE,
            source_id=str(referred.id),
            note=f"L1 referral reward after first paid top-up; transaction_id={transaction.id}",
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Referral first-topup reward duplicate suppressed referred_user_id=%s tx_id=%s",
            referred.id,
            transaction.id,
        )
        return False

    logger.info(
        "Referral first-topup reward credited referrer_id=%s referred_user_id=%s tx_id=%s credits=%s",
        referred.referrer_id,
        referred.id,
        transaction.id,
        bonus,
    )
    return True


async def settle_referral_first_topup_for_user(
    session: AsyncSession,
    user_id: int,
) -> bool:
    """Settle an already-paid first top-up after a referral is bound late."""
    transaction = (
        await session.execute(
            select(Transaction)
            .where(
                Transaction.user_id == int(user_id),
                Transaction.status == TransactionStatus.paid,
                Transaction.amount_rub > 0,
                Transaction.credits > 0,
            )
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if transaction is None:
        return False
    return await award_referral_first_topup(session, transaction)


async def _paid_transaction_by_id(session: AsyncSession, tx_id: int) -> Transaction | None:
    return (
        await session.execute(
            select(Transaction).where(
                Transaction.id == int(tx_id),
                Transaction.status == TransactionStatus.paid,
            )
        )
    ).scalar_one_or_none()


def install_referral_reward_policy(
    repo_module: Any,
    *,
    award_func: Callable[[AsyncSession, Transaction], Awaitable[bool]] | None = None,
    settle_func: Callable[[AsyncSession, int], Awaitable[bool]] | None = None,
) -> None:
    """Install the production referral policy at the shared repository seam.

    Legacy signup-credit writes are suppressed. Successful transaction confirmation
    paths are wrapped so every payment provider can trigger the first-topup reward,
    including a provider retry after payment confirmation committed but reward delivery
    was interrupted. Late referral binding also settles an already-qualified first paid
    top-up, so the reward cannot be stranded by event ordering.
    """
    if getattr(repo_module, "_referral_reward_policy_installed", False):
        return

    reward = award_func or award_referral_first_topup
    settle = settle_func or settle_referral_first_topup_for_user

    original_add_credits = repo_module.add_credits
    original_bind_user_referrer_once = repo_module.bind_user_referrer_once
    original_confirm_transaction = repo_module.confirm_transaction
    original_confirm_transaction_and_add_credits = repo_module.confirm_transaction_and_add_credits
    original_confirm_transaction_by_id = repo_module.confirm_transaction_by_id

    @wraps(original_add_credits)
    async def add_credits(
        session,
        user_id,
        amount,
        *,
        entry_type="adjustment",
        source_type=None,
        source_id=None,
        note=None,
    ):
        if entry_type == LEGACY_REFERRAL_SIGNUP_ENTRY_TYPE:
            user = await repo_module.get_user_by_id(session, user_id)
            logger.info(
                "Deferred legacy referral signup reward user_id=%s source_id=%s until first paid top-up",
                user_id,
                source_id,
            )
            return float(getattr(user, "credits", 0) or 0)
        return await original_add_credits(
            session,
            user_id,
            amount,
            entry_type=entry_type,
            source_type=source_type,
            source_id=source_id,
            note=note,
        )

    @wraps(original_bind_user_referrer_once)
    async def bind_user_referrer_once(
        session,
        user_id,
        *,
        referrer,
        referrer_l2=None,
        referrer_l3=None,
    ):
        bound = await original_bind_user_referrer_once(
            session,
            user_id,
            referrer=referrer,
            referrer_l2=referrer_l2,
            referrer_l3=referrer_l3,
        )
        if bound:
            await settle(session, int(user_id))
        return bound

    @wraps(original_confirm_transaction)
    async def confirm_transaction(session, external_id):
        tx = await original_confirm_transaction(session, external_id)
        candidate = tx or await repo_module.get_transaction_by_external_id(session, external_id)
        if candidate is not None and candidate.status == TransactionStatus.paid:
            await reward(session, candidate)
        return tx

    @wraps(original_confirm_transaction_and_add_credits)
    async def confirm_transaction_and_add_credits(
        session,
        external_id,
        *,
        entry_type="payment_credit",
        note=None,
    ):
        result = await original_confirm_transaction_and_add_credits(
            session,
            external_id,
            entry_type=entry_type,
            note=note,
        )
        candidate = (
            result[0]
            if result
            else await repo_module.get_transaction_by_external_id(session, external_id)
        )
        if candidate is not None and candidate.status == TransactionStatus.paid:
            await reward(session, candidate)
        return result

    @wraps(original_confirm_transaction_by_id)
    async def confirm_transaction_by_id(session, tx_id, *, external_id=None):
        tx = await original_confirm_transaction_by_id(
            session,
            tx_id,
            external_id=external_id,
        )
        candidate = tx or await _paid_transaction_by_id(session, tx_id)
        if candidate is not None and candidate.status == TransactionStatus.paid:
            await reward(session, candidate)
        return tx

    repo_module.add_credits = add_credits
    repo_module.bind_user_referrer_once = bind_user_referrer_once
    repo_module.confirm_transaction = confirm_transaction
    repo_module.confirm_transaction_and_add_credits = confirm_transaction_and_add_credits
    repo_module.confirm_transaction_by_id = confirm_transaction_by_id
    repo_module._referral_reward_policy_installed = True
    repo_module._referral_reward_policy_originals = {
        "add_credits": original_add_credits,
        "bind_user_referrer_once": original_bind_user_referrer_once,
        "confirm_transaction": original_confirm_transaction,
        "confirm_transaction_and_add_credits": original_confirm_transaction_and_add_credits,
        "confirm_transaction_by_id": original_confirm_transaction_by_id,
    }

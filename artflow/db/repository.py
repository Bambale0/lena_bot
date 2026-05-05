# db/repository.py
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

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
    Transaction,
    TransactionStatus,
    User,
)

logger = logging.getLogger(__name__)


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
    welcome_credits: int,
    referrer: User | None = None,
    referrer_l2: User | None = None,
) -> User:
    user = User(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        credits=welcome_credits,
        referral_code=secrets.token_urlsafe(8),
        referrer_id=referrer.id if referrer else None,
        referrer_l2_id=referrer_l2.id if referrer_l2 else None,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("User created: tg_id=%s", tg_id)
    return user


async def add_credits(session: AsyncSession, user_id: int, amount: int) -> int:
    await session.execute(
        update(User).where(User.id == user_id).values(credits=User.credits + amount)
    )
    await session.commit()
    result = await session.execute(select(User.credits).where(User.id == user_id))
    return result.scalar_one()


async def spend_credits(session: AsyncSession, user_id: int, amount: int) -> bool:
    """Returns False if not enough credits."""
    result = await session.execute(select(User.credits).where(User.id == user_id))
    balance = result.scalar_one()
    if balance < amount:
        return False
    await session.execute(
        update(User).where(User.id == user_id).values(credits=User.credits - amount)
    )
    await session.commit()
    return True


async def count_users(session: AsyncSession) -> int:
    from sqlalchemy import func
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.tg_id).where(User.is_banned == False))
    return list(result.scalars().all())


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
    reference_file_id: str | None,
    reference_url: str | None = None,
) -> ImageSession:
    await archive_active_image_sessions(session, user_id)

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


async def count_generations_today(session: AsyncSession) -> int:
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
    credits: int,
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
    result = await session.execute(
        select(Transaction).where(Transaction.external_id == external_id)
    )
    tx = result.scalar_one_or_none()
    if not tx or tx.status == TransactionStatus.paid:
        return None
    await session.execute(
        update(Transaction)
        .where(Transaction.id == tx.id)
        .values(status=TransactionStatus.paid)
    )
    await session.commit()
    return tx


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
    credits: int,
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
        select(ModelCost).where(ModelCost.is_active == True)
    )
    return list(result.scalars().all())


async def get_model_cost(session: AsyncSession, model_key: str) -> ModelCost | None:
    result = await session.execute(
        select(ModelCost).where(ModelCost.model_key == model_key)
    )
    return result.scalar_one_or_none()


async def set_model_cost(session: AsyncSession, model_key: str, credits: int) -> bool:
    result = await session.execute(
        update(ModelCost)
        .where(ModelCost.model_key == model_key)
        .values(credits=credits)
        .returning(ModelCost.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None

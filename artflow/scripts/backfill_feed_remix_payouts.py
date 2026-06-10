from __future__ import annotations

import asyncio
from collections import defaultdict

from sqlalchemy import select

from db.models import FeedRemixPayout, Generation, GenerationStatus
from db.repository import credit_feed_remix_payout
from db.session import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Generation)
            .where(
                Generation.status == GenerationStatus.done,
                Generation.source_feed_gen_id.is_not(None),
                Generation.credits_spent > 0,
            )
            .order_by(Generation.id.asc())
        )
        generations = list(result.scalars().all())

        existing_result = await session.execute(select(FeedRemixPayout.generation_id))
        existing_ids = set(existing_result.scalars().all())

        added = 0
        amount_total = 0.0
        by_user: dict[int, float] = defaultdict(float)

        for gen in generations:
            if gen.id in existing_ids:
                continue
            source = await session.get(Generation, gen.source_feed_gen_id)
            if not source or source.user_id == gen.user_id:
                continue
            amount = await credit_feed_remix_payout(
                session,
                generation=gen,
                source_generation=source,
            )
            if amount <= 0:
                continue
            added += 1
            amount_total += amount
            by_user[source.user_id] += amount
            existing_ids.add(gen.id)

        print({
            'added_payouts': added,
            'amount_total_rub': round(amount_total, 2),
            'users_credited': len(by_user),
            'top_users': sorted(((user_id, round(amount, 2)) for user_id, amount in by_user.items()), key=lambda item: item[1], reverse=True)[:10],
        })


if __name__ == '__main__':
    asyncio.run(main())

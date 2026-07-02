#!/usr/bin/env python3
"""Fix stuck T-Bank pending transactions by checking their status at T-Bank."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select, update
from db.models import Transaction, TransactionStatus, User
from db.session import AsyncSessionLocal
from payments.tbank import get_payment_state


async def main() -> int:
    fixed = 0
    errors = 0
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.provider == 'tbank',
                    Transaction.status == TransactionStatus.pending,
                    Transaction.external_id.is_not(None),
                )
                .order_by(Transaction.created_at.desc())
                .limit(50)
            )
        ).scalars().all()

        print(f"Found {len(rows)} pending T-Bank transactions")

        for tx in rows:
            print(f"\n{'='*60}")
            print(f"Tx #{tx.id} | user={tx.user_id} | {tx.amount_rub}₽/{tx.credits}💋 | {tx.created_at}")
            print(f"External ID: {tx.external_id}")
            try:
                state = await get_payment_state(str(tx.external_id))
                status = str(state.get("Status", "")).upper()
                success = state.get("Success")
                print(f"T-Bank response: Status={status} Success={success}")

                if status == "CONFIRMED" and success:
                    # Mark as paid and add credits
                    tx.status = TransactionStatus.paid
                    user = await session.get(User, tx.user_id)
                    if user:
                        user.credits = float(user.credits or 0) + float(tx.credits)
                        await session.commit()
                        print(f"✅ FIXED! Credited {tx.credits}💋 to user {tx.user_id}")
                        fixed += 1
                        fixed_details.append({
                            "tx_id": tx.id,
                            "user_id": tx.user_id,
                            "amount_rub": tx.amount_rub,
                            "credits": tx.credits,
                            "external_id": tx.external_id,
                        })
                    else:
                        print(f"❌ User {tx.user_id} not found!")
                        await session.rollback()
                elif status in ("CANCELED", "CANCELLED", "REJECTED", "DEADLINE_EXPIRED", "AUTH_FAIL"):
                    tx.status = TransactionStatus.failed
                    await session.commit()
                    print(f"⏭ Marked as failed (status={status})")
                else:
                    print(f"⏳ Still pending at T-Bank (status={status})")

            except Exception as e:
                errors += 1
                print(f"❌ Error checking tx #{tx.id}: {e}")
                await session.rollback()

    print(f"\n{'='*60}")
    print(f"Done: fixed={fixed} errors={errors}")
    if fixed_details:
        print(f"\nFixed details: {json.dumps(fixed_details, ensure_ascii=False, indent=2)}")
    return 0


if __name__ == "__main__":
    fixed_details = []
    raise SystemExit(asyncio.run(main()))
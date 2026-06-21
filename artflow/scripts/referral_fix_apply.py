import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from core.config import settings
from db.models import Transaction, TransactionStatus, User
from db.session import AsyncSessionLocal

ART_DIR = Path('/root/lena/lena_bot/artflow')
BACKUP_DIR = ART_DIR / 'backups' / 'referral_audit'

@dataclass
class UserChange:
    user_id: int
    tg_id: int
    username: str | None
    old_referrer_id: int | None
    old_referrer_l2_id: int | None
    old_referrer_l3_id: int | None
    new_referrer_id: int | None
    new_referrer_l2_id: int | None
    new_referrer_l3_id: int | None
    old_balance: float
    new_balance: float
    delta_balance: float


def canonical_chain(user_id: int, by_id: dict[int, User]) -> list[int | None]:
    chain: list[int] = []
    seen = {user_id}
    cur = by_id[user_id].referrer_id
    while cur and cur in by_id and cur not in seen and len(chain) < 3:
        chain.append(cur)
        seen.add(cur)
        cur = by_id[cur].referrer_id
    while len(chain) < 3:
        chain.append(None)
    return chain[:3]


async def collect_changes():
    async with AsyncSessionLocal() as session:
        users = list((await session.execute(select(User))).scalars().all())
        paid_txs = list((await session.execute(select(Transaction).where(Transaction.status == TransactionStatus.paid))).scalars().all())
        by_id = {u.id: u for u in users}
        canonical_balances = defaultdict(float)
        for tx in paid_txs:
            u = by_id.get(tx.user_id)
            if not u:
                continue
            amount = float(tx.amount_rub or 0)
            l1, l2, l3 = canonical_chain(u.id, by_id)
            for ref_id, pct in [(l1, float(settings.REFERRAL_COMMISSION_L1)), (l2, float(settings.REFERRAL_COMMISSION_L2)), (l3, float(settings.REFERRAL_COMMISSION_L3))]:
                if ref_id and pct > 0:
                    canonical_balances[ref_id] += round(amount * pct, 2)

        changes: list[UserChange] = []
        for u in users:
            l1, l2, l3 = canonical_chain(u.id, by_id)
            new_balance = round(canonical_balances.get(u.id, 0.0), 2)
            old_balance = round(float(u.referral_balance or 0.0), 2)
            if (u.referrer_id, u.referrer_l2_id, u.referrer_l3_id) != (l1, l2, l3) or old_balance != new_balance:
                changes.append(UserChange(
                    user_id=u.id,
                    tg_id=u.tg_id,
                    username=u.username,
                    old_referrer_id=u.referrer_id,
                    old_referrer_l2_id=u.referrer_l2_id,
                    old_referrer_l3_id=u.referrer_l3_id,
                    new_referrer_id=l1,
                    new_referrer_l2_id=l2,
                    new_referrer_l3_id=l3,
                    old_balance=old_balance,
                    new_balance=new_balance,
                    delta_balance=round(new_balance - old_balance, 2),
                ))
        return changes


async def apply_changes(changes: list[UserChange], label: str):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    snapshot_path = BACKUP_DIR / f'referral_fix_snapshot_{label}_{ts}.json'
    report_path = BACKUP_DIR / f'referral_fix_report_{label}_{ts}.json'
    snapshot_path.write_text(json.dumps([asdict(c) for c in changes], ensure_ascii=False, indent=2))

    async with AsyncSessionLocal() as session:
        for c in changes:
            u = await session.get(User, c.user_id, with_for_update=True)
            if not u:
                continue
            u.referrer_id = c.new_referrer_id
            u.referrer_l2_id = c.new_referrer_l2_id
            u.referrer_l3_id = c.new_referrer_l3_id
            u.referral_balance = c.new_balance
        await session.commit()

    summary = {
        'label': label,
        'applied_at': datetime.now().isoformat(),
        'changed_rows': len(changes),
        'balance_changed_rows': sum(1 for c in changes if c.old_balance != c.new_balance),
        'total_positive_delta': round(sum(c.delta_balance for c in changes if c.delta_balance > 0), 2),
        'total_negative_delta': round(sum(c.delta_balance for c in changes if c.delta_balance < 0), 2),
        'snapshot_path': str(snapshot_path),
    }
    report_path.write_text(json.dumps({'summary': summary, 'top_deltas': [asdict(c) for c in sorted(changes, key=lambda x: abs(x.delta_balance), reverse=True)[:100]]}, ensure_ascii=False, indent=2))
    print(json.dumps({'summary': summary, 'report_path': str(report_path)}, ensure_ascii=False))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--label', default='manual')
    args = parser.parse_args()

    changes = await collect_changes()
    summary = {
        'changed_rows': len(changes),
        'balance_changed_rows': sum(1 for c in changes if c.old_balance != c.new_balance),
        'top_deltas': [asdict(c) for c in sorted(changes, key=lambda x: abs(x.delta_balance), reverse=True)[:20]],
    }
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    await apply_changes(changes, args.label)


if __name__ == '__main__':
    asyncio.run(main())

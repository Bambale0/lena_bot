import asyncio
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from db.models import User
from db.session import AsyncSessionLocal

SNAP = Path('/root/lena/lena_bot/artflow/backups/referral_audit') / f'root_cycle_break_snapshot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

async def main():
    async with AsyncSessionLocal() as session:
        users = list((await session.execute(select(User).where(User.id.in_([1, 162])))).scalars().all())
        snap = []
        for u in users:
            snap.append({
                'id': u.id,
                'tg_id': u.tg_id,
                'referrer_id': u.referrer_id,
                'referrer_l2_id': u.referrer_l2_id,
                'referrer_l3_id': u.referrer_l3_id,
                'referral_balance': float(u.referral_balance or 0),
            })
            if u.id == 1:
                u.referrer_id = None
                u.referrer_l2_id = None
                u.referrer_l3_id = None
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2))
        await session.commit()
        print(json.dumps({'snapshot': str(SNAP), 'updated_user_id': 1}, ensure_ascii=False))

asyncio.run(main())

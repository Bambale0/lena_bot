import argparse
import asyncio
import json
from pathlib import Path

from db.models import User
from db.session import AsyncSessionLocal


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot')
    args = parser.parse_args()
    rows = json.loads(Path(args.snapshot).read_text())
    async with AsyncSessionLocal() as session:
        for row in rows:
            u = await session.get(User, row['user_id'], with_for_update=True)
            if not u:
                continue
            u.referrer_id = row['old_referrer_id']
            u.referrer_l2_id = row['old_referrer_l2_id']
            u.referrer_l3_id = row['old_referrer_l3_id']
            u.referral_balance = row['old_balance']
        await session.commit()
    print(json.dumps({'rolled_back_rows': len(rows), 'snapshot': args.snapshot}, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())

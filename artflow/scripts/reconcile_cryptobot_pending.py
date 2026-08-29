import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, Transaction, TransactionStatus
from db.referral_reward_policy import install_referral_reward_policy
from db.session import AsyncSessionLocal

install_referral_reward_policy(repo)

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger('reconcile_cryptobot_pending')

MAX_CHECK = 100
LOOKBACK_HOURS = 72


async def main() -> int:
    if not settings.CRYPTOBOT_TOKEN:
        logger.error('CRYPTOBOT_TOKEN is not configured')
        return 2

    since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.provider == PaymentProvider.cryptobot,
                    Transaction.status == TransactionStatus.pending,
                    Transaction.external_id.is_not(None),
                    Transaction.created_at >= since,
                )
                .order_by(Transaction.created_at.desc())
                .limit(MAX_CHECK)
            )
        ).scalars().all()

    if not rows:
        logger.info('No pending CryptoBot transactions found')
        return 0

    confirmed: list[dict] = []
    checked = 0
    headers = {'Crypto-Pay-API-Token': settings.CRYPTOBOT_TOKEN}
    async with httpx.AsyncClient(base_url=settings.CRYPTOBOT_BASE_URL, headers=headers, timeout=20) as client:
        for tx in rows:
            checked += 1
            try:
                response = await client.get('/getInvoices', params={'invoice_ids': str(tx.external_id)})
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                logger.warning('CryptoBot API check failed external_id=%s err=%s', tx.external_id, exc)
                continue

            items = (payload.get('result') or {}).get('items') or []
            if not items:
                logger.info('Invoice not found in CryptoBot external_id=%s', tx.external_id)
                continue

            item = items[0]
            status = str(item.get('status') or '').lower()
            if status != 'paid':
                logger.info('Invoice still not paid external_id=%s status=%s', tx.external_id, status or 'unknown')
                continue

            async with AsyncSessionLocal() as session:
                ok = await repo.confirm_transaction_and_add_credits(
                    session,
                    str(tx.external_id),
                    note='Payment reconciled via CryptoBot API auto-catchup',
                )
                if ok:
                    confirmed.append({
                        'tx_id': tx.id,
                        'external_id': str(tx.external_id),
                        'user_id': tx.user_id,
                        'credits': float(tx.credits or 0),
                        'amount_rub': float(tx.amount_rub or 0),
                        'paid_at': item.get('paid_at'),
                    })
                    logger.info('Confirmed pending CryptoBot payment tx_id=%s external_id=%s user_id=%s credits=%s', tx.id, tx.external_id, tx.user_id, tx.credits)

    logger.info('Done checked=%s confirmed=%s', checked, len(confirmed))
    print(json.dumps({'checked': checked, 'confirmed': confirmed}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

"""Change the audited Kling 4 rollout policy from a trusted operator shell."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings
from core.kling4_access import set_kling4_access

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def run(*, audience: str, operator_identity: str) -> int:
    async with AsyncSessionLocal() as session:
        applied = await set_kling4_access(
            session,
            audience,
            source="ops",
            operator_identity=operator_identity,
        )
    print(f"Kling 4 access policy: {applied}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audience", choices=("admin", "public", "disabled"))
    parser.add_argument(
        "--operator",
        required=True,
        help="Stable personal operator handle recorded in the immutable audit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(
        asyncio.run(run(audience=args.audience, operator_identity=args.operator))
    )

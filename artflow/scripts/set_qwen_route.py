"""Change an audited Qwen provider route from a trusted operator shell."""

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
from core.qwen_routing import set_qwen_route

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def run(
    *, mode: str, primary: str, backup: str | None, operator_identity: str
) -> int:
    async with AsyncSessionLocal() as session:
        route = await set_qwen_route(
            session,
            mode,
            primary,
            backup,
            admin_tg_id=None,
            source="ops",
            operator_identity=operator_identity,
        )
    backup_label = route.backup_provider or "none"
    print(f"Qwen {route.mode} route: {route.primary_provider} -> {backup_label}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("text", "image", "video"))
    parser.add_argument("primary", choices=("neironych", "kie"))
    parser.add_argument("backup", choices=("neironych", "kie", "none"))
    parser.add_argument(
        "--operator",
        required=True,
        help="Stable personal operator handle recorded in the immutable audit",
    )
    args = parser.parse_args()
    if args.backup == "none":
        args.backup = None
    return args


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                mode=args.mode,
                primary=args.primary,
                backup=args.backup,
                operator_identity=args.operator,
            )
        )
    )

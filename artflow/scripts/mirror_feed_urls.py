#!/usr/bin/env python3
"""
Backfill: download/mirror all public feed generation result_urls to local storage.

This ensures feed images are never lost when external provider URLs expire.
Run with --apply to actually perform the mirroring and update DB records.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, update

from api.public_files import mirror_url, public_url_is_available
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror all public feed generation result URLs to local storage."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually download URLs and update DB records.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process N most recent feed generations (0 = all).",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                Generation.id,
                Generation.result_url,
                Generation.result_urls,
            )
            .where(
                Generation.is_public_feed.is_(True),
                Generation.gen_type.in_((GenerationType.image, GenerationType.video)),
                Generation.status == GenerationStatus.done,
                Generation.result_url.is_not(None),
            )
            .order_by(Generation.id.desc())
        )
        if args.limit > 0:
            stmt = stmt.limit(args.limit)
        rows = (await session.execute(stmt)).all()

    total = len(rows)
    print(f"Found {total} public feed generations.")

    mirrored_count = 0
    skipped_count = 0
    failed_count = 0
    already_local = 0

    for idx, (gen_id, result_url, result_urls_raw) in enumerate(rows, 1):
        print(f"[{idx}/{total}] Generation {gen_id}: {result_url}", end="", flush=True)

        # Parse result_urls
        original_urls: list[str] = [result_url]
        if result_urls_raw:
            try:
                parsed = json.loads(result_urls_raw)
                if isinstance(parsed, list):
                    original_urls = [str(u) for u in parsed if u]
            except (json.JSONDecodeError, TypeError):
                pass

        # Check if already local
        all_local = all(
            url and public_url_is_available(url)
            for url in original_urls
        )
        if all_local:
            already_local += 1
            print(" ✓ already local")
            continue

        if not args.apply:
            print(" [dry-run] needs mirroring")
            skipped_count += 1
            continue

        # Mirror each URL
        new_urls: list[str] = []
        all_ok = True
        for url in original_urls:
            if not url:
                continue
            mirrored = await mirror_url(url)
            if mirrored:
                new_urls.append(mirrored)
            else:
                print(f" FAILED {url}")
                all_ok = False
                new_urls.append(url)

        if not all_ok:
            failed_count += 1
            continue

        # Update DB if the first URL changed
        if new_urls and new_urls[0] != original_urls[0]:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Generation)
                    .where(Generation.id == gen_id)
                    .values(
                        result_url=new_urls[0],
                        result_urls=json.dumps(new_urls, ensure_ascii=False),
                    )
                )
                await session.commit()
            mirrored_count += 1
            print(f" → {new_urls[0]}")
        else:
            already_local += 1
            print(" ✓ already local")

    print("\n── Summary ──")
    print(f"Total feed generations:   {total}")
    print(f"Already local:            {already_local}")
    print(f"Mirrored (DB updated):    {mirrored_count}")
    print(f"Dry-run skipped:          {skipped_count}")
    print(f"Failed:                   {failed_count}")

    if not args.apply:
        print("\nRun with --apply to perform mirroring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
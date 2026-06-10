#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, update

from db.models import Generation
from db.session import AsyncSessionLocal


UPLOAD_DIR = REPO_ROOT / "static" / "upload"


@dataclass
class FeedGenerationInfo:
    id: int
    created_at: datetime | None
    result_url: str | None
    result_urls_raw: str | None


def _parse_result_urls(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, list):
        return [str(x) for x in data if x]
    return []


def _upload_path_from_url(url: str | None) -> Path | None:
    if not url:
        return None
    marker = "/static/upload/"
    if marker not in url:
        return None
    name = url.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0].strip("/")
    if not name or "/" in name or name.startswith("."):
        return None
    return UPLOAD_DIR / name


def _generation_files(gen: FeedGenerationInfo) -> set[Path]:
    paths: set[Path] = set()
    urls = []
    if gen.result_url:
        urls.append(gen.result_url)
    urls.extend(_parse_result_urls(gen.result_urls_raw))
    for url in urls:
        path = _upload_path_from_url(url)
        if not path:
            continue
        paths.add(path)
        paths.update(path.parent.glob(f"{path.stem}_preview_*.webp"))
    return paths


async def _load_public_feed_generations() -> list[FeedGenerationInfo]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    Generation.id,
                    Generation.created_at,
                    Generation.result_url,
                    Generation.result_urls,
                )
                .where(Generation.is_public_feed.is_(True))
                .order_by(Generation.created_at.desc(), Generation.id.desc())
            )
        ).all()
    return [FeedGenerationInfo(*row) for row in rows]


async def _load_other_generation_file_refs(excluded_ids: set[int]) -> set[Path]:
    refs: set[Path] = set()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Generation.id, Generation.result_url, Generation.result_urls)
                .where(Generation.id.not_in(excluded_ids) if excluded_ids else True)
            )
        ).all()
    for _gid, result_url, result_urls_raw in rows:
        for url in [result_url, *_parse_result_urls(result_urls_raw)]:
            path = _upload_path_from_url(url)
            if path:
                refs.add(path)
    return refs


async def main() -> int:
    parser = argparse.ArgumentParser(description="Trim ArtFlow public feed to a safe fixed size.")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--buffer", type=int, default=20, help="Extra newest public posts to keep as a safety buffer.")
    parser.add_argument("--min-age-hours", type=int, default=24)
    parser.add_argument("--apply", action="store_true", help="Actually unpublish old feed items and delete orphaned files.")
    args = parser.parse_args()

    public_feed = await _load_public_feed_generations()
    keep_count = max(args.limit, 0) + max(args.buffer, 0)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(args.min_age_hours, 0))

    keep = public_feed[:keep_count]
    candidates = [
        gen for gen in public_feed[keep_count:]
        if gen.created_at is None or gen.created_at <= cutoff
    ]

    keep_files: set[Path] = set()
    for gen in keep:
        keep_files.update(_generation_files(gen))

    candidate_files_by_gen: dict[int, set[Path]] = {}
    candidate_ids = {gen.id for gen in candidates}
    other_refs = await _load_other_generation_file_refs(candidate_ids)

    reclaimable_files: set[Path] = set()
    reclaimable_bytes = 0
    skipped_refs: dict[int, list[Path]] = defaultdict(list)

    for gen in candidates:
        files = _generation_files(gen)
        safe_files: set[Path] = set()
        for path in files:
            if path in keep_files:
                skipped_refs[gen.id].append(path)
                continue
            # main asset must not be referenced by any other generation
            referenced_elsewhere = False
            if "_preview_" in path.stem:
                base_stem = path.stem.split("_preview_", 1)[0]
                for candidate_main in path.parent.glob(base_stem + ".*"):
                    if candidate_main == path or "_preview_" in candidate_main.stem:
                        continue
                    if candidate_main in other_refs:
                        referenced_elsewhere = True
                        break
            elif path in other_refs:
                referenced_elsewhere = True
            if referenced_elsewhere:
                skipped_refs[gen.id].append(path)
                continue
            safe_files.add(path)
        candidate_files_by_gen[gen.id] = safe_files
        for path in safe_files:
            if path.exists() and path.is_file() and path not in reclaimable_files:
                reclaimable_files.add(path)
                reclaimable_bytes += path.stat().st_size

    print(f"public_feed_total={len(public_feed)}")
    print(f"keep_count={keep_count}")
    print(f"candidates={len(candidates)}")
    print(f"reclaimable_files={len(reclaimable_files)}")
    print(f"reclaimable_mb={reclaimable_bytes / 1024 / 1024:.1f}")
    if candidates:
        oldest = candidates[-1]
        newest = candidates[0]
        print(f"candidate_window={oldest.created_at}..{newest.created_at}")
    for gen in candidates[:10]:
        file_count = len(candidate_files_by_gen.get(gen.id, set()))
        print(f"candidate_gen id={gen.id} created_at={gen.created_at} files={file_count}")

    if not args.apply:
        print("mode=dry-run")
        return 0

    async with AsyncSessionLocal() as session:
        if candidate_ids:
            await session.execute(
                update(Generation)
                .where(Generation.id.in_(candidate_ids), Generation.is_public_feed.is_(True))
                .values(is_public_feed=False)
            )
            await session.commit()

    removed_files = 0
    removed_bytes = 0
    for path in sorted(reclaimable_files):
        if path.exists() and path.is_file():
            size = path.stat().st_size
            path.unlink()
            removed_files += 1
            removed_bytes += size

    print(f"mode=apply")
    print(f"removed_generations={len(candidate_ids)}")
    print(f"removed_files={removed_files}")
    print(f"removed_mb={removed_bytes / 1024 / 1024:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Generation


def candidate_task_ids(raw: str | int | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []

    candidates: list[str] = []

    def add(item: str | None) -> None:
        clean = str(item or "").strip()
        if clean and clean not in candidates:
            candidates.append(clean)

    add(value)
    base = value[len("web:") :] if value.startswith("web:") else value
    if base.startswith("img_"):
        add(base[4:])
    else:
        add(f"img_{base}")

    base_candidates = list(candidates)
    for item in base_candidates:
        clean = item[len("web:") :] if item.startswith("web:") else item
        add(f"web:{clean}")
    return candidates


def parse_input_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def generation_aliases(generation: Generation | Any) -> list[str]:
    payload = parse_input_params(getattr(generation, "input_params", None))
    values: list[str] = []
    for item in [payload.get("public_task_id"), *(payload.get("task_id_aliases") or [])]:
        clean = str(item or "").strip()
        if clean and clean not in values:
            values.append(clean)
    task_id = str(getattr(generation, "task_id", "") or "").strip()
    if task_id and task_id not in values:
        values.append(task_id)
    return values


async def get_repeat_task_by_any_id(session: AsyncSession, raw_task_id: str | int | None) -> Generation | None:
    candidates = candidate_task_ids(raw_task_id)
    if not candidates:
        return None

    # Exact provider/local task id is the strongest match.
    result = await session.execute(
        select(Generation)
        .where(Generation.task_id.in_(candidates))
        .order_by(desc(Generation.id))
        .limit(1)
    )
    exact = result.scalar_one_or_none()
    if exact is not None:
        return exact

    # Numeric DB id is supported directly, including img_<numeric-id> compatibility.
    numeric_candidates: list[int] = []
    for value in candidates:
        clean = value.removeprefix("web:").removeprefix("img_")
        if clean.isdigit():
            numeric = int(clean)
            if numeric > 0 and numeric not in numeric_candidates:
                numeric_candidates.append(numeric)
    if numeric_candidates:
        result = await session.execute(
            select(Generation)
            .where(Generation.id.in_(numeric_candidates))
            .order_by(desc(Generation.id))
            .limit(1)
        )
        numeric_match = result.scalar_one_or_none()
        if numeric_match is not None:
            return numeric_match

    # JSON operators differ across SQLite/Postgres deployments. LIKE is an
    # intentional compatibility fallback; validate the parsed aliases afterwards
    # whenever possible so a substring match cannot silently select another task.
    for candidate in candidates:
        result = await session.execute(
            select(Generation)
            .where(Generation.input_params.like(f"%{candidate}%"))
            .order_by(desc(Generation.id))
            .limit(8)
        )
        for generation in result.scalars().all():
            aliases = generation_aliases(generation)
            if candidate in aliases or str(raw_task_id or "").strip() in aliases:
                return generation

    # Last-resort legacy recovery: preserve the requested LIKE semantics for old
    # snapshots that embedded ids without task_id_aliases.
    raw = str(raw_task_id or "").strip()
    if raw:
        result = await session.execute(
            select(Generation)
            .where(Generation.input_params.like(f"%{raw}%"))
            .order_by(desc(Generation.id))
            .limit(1)
        )
        return result.scalar_one_or_none()
    return None


async def find_repeat_by_confirm_key(
    session: AsyncSession,
    *,
    user_id: int,
    confirm_key: str | None,
) -> Generation | None:
    key = str(confirm_key or "").strip()
    if not key:
        return None
    marker = json.dumps({"repeat_confirm_key": key}, ensure_ascii=False, separators=(",", ":"))[1:-1]
    result = await session.execute(
        select(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.input_params.like(f"%{marker}%"),
        )
        .order_by(desc(Generation.id))
        .limit(1)
    )
    return result.scalar_one_or_none()

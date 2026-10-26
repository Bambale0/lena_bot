from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from db.models import PromptStatus, TrendCategory, UserPrompt

MAX_CATEGORY_CURSOR_LENGTH = 512
MAX_CATEGORY_PAGE_SIZE = 24
MAX_FOLDER_PAGE_SIZE = 48
MAX_PREVIEW_ITEMS = 5


@dataclass(slots=True)
class TrendCategoryShelf:
    category: TrendCategory
    trend_count: int
    previews: list[UserPrompt]


@dataclass(slots=True)
class TrendCategoryShelfPage:
    items: list[TrendCategoryShelf]
    has_more: bool
    next_cursor: str | None


@dataclass(slots=True)
class TrendCategoryItemsPage:
    category: TrendCategory
    items: list[UserPrompt]
    has_more: bool
    next_cursor: str | None


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> dict[str, Any]:
    if not value or len(value) > MAX_CATEGORY_CURSOR_LENGTH:
        raise ValueError("Invalid cursor")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid cursor") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid cursor")
    return payload


def encode_category_cursor(sort_order: int, category_id: int) -> str:
    return _encode_cursor({"i": int(category_id), "o": int(sort_order), "v": 1})


def decode_category_cursor(value: str) -> tuple[int, int]:
    payload = _decode_cursor(value)
    if set(payload) != {"i", "o", "v"} or payload.get("v") != 1:
        raise ValueError("Invalid category cursor")
    order = payload.get("o")
    category_id = payload.get("i")
    if type(order) is not int or type(category_id) is not int or order < 0 or category_id < 1:
        raise ValueError("Invalid category cursor")
    return order, category_id


def encode_trend_cursor(created_at: datetime, prompt_id: int) -> str:
    timestamp = created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    timestamp = timestamp.astimezone(UTC)
    return _encode_cursor({"i": int(prompt_id), "t": timestamp.isoformat(), "v": 1})


def decode_trend_cursor(value: str) -> tuple[datetime, int]:
    payload = _decode_cursor(value)
    if set(payload) != {"i", "t", "v"} or payload.get("v") != 1:
        raise ValueError("Invalid trend cursor")
    prompt_id = payload.get("i")
    timestamp = payload.get("t")
    if type(prompt_id) is not int or prompt_id < 1 or not isinstance(timestamp, str):
        raise ValueError("Invalid trend cursor")
    try:
        created_at = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid trend cursor") from exc
    if created_at.tzinfo is None:
        raise ValueError("Invalid trend cursor")
    return created_at.astimezone(UTC), prompt_id


def _public_prompt_filters():
    return (
        UserPrompt.status == PromptStatus.approved,
        UserPrompt.is_public.is_(True),
        UserPrompt.trend_category_id.is_not(None),
        UserPrompt.tags.any("trend"),
    )


async def get_public_category_shelves(
    session: AsyncSession,
    *,
    limit: int,
    cursor: str | None,
    preview_limit: int = MAX_PREVIEW_ITEMS,
) -> TrendCategoryShelfPage:
    if not 1 <= limit <= MAX_CATEGORY_PAGE_SIZE:
        raise ValueError("Category limit is out of range")
    if not 1 <= preview_limit <= MAX_PREVIEW_ITEMS:
        raise ValueError("Preview limit is out of range")

    counts = (
        select(
            UserPrompt.trend_category_id.label("category_id"),
            func.count(UserPrompt.id).label("trend_count"),
        )
        .where(*_public_prompt_filters())
        .group_by(UserPrompt.trend_category_id)
        .subquery()
    )
    statement = (
        select(TrendCategory, counts.c.trend_count)
        .join(counts, counts.c.category_id == TrendCategory.id)
        .where(TrendCategory.is_visible.is_(True))
        .order_by(TrendCategory.sort_order, TrendCategory.id)
        .limit(limit + 1)
    )
    if cursor:
        sort_order, category_id = decode_category_cursor(cursor)
        statement = statement.where(
            or_(
                TrendCategory.sort_order > sort_order,
                and_(
                    TrendCategory.sort_order == sort_order,
                    TrendCategory.id > category_id,
                ),
            )
        )

    rows = list((await session.execute(statement)).all())
    has_more = len(rows) > limit
    selected = rows[:limit]
    category_ids = [int(category.id) for category, _count in selected]
    previews_by_category: dict[int, list[UserPrompt]] = {item: [] for item in category_ids}

    if category_ids:
        ranked = (
            select(
                UserPrompt.id.label("prompt_id"),
                UserPrompt.trend_category_id.label("category_id"),
                func.row_number()
                .over(
                    partition_by=UserPrompt.trend_category_id,
                    order_by=(desc(UserPrompt.created_at), desc(UserPrompt.id)),
                )
                .label("preview_rank"),
            )
            .where(*_public_prompt_filters(), UserPrompt.trend_category_id.in_(category_ids))
            .subquery()
        )
        preview_statement = (
            select(UserPrompt, ranked.c.preview_rank)
            .join(ranked, ranked.c.prompt_id == UserPrompt.id)
            .where(ranked.c.preview_rank <= preview_limit)
            .order_by(ranked.c.category_id, ranked.c.preview_rank)
        )
        for prompt, _rank in (await session.execute(preview_statement)).all():
            previews_by_category[int(prompt.trend_category_id)].append(prompt)

    items = [
        TrendCategoryShelf(
            category=category,
            trend_count=int(count),
            previews=previews_by_category[int(category.id)],
        )
        for category, count in selected
    ]
    next_cursor = None
    if has_more and items:
        last = items[-1].category
        next_cursor = encode_category_cursor(int(last.sort_order), int(last.id))
    return TrendCategoryShelfPage(items=items, has_more=has_more, next_cursor=next_cursor)


async def get_public_category_trends(
    session: AsyncSession,
    *,
    key: str,
    limit: int,
    cursor: str | None,
) -> TrendCategoryItemsPage | None:
    if not 1 <= limit <= MAX_FOLDER_PAGE_SIZE:
        raise ValueError("Trend limit is out of range")
    normalized_key = str(key or "").strip().lower()
    if not normalized_key or len(normalized_key) > 32:
        raise ValueError("Invalid category key")

    category_statement = select(TrendCategory).where(
        TrendCategory.key == normalized_key,
        TrendCategory.is_visible.is_(True),
    )
    category_row = (await session.execute(category_statement)).first()
    if category_row is None:
        return None
    category = category_row[0]

    statement = (
        select(UserPrompt)
        .where(
            *_public_prompt_filters(),
            UserPrompt.trend_category_id == category.id,
        )
        .order_by(desc(UserPrompt.created_at), desc(UserPrompt.id))
        .limit(limit + 1)
    )
    if cursor:
        created_at, prompt_id = decode_trend_cursor(cursor)
        statement = statement.where(
            or_(
                UserPrompt.created_at < created_at,
                and_(UserPrompt.created_at == created_at, UserPrompt.id < prompt_id),
            )
        )
    rows = list((await session.execute(statement)).all())
    prompts = [row[0] for row in rows]
    has_more = len(prompts) > limit
    items = prompts[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_trend_cursor(last.created_at, int(last.id))
    return TrendCategoryItemsPage(
        category=category,
        items=items,
        has_more=has_more,
        next_cursor=next_cursor,
    )


async def hydrate_trend_categories(
    session: AsyncSession, prompts: Sequence[UserPrompt]
) -> list[UserPrompt]:
    category_ids = {
        int(prompt.trend_category_id)
        for prompt in prompts
        if getattr(prompt, "trend_category_id", None) is not None
    }
    if not category_ids:
        return list(prompts)
    result = await session.execute(select(TrendCategory).where(TrendCategory.id.in_(category_ids)))
    categories = {int(row[0].id): row[0] for row in result.all()}
    for prompt in prompts:
        category_id = getattr(prompt, "trend_category_id", None)
        attributes.set_committed_value(
            prompt,
            "trend_category_record",
            categories.get(int(category_id)) if category_id is not None else None,
        )
    return list(prompts)

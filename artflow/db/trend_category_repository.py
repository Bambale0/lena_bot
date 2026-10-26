from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import and_, desc, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from core.trends import TREND_CATEGORY_PREFIX, is_trend_prompt, mirror_trend_category_tag
from db.models import (
    PromptStatus,
    TrendCategory,
    TrendCategoryAudit,
    TrendCategoryCatalogState,
    UserPrompt,
)

MAX_CATEGORY_CURSOR_LENGTH = 512
MAX_CATEGORY_PAGE_SIZE = 24
MAX_FOLDER_PAGE_SIZE = 48
MAX_PREVIEW_ITEMS = 5
CATEGORY_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_TREND_CATEGORIES = 100


class TrendCategoryConflict(ValueError):
    def __init__(self, message: str, revision: int):
        super().__init__(message)
        self.revision = int(revision)


class TrendCategoryMutationError(ValueError):
    pass


class TrendCategoryPopulated(TrendCategoryMutationError):
    def __init__(self, count: int):
        super().__init__("Подтвердите скрытие непустой категории")
        self.count = int(count)


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


@dataclass(slots=True)
class TrendCategoryAdminItem:
    category: TrendCategory
    trend_count: int
    published_count: int


@dataclass(slots=True)
class TrendCategoryAdminCatalog:
    items: list[TrendCategoryAdminItem]
    revision: int


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


def encode_trend_cursor(created_at: datetime | None, prompt_id: int) -> str:
    timestamp: str | None = None
    if created_at is not None:
        normalized = created_at
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        timestamp = normalized.astimezone(UTC).isoformat()
    return _encode_cursor({"i": int(prompt_id), "t": timestamp, "v": 1})


def decode_trend_cursor(value: str) -> tuple[datetime | None, int]:
    payload = _decode_cursor(value)
    if set(payload) != {"i", "t", "v"} or payload.get("v") != 1:
        raise ValueError("Invalid trend cursor")
    prompt_id = payload.get("i")
    timestamp = payload.get("t")
    if type(prompt_id) is not int or prompt_id < 1 or not (
        timestamp is None or isinstance(timestamp, str)
    ):
        raise ValueError("Invalid trend cursor")
    if timestamp is None:
        return None, prompt_id
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
        UserPrompt.tags.any("trend"),
    )


def _prompt_matches_category():
    """Resolve both current foreign keys and compatibility-window legacy tags."""
    return or_(
        UserPrompt.trend_category_id == TrendCategory.id,
        and_(
            UserPrompt.trend_category_id.is_(None),
            UserPrompt.tags.any(literal(TREND_CATEGORY_PREFIX) + TrendCategory.key),
        ),
    )


def normalize_category_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    if not CATEGORY_KEY_PATTERN.fullmatch(key):
        raise ValueError("Invalid trend category")
    return key


async def get_existing_trend_category(
    session: AsyncSession, category_key: Any
) -> TrendCategory | None:
    key = normalize_category_key(category_key)
    result = await session.execute(select(TrendCategory).where(TrendCategory.key == key))
    row = result.first()
    return row[0] if row is not None else None


async def require_existing_trend_category(
    session: AsyncSession, category_key: Any
) -> TrendCategory:
    category = await get_existing_trend_category(session, category_key)
    if category is None:
        raise ValueError("Trend category is unavailable")
    return category


def _legacy_category_key(prompt: UserPrompt) -> str | None:
    for item in getattr(prompt, "tags", None) or []:
        tag = str(item or "").strip().lower()
        if tag.startswith("trend-category:"):
            key = tag.removeprefix("trend-category:").strip()
            return key or None
    return None


async def get_visible_trend_category(
    session: AsyncSession,
    category_key: Any,
) -> TrendCategory | None:
    try:
        key = normalize_category_key(category_key)
    except ValueError:
        return None
    result = await session.execute(
        select(TrendCategory).where(
            TrendCategory.key == key,
            TrendCategory.is_visible.is_(True),
        )
    )
    row = result.first()
    return row[0] if row is not None else None


async def list_visible_trend_categories(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[TrendCategory]:
    if not 1 <= limit <= 100:
        raise ValueError("Category limit is out of range")
    result = await session.execute(
        select(TrendCategory)
        .where(TrendCategory.is_visible.is_(True))
        .order_by(TrendCategory.sort_order, TrendCategory.id)
        .limit(limit)
    )
    return [row[0] for row in result.all()]


async def get_visible_trend_category_for_prompt(
    session: AsyncSession,
    prompt: UserPrompt,
    *,
    lock: bool = False,
) -> TrendCategory | None:
    category_id = getattr(prompt, "trend_category_id", None)
    statement = select(TrendCategory).where(TrendCategory.is_visible.is_(True))
    if category_id is not None:
        statement = statement.where(TrendCategory.id == int(category_id))
    else:
        key = _legacy_category_key(prompt)
        if key is None or not CATEGORY_KEY_PATTERN.fullmatch(key):
            return None
        statement = statement.where(TrendCategory.key == key)
    if lock:
        # PostgreSQL FOR SHARE serializes the final admission decision with a
        # concurrent category hide. SQLite ignores this in local unit tests.
        statement = statement.with_for_update(read=True)
    row = (await session.execute(statement)).first()
    if row is None:
        return None
    category = row[0]
    attributes.set_committed_value(prompt, "trend_category_record", category)
    return category


async def public_prompt_library_item_is_visible(
    session: AsyncSession,
    prompt: UserPrompt | None,
    *,
    lock: bool = False,
) -> bool:
    """Keep ordinary prompts public while enforcing the trend category switch."""
    if prompt is None:
        return False
    if not is_trend_prompt(prompt):
        return True
    return await get_visible_trend_category_for_prompt(session, prompt, lock=lock) is not None


async def filter_public_prompt_library_items(
    session: AsyncSession,
    prompts: Sequence[UserPrompt],
) -> list[UserPrompt]:
    """Remove hidden-category trends without changing ordinary prompt ordering."""
    items = list(prompts)
    trends = [prompt for prompt in items if is_trend_prompt(prompt)]
    if not trends:
        return items
    visible_trends = await hydrate_visible_trend_categories(session, trends)
    visible_ids = {int(prompt.id) for prompt in visible_trends}
    return [
        prompt
        for prompt in items
        if not is_trend_prompt(prompt) or int(prompt.id) in visible_ids
    ]


async def get_visible_trends(
    session: AsyncSession,
    *,
    limit: int,
) -> list[UserPrompt]:
    """Return the bounded legacy trend list after category visibility filtering."""
    if not 1 <= limit <= 200:
        raise ValueError("Trend limit is out of range")
    statement = (
        select(UserPrompt, TrendCategory)
        .join(TrendCategory, _prompt_matches_category())
        .where(
            UserPrompt.status == PromptStatus.approved,
            UserPrompt.is_public.is_(True),
            UserPrompt.tags.any("trend"),
            TrendCategory.is_visible.is_(True),
        )
        .order_by(
            desc(UserPrompt.uses_count),
            desc(UserPrompt.likes),
            desc(UserPrompt.created_at),
        )
        .limit(limit)
    )
    rows = list((await session.execute(statement)).all())
    prompts: list[UserPrompt] = []
    for prompt, category in rows:
        attributes.set_committed_value(prompt, "trend_category_record", category)
        prompts.append(prompt)
    return prompts


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
            TrendCategory.id.label("category_id"),
            func.count(UserPrompt.id).label("trend_count"),
        )
        .select_from(TrendCategory)
        .join(UserPrompt, _prompt_matches_category())
        .where(*_public_prompt_filters())
        .group_by(TrendCategory.id)
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
    category_ids_by_key = {str(category.key): int(category.id) for category, _count in selected}

    if category_ids:
        ranked = (
            select(
                UserPrompt.id.label("prompt_id"),
                TrendCategory.id.label("category_id"),
                func.row_number()
                .over(
                    partition_by=TrendCategory.id,
                    order_by=(
                        desc(UserPrompt.created_at).nulls_last(),
                        desc(UserPrompt.id),
                    ),
                )
                .label("preview_rank"),
            )
            .select_from(TrendCategory)
            .join(UserPrompt, _prompt_matches_category())
            .where(*_public_prompt_filters(), TrendCategory.id.in_(category_ids))
            .subquery()
        )
        preview_statement = (
            select(UserPrompt, ranked.c.preview_rank)
            .join(ranked, ranked.c.prompt_id == UserPrompt.id)
            .where(ranked.c.preview_rank <= preview_limit)
            .order_by(ranked.c.category_id, ranked.c.preview_rank)
        )
        for prompt, _rank in (await session.execute(preview_statement)).all():
            category_id = getattr(prompt, "trend_category_id", None)
            if category_id is None:
                category_id = category_ids_by_key.get(_legacy_category_key(prompt) or "")
            if category_id in previews_by_category:
                previews_by_category[int(category_id)].append(prompt)

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
            or_(
                UserPrompt.trend_category_id == category.id,
                and_(
                    UserPrompt.trend_category_id.is_(None),
                    UserPrompt.tags.any(f"{TREND_CATEGORY_PREFIX}{category.key}"),
                ),
            ),
        )
        .order_by(desc(UserPrompt.created_at).nulls_last(), desc(UserPrompt.id))
        .limit(limit + 1)
    )
    if cursor:
        created_at, prompt_id = decode_trend_cursor(cursor)
        if created_at is None:
            statement = statement.where(
                UserPrompt.created_at.is_(None),
                UserPrompt.id < prompt_id,
            )
        else:
            statement = statement.where(
                or_(
                    UserPrompt.created_at < created_at,
                    and_(UserPrompt.created_at == created_at, UserPrompt.id < prompt_id),
                    UserPrompt.created_at.is_(None),
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


async def hydrate_visible_trend_categories(
    session: AsyncSession, prompts: Sequence[UserPrompt]
) -> list[UserPrompt]:
    prompts = list(prompts)
    category_ids = {
        int(prompt.trend_category_id)
        for prompt in prompts
        if getattr(prompt, "trend_category_id", None) is not None
    }
    legacy_keys = {
        key
        for prompt in prompts
        if getattr(prompt, "trend_category_id", None) is None
        for key in [_legacy_category_key(prompt)]
        if key is not None and CATEGORY_KEY_PATTERN.fullmatch(key)
    }
    if not category_ids and not legacy_keys:
        return []
    statement = select(TrendCategory).where(TrendCategory.is_visible.is_(True))
    filters = []
    if category_ids:
        filters.append(TrendCategory.id.in_(category_ids))
    if legacy_keys:
        filters.append(TrendCategory.key.in_(legacy_keys))
    result = await session.execute(statement.where(or_(*filters)))
    categories = [row[0] for row in result.all()]
    by_id = {int(category.id): category for category in categories}
    by_key = {str(category.key): category for category in categories}
    visible: list[UserPrompt] = []
    for prompt in prompts:
        category_id = getattr(prompt, "trend_category_id", None)
        category = (
            by_id.get(int(category_id))
            if category_id is not None
            else by_key.get(_legacy_category_key(prompt) or "")
        )
        if category is None:
            continue
        attributes.set_committed_value(prompt, "trend_category_record", category)
        visible.append(prompt)
    return visible


def _normalized_admin_title(value: Any) -> str:
    title = " ".join(str(value or "").split())
    if not 1 <= len(title) <= 80:
        raise TrendCategoryMutationError("Название категории должно содержать от 1 до 80 символов")
    return title


async def _locked_catalog_state(session: AsyncSession) -> TrendCategoryCatalogState:
    row = (
        await session.execute(
            select(TrendCategoryCatalogState)
            .where(TrendCategoryCatalogState.id == 1)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise TrendCategoryMutationError("Состояние каталога недоступно")
    return row[0]


def _require_catalog_revision(
    state: TrendCategoryCatalogState, expected_revision: int
) -> None:
    if int(state.revision) != int(expected_revision):
        raise TrendCategoryConflict("Каталог уже изменился", int(state.revision))


def _category_state(category: TrendCategory) -> dict[str, Any]:
    return {
        "key": str(category.key),
        "title": str(category.title),
        "sort_order": int(category.sort_order),
        "is_visible": bool(category.is_visible),
    }


def _audit_category_change(
    session: AsyncSession,
    *,
    category: TrendCategory,
    action: str,
    revision: int,
    actor_tg_id: int,
    source: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    target_prompt_id: int | None = None,
) -> None:
    session.add(
        TrendCategoryAudit(
            category_id=int(category.id),
            category_key=str(category.key),
            target_prompt_id=target_prompt_id,
            action=action,
            source=source,
            actor_tg_id=actor_tg_id,
            actor_operator=None,
            catalog_revision=revision,
            before_state=before,
            after_state=after,
        )
    )


async def _all_categories_locked(session: AsyncSession) -> list[TrendCategory]:
    rows = await session.execute(
        select(TrendCategory)
        .order_by(TrendCategory.sort_order, TrendCategory.id)
        .with_for_update()
    )
    return [row[0] for row in rows.all()]


async def get_admin_trend_category_catalog(
    session: AsyncSession,
) -> TrendCategoryAdminCatalog:
    state_row = await session.execute(
        select(TrendCategoryCatalogState).where(TrendCategoryCatalogState.id == 1)
    )
    state = state_row.first()
    if state is None:
        raise TrendCategoryMutationError("Состояние каталога недоступно")
    published = and_(
        UserPrompt.status == PromptStatus.approved,
        UserPrompt.is_public.is_(True),
    )
    rows = await session.execute(
        select(
            TrendCategory,
            func.count(UserPrompt.id).label("trend_count"),
            func.count(UserPrompt.id).filter(published).label("published_count"),
        )
        .outerjoin(
            UserPrompt,
            and_(_prompt_matches_category(), UserPrompt.tags.any("trend")),
        )
        .group_by(TrendCategory.id)
        .order_by(TrendCategory.sort_order, TrendCategory.id)
    )
    return TrendCategoryAdminCatalog(
        items=[
            TrendCategoryAdminItem(
                category=category,
                trend_count=int(trend_count or 0),
                published_count=int(published_count or 0),
            )
            for category, trend_count, published_count in rows.all()
        ],
        revision=int(state[0].revision),
    )


async def create_trend_category(
    session: AsyncSession,
    *,
    title: str,
    expected_revision: int,
    actor_tg_id: int,
    source: str,
) -> tuple[TrendCategory, int]:
    state = await _locked_catalog_state(session)
    _require_catalog_revision(state, expected_revision)
    categories = await _all_categories_locked(session)
    normalized = _normalized_admin_title(title)
    if len(categories) >= MAX_TREND_CATEGORIES:
        raise TrendCategoryMutationError("Достигнут лимит: 100 категорий")
    if any(str(item.title).casefold() == normalized.casefold() for item in categories):
        raise TrendCategoryMutationError("Категория с таким названием уже существует")
    known_keys = {str(item.key) for item in categories}
    key = ""
    for _attempt in range(5):
        candidate = f"cat_{uuid4().hex[:16]}"
        if candidate not in known_keys:
            key = candidate
            break
    if not key:
        raise TrendCategoryMutationError("Не удалось создать уникальный ключ категории")
    category = TrendCategory(
        key=key,
        title=normalized,
        sort_order=len(categories),
        is_visible=True,
    )
    session.add(category)
    await session.flush()
    state.revision = int(state.revision) + 1
    _audit_category_change(
        session,
        category=category,
        action="create",
        revision=int(state.revision),
        actor_tg_id=actor_tg_id,
        source=source,
        before=None,
        after=_category_state(category),
    )
    await session.flush()
    return category, int(state.revision)


async def _category_trend_count(
    session: AsyncSession, category: TrendCategory
) -> int:
    category_match = or_(
        UserPrompt.trend_category_id == category.id,
        and_(
            UserPrompt.trend_category_id.is_(None),
            UserPrompt.tags.any(f"{TREND_CATEGORY_PREFIX}{category.key}"),
        ),
    )
    return int(
        (
            await session.execute(
                select(func.count(UserPrompt.id)).where(
                    UserPrompt.tags.any("trend"), category_match
                )
            )
        ).scalar_one()
        or 0
    )


async def update_trend_category(
    session: AsyncSession,
    *,
    key: str,
    title: str | None,
    is_visible: bool | None,
    confirm_populated: bool,
    expected_revision: int,
    actor_tg_id: int,
    source: str,
) -> tuple[TrendCategory, int]:
    state = await _locked_catalog_state(session)
    _require_catalog_revision(state, expected_revision)
    categories = await _all_categories_locked(session)
    category = next((item for item in categories if str(item.key) == key), None)
    if category is None:
        raise TrendCategoryMutationError("Категория не найдена")
    before = _category_state(category)
    if title is not None:
        normalized = _normalized_admin_title(title)
        if any(
            int(item.id) != int(category.id)
            and str(item.title).casefold() == normalized.casefold()
            for item in categories
        ):
            raise TrendCategoryMutationError("Категория с таким названием уже существует")
        category.title = normalized
    if is_visible is not None and bool(is_visible) != bool(category.is_visible):
        if not is_visible:
            count = await _category_trend_count(session, category)
            if count and not confirm_populated:
                raise TrendCategoryPopulated(count)
        category.is_visible = bool(is_visible)
    after = _category_state(category)
    if before == after:
        return category, int(state.revision)
    state.revision = int(state.revision) + 1
    _audit_category_change(
        session,
        category=category,
        action="update",
        revision=int(state.revision),
        actor_tg_id=actor_tg_id,
        source=source,
        before=before,
        after=after,
    )
    await session.flush()
    return category, int(state.revision)


async def reorder_trend_categories(
    session: AsyncSession,
    *,
    keys: list[str],
    expected_revision: int,
    actor_tg_id: int,
    source: str,
) -> tuple[list[TrendCategory], int]:
    state = await _locked_catalog_state(session)
    _require_catalog_revision(state, expected_revision)
    categories = await _all_categories_locked(session)
    existing = {str(item.key): item for item in categories}
    if len(keys) != len(set(keys)) or set(keys) != set(existing):
        raise TrendCategoryMutationError("Передайте полный список категорий без повторов")
    changed = [
        existing[key]
        for index, key in enumerate(keys)
        if int(existing[key].sort_order) != index
    ]
    if not changed:
        return categories, int(state.revision)
    before = {str(item.key): _category_state(item) for item in categories}
    for index, category in enumerate(categories):
        category.sort_order = -(index + 1)
    await session.flush()
    ordered = [existing[key] for key in keys]
    for index, category in enumerate(ordered):
        category.sort_order = index
    state.revision = int(state.revision) + 1
    for category in ordered:
        old = before[str(category.key)]
        new = _category_state(category)
        if old == new:
            continue
        _audit_category_change(
            session,
            category=category,
            action="reorder",
            revision=int(state.revision),
            actor_tg_id=actor_tg_id,
            source=source,
            before=old,
            after=new,
        )
    await session.flush()
    return ordered, int(state.revision)


async def reassign_trend_prompt(
    session: AsyncSession,
    *,
    prompt_id: int,
    target_key: str,
    expected_revision: int,
    actor_tg_id: int,
    source: str,
) -> tuple[UserPrompt, TrendCategory, int]:
    state = await _locked_catalog_state(session)
    _require_catalog_revision(state, expected_revision)
    category_row = await session.execute(
        select(TrendCategory).where(TrendCategory.key == target_key).with_for_update()
    )
    category_result = category_row.first()
    if category_result is None:
        raise TrendCategoryMutationError("Категория не найдена")
    category = category_result[0]
    prompt_row = await session.execute(
        select(UserPrompt).where(UserPrompt.id == prompt_id).with_for_update()
    )
    prompt_result = prompt_row.first()
    prompt = prompt_result[0] if prompt_result is not None else None
    if not is_trend_prompt(prompt):
        raise TrendCategoryMutationError("Тренд не найден")
    before_key = _legacy_category_key(prompt)
    if getattr(prompt, "trend_category_id", None) is not None:
        old_row = await session.execute(
            select(TrendCategory.key).where(
                TrendCategory.id == int(prompt.trend_category_id)
            )
        )
        before_key = old_row.scalar_one_or_none() or before_key
    if int(getattr(prompt, "trend_category_id", 0) or 0) == int(category.id) and before_key == str(category.key):
        return prompt, category, int(state.revision)
    prompt.trend_category_id = int(category.id)
    prompt.tags = mirror_trend_category_tag(list(prompt.tags or []), str(category.key))
    state.revision = int(state.revision) + 1
    _audit_category_change(
        session,
        category=category,
        action="reassign",
        revision=int(state.revision),
        actor_tg_id=actor_tg_id,
        source=source,
        before={"category_key": before_key},
        after={"category_key": str(category.key)},
        target_prompt_id=int(prompt.id),
    )
    await session.flush()
    return prompt, category, int(state.revision)

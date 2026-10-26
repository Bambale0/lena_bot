"""Add the database-backed trend category catalog and legacy backfill.

Revision ID: 052_trend_categories
Revises: 051_qwen_ops_audit_actor

This is an expand-only compatibility migration. Application rollback keeps the
schema and category evidence in place; a later release may contract legacy tags.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "052_trend_categories"
down_revision = "051_qwen_ops_audit_actor"
branch_labels = None
depends_on = None

DEFAULT_CATEGORY_KEY = "featured"
CATEGORY_SEED: tuple[tuple[str, str], ...] = (
    ("featured", "Тренды"),
    ("photo-video", "Фото → видео"),
    ("portrait", "Портреты"),
    ("cartoon", "Мультфильм"),
    ("animals", "С животными"),
    ("holidays", "Праздники"),
    ("style", "Образы"),
)
TREND_TAG = "trend"
CATEGORY_PREFIX = "trend-category:"
BACKFILL_BATCH_SIZE = 500


def _normalized_tags(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(item).strip().lower() for item in raw if str(item or "").strip()]


def _category_key(tags: list[str]) -> str | None:
    for tag in tags:
        if tag.startswith(CATEGORY_PREFIX):
            value = tag[len(CATEGORY_PREFIX) :].strip()
            if value:
                return value
    return None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _pending_trend_prompts_query(
    prompt_table: sa.Table,
    *,
    after_id: int,
    batch_size: int = BACKFILL_BATCH_SIZE,
) -> sa.Select:
    """Select only pending trend rows and keep migration memory bounded."""

    return (
        sa.select(prompt_table.c.id, prompt_table.c.tags)
        .where(
            prompt_table.c.trend_category_id.is_(None),
            prompt_table.c.id > after_id,
            sa.literal(TREND_TAG) == sa.any_(prompt_table.c.tags),
        )
        .order_by(prompt_table.c.id)
        .limit(batch_size)
    )


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "trend_category_catalog_state" not in tables:
        op.create_table(
            "trend_category_catalog_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint("id = 1", name="ck_trend_category_catalog_state_singleton"),
            sa.CheckConstraint("revision >= 1", name="ck_trend_category_catalog_state_revision"),
        )

    tables = _table_names(bind)
    if "trend_categories" not in tables:
        op.create_table(
            "trend_categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(32), nullable=False),
            sa.Column("title", sa.String(80), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("key", name="uq_trend_categories_key"),
            sa.UniqueConstraint("sort_order", name="uq_trend_categories_sort_order"),
            sa.CheckConstraint(
                "length(key) BETWEEN 1 AND 32", name="ck_trend_categories_key_length"
            ),
            sa.CheckConstraint(
                "length(title) BETWEEN 1 AND 80", name="ck_trend_categories_title_length"
            ),
        )

    category_table = sa.Table("trend_categories", sa.MetaData(), autoload_with=bind)
    for sort_order, (key, title) in enumerate(CATEGORY_SEED):
        existing = bind.execute(
            sa.select(category_table.c.id).where(category_table.c.key == key)
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(
                category_table.insert().values(
                    key=key,
                    title=title,
                    sort_order=sort_order,
                    is_visible=True,
                )
            )

    state_table = sa.Table(
        "trend_category_catalog_state", sa.MetaData(), autoload_with=bind
    )
    if bind.execute(sa.select(state_table.c.id).where(state_table.c.id == 1)).scalar_one_or_none() is None:
        bind.execute(state_table.insert().values(id=1, revision=1))

    prompt_columns = {item["name"] for item in sa.inspect(bind).get_columns("user_prompts")}
    if "trend_category_id" not in prompt_columns:
        op.add_column(
            "user_prompts", sa.Column("trend_category_id", sa.Integer(), nullable=True)
        )
        op.create_foreign_key(
            "fk_user_prompts_trend_category_id",
            "user_prompts",
            "trend_categories",
            ["trend_category_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    index_names = {item["name"] for item in sa.inspect(bind).get_indexes("user_prompts")}
    if "ix_user_prompts_trend_category_public_created_id" not in index_names:
        op.create_index(
            "ix_user_prompts_trend_category_public_created_id",
            "user_prompts",
            ["trend_category_id", "is_public", "created_at", "id"],
            unique=False,
        )

    tables = _table_names(bind)
    if "trend_category_audit" not in tables:
        op.create_table(
            "trend_category_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "category_id",
                sa.Integer(),
                sa.ForeignKey("trend_categories.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("category_key", sa.String(32), nullable=False),
            sa.Column(
                "target_prompt_id",
                sa.Integer(),
                sa.ForeignKey("user_prompts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("actor_tg_id", sa.BigInteger(), nullable=True),
            sa.Column("actor_operator", sa.String(128), nullable=True),
            sa.Column("catalog_revision", sa.Integer(), nullable=False),
            sa.Column("before_state", sa.JSON(), nullable=True),
            sa.Column("after_state", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "length(action) BETWEEN 1 AND 32", name="ck_trend_category_audit_action"
            ),
        )
        op.create_index(
            "ix_trend_category_audit_category_id",
            "trend_category_audit",
            ["category_id"],
            unique=False,
        )
        op.create_index(
            "ix_trend_category_audit_target_prompt_id",
            "trend_category_audit",
            ["target_prompt_id"],
            unique=False,
        )
        op.create_index(
            "ix_trend_category_audit_action",
            "trend_category_audit",
            ["action"],
            unique=False,
        )

    prompt_table = sa.Table("user_prompts", sa.MetaData(), autoload_with=bind)
    audit_table = sa.Table("trend_category_audit", sa.MetaData(), autoload_with=bind)
    category_ids = dict(
        bind.execute(sa.select(category_table.c.key, category_table.c.id)).all()
    )
    fallback_id = category_ids[DEFAULT_CATEGORY_KEY]
    known_keys = set(category_ids)
    after_id = 0
    while True:
        prompts = bind.execute(
            _pending_trend_prompts_query(
                prompt_table,
                after_id=after_id,
                batch_size=BACKFILL_BATCH_SIZE,
            )
        ).all()
        if not prompts:
            break

        prompt_ids_by_key: dict[str, list[int]] = {}
        unresolved: list[tuple[int, str]] = []
        for prompt_id, raw_tags in prompts:
            tags = _normalized_tags(raw_tags)
            legacy_key = _category_key(tags)
            resolved_key = legacy_key if legacy_key in known_keys else DEFAULT_CATEGORY_KEY
            prompt_ids_by_key.setdefault(resolved_key, []).append(int(prompt_id))
            if legacy_key and legacy_key not in known_keys:
                unresolved.append((int(prompt_id), legacy_key))

        for resolved_key, prompt_ids in prompt_ids_by_key.items():
            bind.execute(
                prompt_table.update()
                .where(
                    prompt_table.c.id.in_(prompt_ids),
                    prompt_table.c.trend_category_id.is_(None),
                )
                .values(trend_category_id=category_ids[resolved_key])
            )

        if unresolved:
            unresolved_ids = [prompt_id for prompt_id, _ in unresolved]
            recorded_ids = set(
                bind.execute(
                    sa.select(audit_table.c.target_prompt_id).where(
                        audit_table.c.action == "legacy_unresolved",
                        audit_table.c.target_prompt_id.in_(unresolved_ids),
                    )
                ).scalars()
            )
            audit_rows = [
                {
                    "category_id": fallback_id,
                    "category_key": legacy_key[:32],
                    "target_prompt_id": prompt_id,
                    "action": "legacy_unresolved",
                    "source": "migration",
                    "actor_tg_id": None,
                    "actor_operator": None,
                    "catalog_revision": 1,
                    "before_state": {"legacy_category_key": legacy_key},
                    "after_state": {"assigned_category_key": DEFAULT_CATEGORY_KEY},
                }
                for prompt_id, legacy_key in unresolved
                if prompt_id not in recorded_ids
            ]
            if audit_rows:
                bind.execute(audit_table.insert(), audit_rows)

        after_id = int(prompts[-1][0])


def downgrade() -> None:
    # Expand-only compatibility state and migration evidence must survive an
    # application rollback. Contract legacy tags only in a later release.
    pass

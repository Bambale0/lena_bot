from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from core.trends import DEFAULT_TREND_CATEGORY, TREND_CATEGORIES
from db.models import (
    TrendCategory,
    TrendCategoryAudit,
    TrendCategoryCatalogState,
    UserPrompt,
)


def test_trend_category_migration_is_the_single_expand_only_head() -> None:
    config = Config()
    config.set_main_option("script_location", "db/migrations")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["056_broadcast_delivery"]
    assert scripts.get_revision("054_referral_lineage").down_revision == "053_wan_kie_primary_fallback"
    assert scripts.get_revision("053_wan_kie_primary_fallback").down_revision == "052_trend_categories"
    assert scripts.get_revision("052_trend_categories").down_revision == "051_qwen_ops_audit_actor"


def test_trend_category_models_expose_catalog_relation_and_public_folder_index() -> None:
    assert TrendCategory.__table__.c.key.type.length == 32
    assert TrendCategory.__table__.c.title.type.length == 80
    assert TrendCategoryCatalogState.__table__.c.revision.nullable is False
    assert TrendCategoryAudit.__table__.c.before_state.type.python_type is dict
    assert UserPrompt.__table__.c.trend_category_id.nullable is True
    indexes = {index.name: tuple(column.name for column in index.columns) for index in UserPrompt.__table__.indexes}
    assert indexes["ix_user_prompts_trend_category_public_created_id"] == (
        "trend_category_id",
        "is_public",
        "created_at",
        "id",
    )


def test_pending_backfill_query_is_database_filtered_and_bounded() -> None:
    migration = importlib.import_module("db.migrations.versions.052_trend_categories")
    prompt_table = migration.sa.table(
        "user_prompts",
        migration.sa.column("id", migration.sa.Integer()),
        migration.sa.column("tags", migration.sa.ARRAY(migration.sa.Text())),
        migration.sa.column("trend_category_id", migration.sa.Integer()),
    )
    query = migration._pending_trend_prompts_query(
        prompt_table,
        after_id=41,
        batch_size=500,
    )
    sql = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "'trend' = ANY (user_prompts.tags)" in sql
    assert "user_prompts.trend_category_id IS NULL" in sql
    assert "user_prompts.id > 41" in sql
    assert "ORDER BY user_prompts.id" in sql
    assert "LIMIT 500" in sql


def _exercise_migration(connection) -> None:
    connection.execute(text("CREATE TABLE users (id integer PRIMARY KEY)"))
    connection.execute(
        text(
            "CREATE TABLE user_prompts ("
            "id integer PRIMARY KEY, author_id integer NOT NULL REFERENCES users(id), "
            "title varchar(60) NOT NULL, description varchar(200) NOT NULL, "
            "category varchar(32) NOT NULL, prompt_text text NOT NULL, preview_url text, "
            "model varchar(64), tags text[] NOT NULL, likes integer NOT NULL DEFAULT 0, "
            "is_public boolean NOT NULL DEFAULT true, status varchar(32) NOT NULL, "
            "uses_count integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    connection.execute(text("INSERT INTO users (id) VALUES (1)"))
    connection.execute(
        text(
            "INSERT INTO user_prompts "
            "(id,author_id,title,description,category,prompt_text,tags,status) VALUES "
            "(1,1,'Known','Known','photo','secret',ARRAY['trend','trend-category:animals']::text[],'approved'),"
            "(2,1,'Unknown','Unknown','photo','secret',ARRAY['trend','trend-category:legacy-special']::text[],'approved'),"
            "(3,1,'No category','No category','photo','secret',ARRAY['trend']::text[],'approved'),"
            "(4,1,'Ordinary','Ordinary','photo','secret',ARRAY['not-trend','trend-category:animals']::text[],'approved')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO user_prompts "
            "(id,author_id,title,description,category,prompt_text,tags,status) "
            "SELECT 1000+n,1,'Known batch','Known batch','photo','secret',"
            "ARRAY['trend','trend-category:animals']::text[],'approved' "
            "FROM generate_series(1,1105) AS n"
        )
    )
    connection.execute(
        text(
            "INSERT INTO user_prompts "
            "(id,author_id,title,description,category,prompt_text,tags,status) "
            "SELECT 3000+n,1,'Unknown batch','Unknown batch','photo','secret',"
            "ARRAY['trend','trend-category:legacy-batch']::text[],'approved' "
            "FROM generate_series(1,1105) AS n"
        )
    )

    migration = importlib.import_module("db.migrations.versions.052_trend_categories")
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        migration.upgrade()

    categories = connection.execute(
        text("SELECT key,title,sort_order FROM trend_categories ORDER BY sort_order")
    ).all()
    assert categories == [
        (key, meta["title"], position)
        for position, (key, meta) in enumerate(TREND_CATEGORIES.items())
    ]
    assigned = connection.execute(
        text(
            "SELECT p.id,c.key,p.tags FROM user_prompts p "
            "JOIN trend_categories c ON c.id=p.trend_category_id "
            "WHERE p.id <= 4 ORDER BY p.id"
        )
    ).all()
    assert assigned[0][1] == "animals"
    assert assigned[1][1] == DEFAULT_TREND_CATEGORY
    assert "trend-category:legacy-special" in assigned[1][2]
    assert assigned[2][1] == DEFAULT_TREND_CATEGORY
    assert len(assigned) == 3
    assert connection.execute(
        text("SELECT trend_category_id FROM user_prompts WHERE id=4")
    ).scalar_one() is None
    unresolved = connection.execute(
        text(
            "SELECT action,category_key,target_prompt_id,before_state,after_state "
            "FROM trend_category_audit WHERE action='legacy_unresolved' AND target_prompt_id=2"
        )
    ).one()
    assert unresolved[0:3] == ("legacy_unresolved", "legacy-special", 2)
    assert unresolved[3]["legacy_category_key"] == "legacy-special"
    assert unresolved[4]["assigned_category_key"] == DEFAULT_TREND_CATEGORY
    assert connection.execute(text("SELECT count(*) FROM trend_category_audit")).scalar_one() == 1106
    assert connection.execute(
        text("SELECT count(*) FROM user_prompts WHERE trend_category_id IS NOT NULL")
    ).scalar_one() == 2213
    assert connection.execute(
        text(
            "SELECT count(*) FROM user_prompts WHERE id > 3000 "
            "AND tags @> ARRAY['trend-category:legacy-batch']::text[]"
        )
    ).scalar_one() == 1105
    assert connection.execute(text("SELECT revision FROM trend_category_catalog_state WHERE id=1")).scalar_one() == 1
    assert "ix_user_prompts_trend_category_public_created_id" in {
        item["name"] for item in inspect(connection).get_indexes("user_prompts")
    }


@pytest.mark.asyncio
async def test_trend_category_migration_is_idempotent_on_disposable_postgres() -> None:
    raw_url = os.getenv("APIX_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Disposable PostgreSQL required; configured in backend CI")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "apix_session_migration_test"
        or url.query
    ):
        pytest.fail("APIX_TEST_POSTGRES_URL must target the dedicated loopback test database")
    engine = create_async_engine(url)
    schema = f"trend_categories_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(_exercise_migration)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def test_trend_runtime_model_repair_precedes_the_single_migration_head() -> None:
    config = Config()
    config.set_main_option("script_location", "db/migrations")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["051_qwen_ops_audit_actor"]
    assert (
        scripts.get_revision("051_qwen_ops_audit_actor").down_revision
        == "050_kling4_ops_audit_actor"
    )
    assert (
        scripts.get_revision("050_kling4_ops_audit_actor").down_revision
        == "049_trend_runtime_model_repair"
    )
    assert scripts.get_revision("049_trend_runtime_model_repair").down_revision == "048_wan_routing"


def _exercise(connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE user_prompts (id integer PRIMARY KEY, model varchar(64), tags text[] NOT NULL)"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE trend_run_claims (id integer PRIMARY KEY, trend_id integer NOT NULL, "
            "status varchar(16) NOT NULL, generation_id integer)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO user_prompts VALUES "
            "(70, 'bytedance/seedance-2-5__resolution=720p', "
            "ARRAY['trend','trend-video','trend-duration:10']::text[]), "
            "(71, 'bytedance/seedance-2-5', ARRAY['trend','trend-video']::text[])"
        )
    )
    connection.execute(
        text(
            "INSERT INTO trend_run_claims VALUES "
            "(1, 70, 'running', NULL), (2, 70, 'complete', 100), (3, 71, 'running', NULL)"
        )
    )

    migration = importlib.import_module("db.migrations.versions.049_trend_runtime_model_repair")
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        migration.upgrade()
        migration.upgrade()

    repaired = connection.execute(
        text("SELECT model, tags FROM user_prompts WHERE id = 70")
    ).one()
    assert repaired[0] == "bytedance/seedance-2-5"
    assert repaired[1].count("trend-resolution:720p") == 1
    assert connection.execute(
        text("SELECT id FROM trend_run_claims ORDER BY id")
    ).scalars().all() == [2, 3]


@pytest.mark.asyncio
async def test_trend_runtime_model_repair_on_disposable_postgres() -> None:
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
    schema = f"trend_runtime_model_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(_exercise)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

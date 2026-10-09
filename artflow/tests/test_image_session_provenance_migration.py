"""Exercise the target migration on disposable data, never an app database.

SQLite runs in the ordinary suite. The PostgreSQL round trip additionally runs
when APIX_TEST_POSTGRES_URL names a loopback PostgreSQL database whose exact
name is apix_session_migration_test. It creates a unique transactional schema
and rolls everything back, without changing public schema or reading app data.
CI must provide that dedicated PostgreSQL service; a skipped test is not proof
that PostgreSQL migration verification has passed.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/versions/038_image_session_prompt_provenance.py"


def _migration():
    spec = importlib.util.spec_from_file_location("session_provenance_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _roundtrip(connection):
    old_rows = [
        {"id": 1, "base_prompt": "synthetic-legacy-foreign-secret", "last_prompt": "synthetic-last-secret"},
        {"id": 2, "base_prompt": "synthetic-legacy-own-but-unproven", "last_prompt": None},
    ]
    table = sa.Table(
        "image_sessions", sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("base_prompt", sa.Text),
        sa.Column("last_prompt", sa.Text),
    )
    table.create(connection)
    connection.execute(table.insert(), old_rows)
    module = _migration()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        module.upgrade()
    column = next(
        item for item in sa.inspect(connection).get_columns("image_sessions")
        if item["name"] == "prompt_provenance"
    )
    assert column["nullable"] is True
    assert column["default"] is None
    assert column["type"].length == 32
    assert connection.execute(sa.text(
        "SELECT id, base_prompt, last_prompt, prompt_provenance FROM image_sessions ORDER BY id"
    )).mappings().all() == [dict(row, prompt_provenance=None) for row in old_rows]
    connection.execute(sa.text(
        "INSERT INTO image_sessions (id, base_prompt, last_prompt, prompt_provenance) "
        "VALUES (3, 'synthetic-new-own', 'synthetic-new-own', 'user_supplied')"
    ))
    with Operations.context(context):
        module.downgrade()
    assert "prompt_provenance" not in {
        item["name"] for item in sa.inspect(connection).get_columns("image_sessions")
    }
    assert connection.execute(sa.select(table).order_by(table.c.id)).mappings().all() == [
        *old_rows,
        {"id": 3, "base_prompt": "synthetic-new-own", "last_prompt": "synthetic-new-own"},
    ]
    # Re-upgrade still does not backfill even the previously trusted row.
    with Operations.context(context):
        module.upgrade()
    assert connection.execute(sa.text(
        "SELECT prompt_provenance FROM image_sessions ORDER BY id"
    )).scalars().all() == [None, None, None]


def test_provenance_migration_extends_verified_037_without_branching():
    config = Config()
    config.set_main_option("script_location", str(ROOT / "db/migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert len(scripts.get_heads()) == 1
    assert "038_image_session_provenance" in {
        migration.revision for migration in scripts.walk_revisions()
    }
    assert scripts.get_revision("038_image_session_provenance").down_revision == "037_provider_routing_settings"


def test_sqlite_provenance_migration_preserves_history_without_default_or_backfill():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            _roundtrip(connection)
    finally:
        engine.dispose()


async def test_postgres_provenance_migration_upgrade_downgrade_roundtrip():
    raw_url = os.getenv("APIX_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Dedicated loopback PostgreSQL test service is not configured")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "apix_session_migration_test"
        or url.query
    ):
        pytest.fail("APIX_TEST_POSTGRES_URL must target the dedicated loopback test database")
    engine = create_async_engine(url)
    schema = f"session_provenance_test_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(_roundtrip)
            finally:
                # PostgreSQL transactional DDL removes the entire temporary
                # schema on rollback, even if a migration assertion fails.
                await transaction.rollback()
    finally:
        await engine.dispose()

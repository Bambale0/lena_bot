"""Verify both routing constraints on a disposable PostgreSQL schema."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]


def load_migration(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "db/migrations/versions" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_postgres_seedream_routing_and_audit_accept_kie_after_upgrade():
    raw = os.getenv("APIX_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Dedicated PostgreSQL required; mandatory in backend CI")
    url = make_url(raw)
    assert url.host in {"localhost", "127.0.0.1", "::1"} and url.database == "apix_session_migration_test"
    engine = create_async_engine(url)
    schema = "seedream_routing_" + uuid4().hex
    old = load_migration("037_provider_routing_settings.py")
    new = load_migration("057_seedream_provider_routing.py")
    def setup(conn):
        with Operations.context(MigrationContext.configure(conn)):
            old.upgrade()
            new.upgrade()
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                await conn.run_sync(setup)
                await conn.execute(sa.text("INSERT INTO provider_routing_settings(model_key,primary_provider) VALUES ('nano-banana-2.1','nexus'),('seedream-5.0-pro','neironych')"))
                await conn.execute(sa.text("UPDATE provider_routing_settings SET primary_provider='kie' WHERE model_key='seedream-5.0-pro'"))
                await conn.execute(sa.text("INSERT INTO provider_routing_audit(model_key,previous_provider,new_provider,changed_by_admin_tg_id,source) VALUES ('seedream-5.0-pro','neironych','kie',42,'web')"))
                assert (await conn.execute(sa.text("SELECT primary_provider FROM provider_routing_settings WHERE model_key='seedream-5.0-pro'"))).scalar_one() == "kie"
                assert (await conn.execute(sa.text("SELECT primary_provider FROM provider_routing_settings WHERE model_key='nano-banana-2.1'"))).scalar_one() == "nexus"
                # Unknown values remain rejected, atomically, on both tables.
                for sql in [
                    "UPDATE provider_routing_settings SET primary_provider='unknown' WHERE model_key='seedream-5.0-pro'",
                    "UPDATE provider_routing_audit SET new_provider='unknown'",
                ]:
                    nested = await conn.begin_nested()
                    with pytest.raises(sa.exc.IntegrityError):
                        await conn.execute(sa.text(sql))
                    await nested.rollback()
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

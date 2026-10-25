"""Verify the photo-1 policy rollout on disposable PostgreSQL data."""
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

from core.feed_recipe_identity_policy import validate_instruction
from core.feed_remix_prompt import build_feed_image_recipe_prompt

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/versions/041_feed_photo1_identity_default.py"


def _migration():
    spec = importlib.util.spec_from_file_location("feed_photo1_policy_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_photo1_policy_migration_is_current_and_valid():
    config = Config()
    config.set_main_option("script_location", str(ROOT / "db/migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["050_kling4_ops_audit_actor"]
    assert (
        scripts.get_revision("050_kling4_ops_audit_actor").down_revision
        == "049_trend_runtime_model_repair"
    )
    assert scripts.get_revision("049_trend_runtime_model_repair").down_revision == "048_wan_routing"
    assert scripts.get_revision("048_wan_routing").down_revision == "047_kling4_preview"
    assert scripts.get_revision("047_kling4_preview").down_revision == "046_tribute_catalog"
    assert scripts.get_revision("044_trend_run_claims").down_revision == "043_wan30_pricing"
    assert scripts.get_revision("043_wan30_pricing").down_revision == "042_qwen_routing"
    assert scripts.get_revision("042_qwen_routing").down_revision == "041_feed_photo1_identity_default"
    assert scripts.get_revision("041_feed_photo1_identity_default").down_revision == "040_feed_recipe_identity_policy"
    instruction = _migration().DEFAULT_INSTRUCTION
    assert validate_instruction(instruction) == instruction
    assert "Photo 1" in instruction and "Additional user photos" in instruction
    assert "reader's requested changes to clothing, pose, styling, hair color and other non-facial details" in instruction
    assert "take priority over both the creator prompt and photos" in instruction
    assert "conflicting description of facial identity" in instruction


def test_photo1_default_keeps_explicit_reader_edits():
    instruction = _migration().DEFAULT_INSTRUCTION
    change = "blue coat, standing pose and blonde hair"
    composed = build_feed_image_recipe_prompt(
        "A person in a red coat, sitting, with dark hair.",
        change,
        identity_instruction=instruction,
    )
    assert composed.index(change) < composed.index("Фото 1 — лицо")
    assert "reader's requested changes to clothing, pose, styling, hair color and other non-facial details" in composed
    assert "take priority over both the creator prompt and photos" in composed


def _exercise_migration(connection):
    policy = sa.Table(
        "feed_recipe_identity_policy", sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instruction", sa.Text, nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    audit = sa.Table(
        "feed_recipe_identity_policy_audit", sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("previous_instruction", sa.Text, nullable=False),
        sa.Column("new_instruction", sa.Text, nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
    )
    policy.create(connection)
    audit.create(connection)
    previous = "Old seed: use supplied photos for the person's facial identity."
    connection.execute(policy.insert().values(id=1, instruction=previous))
    migration = _migration()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        migration.upgrade()
        migration.upgrade()
    assert connection.execute(sa.select(policy.c.instruction)).scalar_one() == migration.DEFAULT_INSTRUCTION
    rows = connection.execute(sa.select(
        audit.c.previous_instruction, audit.c.new_instruction, audit.c.changed_by_admin_tg_id,
    )).one()
    assert rows == (previous, migration.DEFAULT_INSTRUCTION, 0)
    assert connection.execute(sa.select(sa.func.count()).select_from(audit)).scalar_one() == 1

    # An administrator's later change remains authoritative on re-upgrade.
    custom = "Admin selected a separate facial identity instruction with sufficient length for policy validation."
    connection.execute(policy.update().values(instruction=custom, updated_by_admin_tg_id=42))
    with Operations.context(context):
        migration.upgrade()
    assert connection.execute(sa.select(policy.c.instruction)).scalar_one() == custom
    assert connection.execute(sa.select(sa.func.count()).select_from(audit)).scalar_one() == 1


async def test_photo1_policy_migration_preserves_admin_edits_in_postgres():
    raw_url = os.getenv("APIX_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Dedicated loopback PostgreSQL test service is not configured")
    url = make_url(raw_url)
    if (url.drivername != "postgresql+asyncpg"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or url.database != "apix_session_migration_test" or url.query):
        pytest.fail("APIX_TEST_POSTGRES_URL must target the dedicated loopback test database")
    engine = create_async_engine(url)
    schema = f"photo1_policy_test_{uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.run_sync(_exercise_migration)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

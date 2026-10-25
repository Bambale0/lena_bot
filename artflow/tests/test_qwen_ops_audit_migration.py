import importlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_qwen_ops_actor_migration_preserves_admin_audit_and_enforces_actor_shape():
    migration = importlib.import_module(
        "db.migrations.versions.051_qwen_ops_audit_actor"
    )
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    old_audit = sa.Table(
        "qwen_routing_audit",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("previous_primary_provider", sa.String(16), nullable=False),
        sa.Column("previous_backup_provider", sa.String(16), nullable=True),
        sa.Column("new_primary_provider", sa.String(16), nullable=False),
        sa.Column("new_backup_provider", sa.String(16), nullable=True),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            old_audit.insert().values(
                id=1,
                mode="image",
                previous_primary_provider="neironych",
                previous_backup_provider="kie",
                new_primary_provider="kie",
                new_backup_provider="neironych",
                changed_by_admin_tg_id=123,
                source="web",
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        upgraded = sa.Table(
            "qwen_routing_audit",
            sa.MetaData(),
            autoload_with=connection,
        )
        preserved = connection.execute(sa.select(upgraded)).mappings().one()
        assert preserved["changed_by_admin_tg_id"] == 123
        assert preserved["changed_by_operator"] is None
        assert upgraded.c.changed_by_admin_tg_id.nullable is True

        connection.execute(
            upgraded.insert().values(
                id=2,
                mode="image",
                previous_primary_provider="neironych",
                previous_backup_provider="kie",
                new_primary_provider="kie",
                new_backup_provider="neironych",
                changed_by_admin_tg_id=None,
                changed_by_operator="codex-for-Bambale0-20261025",
                source="ops",
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                upgraded.insert().values(
                    id=3,
                    mode="image",
                    previous_primary_provider="neironych",
                    previous_backup_provider="kie",
                    new_primary_provider="kie",
                    new_backup_provider="neironych",
                    changed_by_admin_tg_id=123,
                    changed_by_operator="fake-ops",
                    source="ops",
                )
            )


def test_qwen_ops_actor_migration_refuses_a_version_only_downgrade():
    migration = importlib.import_module(
        "db.migrations.versions.051_qwen_ops_audit_actor"
    )

    with pytest.raises(RuntimeError, match="immutable release evidence"):
        migration.downgrade()

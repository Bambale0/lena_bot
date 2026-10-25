import importlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_kling4_ops_actor_migration_preserves_admin_audit_and_enforces_actor_shape():
    migration = importlib.import_module(
        "db.migrations.versions.050_kling4_ops_audit_actor"
    )
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    old_audit = sa.Table(
        "kling4_access_audit",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("previous_audience", sa.String(16), nullable=False),
        sa.Column("new_audience", sa.String(16), nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            old_audit.insert().values(
                id=1,
                previous_audience="admin",
                new_audience="public",
                changed_by_admin_tg_id=123,
                source="bot",
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        upgraded = sa.Table(
            "kling4_access_audit",
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
                previous_audience="admin",
                new_audience="public",
                changed_by_admin_tg_id=None,
                changed_by_operator="root@release-container",
                source="ops",
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                upgraded.insert().values(
                    id=3,
                    previous_audience="admin",
                    new_audience="public",
                    changed_by_admin_tg_id=123,
                    changed_by_operator="root@release-container",
                    source="ops",
                )
            )

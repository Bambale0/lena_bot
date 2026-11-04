"""Allow audited KIE routing for Seedream 5 Pro without changing existing rows."""
import sqlalchemy as sa
from alembic import op

revision = "057_seedream_routing"
down_revision = "056_broadcast_delivery"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    ("provider_routing_settings", "ck_provider_routing_provider", "primary_provider"),
    ("provider_routing_audit", "ck_provider_routing_audit_new_provider", "new_provider"),
)


def upgrade() -> None:
    for table, name, column in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ('neironych','nexus','kie')")


def downgrade() -> None:
    # Never delete or rewrite immutable routing history to force a downgrade.
    bind = op.get_bind()
    for table, _, column in _CONSTRAINTS:
        if bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {column}='kie' LIMIT 1")).first():
            raise RuntimeError("KIE routing history requires migration 057; downgrade would invalidate data")
    for table, name, column in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ('neironych','nexus')")

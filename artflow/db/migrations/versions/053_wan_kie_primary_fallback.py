"""Allow audited KIE-primary / Neironych-fallback Wan routing.

Revision ID: 053_wan_kie_primary_fallback
Revises: 052_trend_categories

The change only expands the accepted policy values. Existing route rows and
their revisions remain unchanged until an authenticated administrator saves a
new policy through the control plane.
"""

from alembic import op

revision = "053_wan_kie_primary_fallback"
down_revision = "052_trend_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_wan_route_policy", "wan_routing_settings", type_="check"
    )
    op.create_check_constraint(
        "ck_wan_route_policy",
        "wan_routing_settings",
        "policy IN ('neironych_kie','kie_neironych','neironych_only','kie_only')",
    )


def downgrade() -> None:
    # Expand-only: a rollback of application code must not invalidate an
    # already audited kie_neironych row. A later migration may contract it.
    pass

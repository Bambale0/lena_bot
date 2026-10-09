"""Record trusted provenance only for newly audited image-session prompts.

Revision ID: 038_image_session_provenance
Revises: 037_provider_routing_settings

Historical rows deliberately remain NULL. Neither upgrade nor downgrade
rewrites saved prompts or infers ownership from missing generation lineage.
"""
import sqlalchemy as sa
from alembic import op

revision = "038_image_session_provenance"
down_revision = "037_provider_routing_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_sessions",
        sa.Column("prompt_provenance", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("image_sessions", "prompt_provenance")

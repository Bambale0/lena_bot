"""Reject a second unlinked trend claim for the same user across devices.

Revision ID: 059_trend_single_unlinked_actor
Revises: 058_feed_remix_claims
"""
import sqlalchemy as sa
from alembic import op

revision = "059_trend_single_unlinked_actor"
down_revision = "058_feed_remix_claims"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_trend_run_claim_single_unlinked_user"


def upgrade() -> None:
    # Fail safely rather than deleting or altering existing paid evidence.
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM ("
            " SELECT user_id FROM trend_run_claims"
            " WHERE generation_id IS NULL GROUP BY user_id HAVING count(*) > 1"
            ") conflicting_actors"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError("Unlinked trend claims need manual review before admission hardening")
    op.create_index(
        INDEX_NAME, "trend_run_claims", ["user_id"], unique=True,
        postgresql_where=sa.text("generation_id IS NULL"),
        sqlite_where=sa.text("generation_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="trend_run_claims")

"""Repair trend pricing keys stored as provider runtime model ids.

Revision ID: 049_trend_runtime_model_repair
Revises: 048_wan_routing
"""

from alembic import op

revision = "049_trend_runtime_model_repair"
down_revision = "048_wan_routing"
branch_labels = None
depends_on = None

LEGACY_MODEL = "bytedance/seedance-2-5__resolution=720p"
RUNTIME_MODEL = "bytedance/seedance-2-5"
RESOLUTION_TAG = "trend-resolution:720p"


def upgrade() -> None:
    # These claims were created before any provider submission. Leaving them in
    # place permanently turns a corrected retry into a 409 response.
    op.execute(
        f"""
        DELETE FROM trend_run_claims AS claim
        USING user_prompts AS prompt
        WHERE claim.trend_id = prompt.id
          AND prompt.model = '{LEGACY_MODEL}'
          AND prompt.tags @> ARRAY['trend']::text[]
          AND claim.status = 'running'
          AND claim.generation_id IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE user_prompts
        SET model = '{RUNTIME_MODEL}',
            tags = CASE
                WHEN tags @> ARRAY['{RESOLUTION_TAG}']::text[] THEN tags
                ELSE array_append(tags, '{RESOLUTION_TAG}')
            END
        WHERE model = '{LEGACY_MODEL}'
          AND tags @> ARRAY['trend']::text[]
        """
    )


def downgrade() -> None:
    # This is a forward data repair. Reintroducing provider-invalid model ids or
    # resurrecting stale admission claims would make rollback less safe.
    pass

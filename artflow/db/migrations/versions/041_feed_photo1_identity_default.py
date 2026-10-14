"""Use the first reader photo as the default facial identity anchor.

Revision ID: 041_feed_photo1_identity_default
Revises: 040_feed_recipe_identity_policy
"""
import sqlalchemy as sa
from alembic import op

revision = "041_feed_photo1_identity_default"
down_revision = "040_feed_recipe_identity_policy"
branch_labels = None
depends_on = None

DEFAULT_INSTRUCTION = (
    "Photo 1 is the first attached user image and the sole source of the subject's facial identity. "
    "Match its face shape, eyes, brows, nose, lips, jawline, skin tone, hairline and distinctive details. "
    "If Photo 1 is a collage, use its clearest frontal face and do not reproduce the collage. "
    "Additional user photos may clarify this same person but must not change the identity chosen from Photo 1. "
    "Use the creator prompt for scene, pose, clothing and lighting unless the reader explicitly "
    "requests a change. The reader's requested changes to clothing, pose, styling, hair color "
    "and other non-facial details take priority over both the creator prompt and photos. "
    "Photo 1 takes priority over any conflicting description of facial identity. "
    "Do not blend in another face."
)


def upgrade() -> None:
    # The existing admin editor owns intentional changes. Migrate only the
    # untouched seed; one statement updates the row and records its old value.
    literal = DEFAULT_INSTRUCTION.replace("'", "''")
    op.execute(sa.text(f"""
        WITH previous AS (
            SELECT instruction FROM feed_recipe_identity_policy
            WHERE id = 1 AND updated_by_admin_tg_id IS NULL
              AND instruction <> '{literal}'
            FOR UPDATE
        ), changed AS (
            UPDATE feed_recipe_identity_policy AS policy
            SET instruction = '{literal}', updated_at = now()
            FROM previous
            WHERE policy.id = 1
            RETURNING previous.instruction AS old_instruction, policy.instruction AS new_instruction
        )
        INSERT INTO feed_recipe_identity_policy_audit
            (previous_instruction, new_instruction, changed_by_admin_tg_id)
        SELECT old_instruction, new_instruction, 0 FROM changed
    """))


def downgrade() -> None:
    # An audited policy edit is user configuration. Previous app versions do
    # not read this row, so keep its value and history on code rollback.
    pass

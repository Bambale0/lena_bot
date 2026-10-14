"""Add audited, editable face identity instruction for feed image recipes.

Revision ID: 040_feed_recipe_identity_policy
Revises: 039_image_recovery_policy
"""
import sqlalchemy as sa
from alembic import op

revision = "040_feed_recipe_identity_policy"
down_revision = "039_image_recovery_policy"
branch_labels = None
depends_on = None

DEFAULT_INSTRUCTION = (
    "The supplied reference photos are the EXCLUSIVE source of the subject's face and identity. "
    "If they show multiple views or a collage, use the clearest frontal face as the identity anchor "
    "and other views to confirm the same person's features; do not output the collage layout. "
    "Preserve face shape, eyes, eyebrows, nose, lips, jawline, skin tone, hairline, hair texture, "
    "hair color and distinctive facial details. Apply the creator recipe to the scene, clothing, "
    "pose, lighting and artistic style, but the reader's reference takes priority over conflicting "
    "appearance or color descriptions, including a monochrome scene instruction. The reader's "
    "explicit appearance changes take priority where requested. Do not copy the creator's face, "
    "invent a different face, blend identities or output a collage."
)


def upgrade() -> None:
    op.create_table(
        "feed_recipe_identity_policy",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instruction", sa.Text, nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_feed_recipe_identity_policy_singleton"),
        sa.CheckConstraint("length(instruction) BETWEEN 100 AND 3000", name="ck_feed_recipe_identity_instruction_length"),
    )
    op.create_table(
        "feed_recipe_identity_policy_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("previous_instruction", sa.Text, nullable=False),
        sa.Column("new_instruction", sa.Text, nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    policy = sa.table(
        "feed_recipe_identity_policy", sa.column("id", sa.Integer), sa.column("instruction", sa.Text),
    )
    op.bulk_insert(policy, [{"id": 1, "instruction": DEFAULT_INSTRUCTION}])


def downgrade() -> None:
    op.drop_table("feed_recipe_identity_policy_audit")
    op.drop_table("feed_recipe_identity_policy")

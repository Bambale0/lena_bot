"""Kling 4 admin preview, durable intents and admin-editable tariff matrix.
Revision ID: 047_kling4_preview
Revises: 046_tribute_catalog
"""

import sqlalchemy as sa
from alembic import op

revision = "047_kling4_preview"
down_revision = "046_tribute_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kling4_access_policy",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("updated_by_admin_tg_id", sa.BigInteger, nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "id = 1 AND audience IN ('admin','public','disabled')", name="ck_kling4_policy"
        ),
    )
    op.create_table(
        "kling4_access_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("previous_audience", sa.String(16), nullable=False),
        sa.Column("new_audience", sa.String(16), nullable=False),
        sa.Column("changed_by_admin_tg_id", sa.BigInteger, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "kling4_intents",
        sa.Column("intent_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "generation_id",
            sa.Integer,
            sa.ForeignKey("generations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    bind = op.get_bind()
    bind.execute(sa.text("INSERT INTO kling4_access_policy (id,audience) VALUES (1,'admin')"))
    table = sa.Table("model_costs", sa.MetaData(), autoload_with=bind)
    for route, label in [("reference", "Референсы"), ("keyframe", "Ключевые кадры")]:
        model = f"kling-4.0/{route}-to-video"
        entries = [(model, f"🎬 Kling 4 · {label}", 28.5)]
        for resolution, no_video, video in [("720p", 28.5, 17.0), ("1080p", 42.5, 25.5)]:
            entries.append(
                (
                    f"{model}__resolution={resolution}",
                    f"Kling 4 · {label} · {resolution} · за сек",
                    no_video,
                )
            )
            if route == "reference":
                entries.append(
                    (
                        f"{model}__resolution={resolution}__video_input=true",
                        f"Kling 4 · {resolution} · видеовход · за сек",
                        video,
                    )
                )
        for key, title, rate in entries:
            if (
                bind.execute(
                    sa.select(table.c.id).where(table.c.model_key == key)
                ).scalar_one_or_none()
                is None
            ):
                bind.execute(
                    table.insert().values(
                        model_key=key,
                        display_name=title,
                        gen_type="video",
                        credits=rate,
                        is_active=True,
                    )
                )


def downgrade():
    # Financial intents and rollout audit must survive an application rollback.
    pass

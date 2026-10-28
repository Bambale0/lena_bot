"""Make referral lineage immutable and add auditable repair records.

Revision ID: 054_referral_lineage_immutability
Revises: 053_wan_kie_primary_fallback
"""

import sqlalchemy as sa
from alembic import op

revision = "054_referral_lineage_immutability"
down_revision = "053_wan_kie_primary_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_lineage_repair_batches",
        sa.Column("batch_key", sa.String(64), primary_key=True),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("invalid_edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_commission_rub", sa.Float(), nullable=False, server_default="0"),
        sa.Column("balance_debit_rub", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unrecovered_rub", sa.Float(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('applying', 'applied')", name="ck_referral_lineage_repair_status"
        ),
    )
    op.create_table(
        "referral_lineage_repair_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_key",
            sa.String(64),
            sa.ForeignKey("referral_lineage_repair_batches.batch_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("old_referrer_id", sa.Integer()),
        sa.Column("old_referrer_l2_id", sa.Integer()),
        sa.Column("old_referrer_l3_id", sa.Integer()),
        sa.Column("new_referrer_id", sa.Integer()),
        sa.Column("new_referrer_l2_id", sa.Integer()),
        sa.Column("new_referrer_l3_id", sa.Integer()),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("batch_key", "user_id", name="uq_referral_lineage_repair_batch_user"),
    )
    op.create_index(
        "ix_referral_lineage_repair_rows_user_id",
        "referral_lineage_repair_rows",
        ["user_id"],
    )
    op.create_table(
        "referral_finance_repair_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_key",
            sa.String(64),
            sa.ForeignKey("referral_lineage_repair_batches.batch_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=False),
        sa.Column("balance_debit_rub", sa.Float(), nullable=False),
        sa.Column("unrecovered_rub", sa.Float(), nullable=False),
        sa.Column(
            "reversal_ledger_id",
            sa.Integer(),
            sa.ForeignKey("referral_commission_ledger.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "batch_key",
            "transaction_id",
            "recipient_user_id",
            "level",
            name="uq_referral_finance_repair_batch_event",
        ),
    )
    op.create_index(
        "ix_referral_finance_repair_rows_recipient",
        "referral_finance_repair_rows",
        ["recipient_user_id"],
    )

    # PostgreSQL enforces the invariant below every application code path. A repair
    # is allowed only while an auditable batch is in the same transaction's
    # `applying` state.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_referral_lineage_immutability()
            RETURNS trigger AS $$
            DECLARE
                repair_batch text;
            BEGIN
                IF NEW.referrer_id IS NOT DISTINCT FROM OLD.referrer_id
                   AND NEW.referrer_l2_id IS NOT DISTINCT FROM OLD.referrer_l2_id
                   AND NEW.referrer_l3_id IS NOT DISTINCT FROM OLD.referrer_l3_id THEN
                    RETURN NEW;
                END IF;

                repair_batch := current_setting('apix.referral_repair_batch', true);
                IF repair_batch IS NULL OR NOT EXISTS (
                    SELECT 1
                    FROM referral_lineage_repair_batches b
                    JOIN referral_lineage_repair_rows r
                      ON r.batch_key = b.batch_key AND r.user_id = OLD.id
                    WHERE b.batch_key = repair_batch
                      AND b.status = 'applying'
                      AND r.old_referrer_id IS NOT DISTINCT FROM OLD.referrer_id
                      AND r.old_referrer_l2_id IS NOT DISTINCT FROM OLD.referrer_l2_id
                      AND r.old_referrer_l3_id IS NOT DISTINCT FROM OLD.referrer_l3_id
                      AND r.new_referrer_id IS NOT DISTINCT FROM NEW.referrer_id
                      AND r.new_referrer_l2_id IS NOT DISTINCT FROM NEW.referrer_l2_id
                      AND r.new_referrer_l3_id IS NOT DISTINCT FROM NEW.referrer_l3_id
                ) THEN
                    RAISE EXCEPTION 'referral lineage is immutable after user creation';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_users_referral_lineage_immutable
            BEFORE UPDATE OF referrer_id, referrer_l2_id, referrer_l3_id ON users
            FOR EACH ROW EXECUTE FUNCTION enforce_referral_lineage_immutability()
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_referral_repair_row_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'referral repair evidence is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table_name in (
            "referral_lineage_repair_rows",
            "referral_finance_repair_rows",
        ):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION prevent_referral_repair_row_mutation()
                """
            )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_referral_repair_batch_finalization()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'UPDATE'
                   AND OLD.status = 'applying'
                   AND NEW.status = 'applied'
                   AND current_setting('apix.referral_repair_batch', true) = OLD.batch_key
                   AND NEW.batch_key = OLD.batch_key
                   AND NEW.operator = OLD.operator
                   AND NEW.reason = OLD.reason
                   AND NEW.created_at = OLD.created_at THEN
                    IF NEW.invalid_edge_count <> OLD.invalid_edge_count
                       OR NEW.changed_user_count <> OLD.changed_user_count
                       OR NEW.invalid_commission_rub <> OLD.invalid_commission_rub
                       OR NEW.balance_debit_rub < 0
                       OR NEW.unrecovered_rub < 0
                       OR NEW.summary_json IS NULL
                       OR NEW.applied_at IS NULL THEN
                        RAISE EXCEPTION 'invalid referral repair batch finalization';
                    END IF;
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'referral repair batch evidence is immutable';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_referral_lineage_repair_batches_immutable
            BEFORE UPDATE OR DELETE ON referral_lineage_repair_batches
            FOR EACH ROW EXECUTE FUNCTION enforce_referral_repair_batch_finalization()
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM referral_lineage_repair_batches)")
    ).scalar():
        raise RuntimeError(
            "Cannot downgrade after a referral repair: retain immutable audit evidence"
        )
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_users_referral_lineage_immutable ON users")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_referral_lineage_repair_batches_immutable "
            "ON referral_lineage_repair_batches"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_referral_lineage_repair_rows_append_only "
            "ON referral_lineage_repair_rows"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_referral_finance_repair_rows_append_only "
            "ON referral_finance_repair_rows"
        )
        op.execute("DROP FUNCTION IF EXISTS enforce_referral_lineage_immutability()")
        op.execute("DROP FUNCTION IF EXISTS enforce_referral_repair_batch_finalization()")
        op.execute("DROP FUNCTION IF EXISTS prevent_referral_repair_row_mutation()")
    op.drop_index(
        "ix_referral_finance_repair_rows_recipient", table_name="referral_finance_repair_rows"
    )
    op.drop_table("referral_finance_repair_rows")
    op.drop_index(
        "ix_referral_lineage_repair_rows_user_id", table_name="referral_lineage_repair_rows"
    )
    op.drop_table("referral_lineage_repair_rows")
    op.drop_table("referral_lineage_repair_batches")

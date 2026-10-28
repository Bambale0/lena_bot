"""Add immutable audit evidence for invalid referral credit reversals.

Revision ID: 055_referral_credit
Revises: 054_referral_lineage
"""

import sqlalchemy as sa
from alembic import op

revision = "055_referral_credit"
down_revision = "054_referral_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column_name in (
        "invalid_credit_credits",
        "balance_debit_credits",
        "unrecovered_credits",
    ):
        op.add_column(
            "referral_lineage_repair_batches",
            sa.Column(column_name, sa.Float(), nullable=False, server_default="0"),
        )

    op.create_table(
        "referral_credit_repair_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_key",
            sa.String(64),
            sa.ForeignKey("referral_lineage_repair_batches.batch_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "original_ledger_id",
            sa.Integer(),
            sa.ForeignKey("credit_ledger.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("amount_credits", sa.Float(), nullable=False),
        sa.Column("balance_debit_credits", sa.Float(), nullable=False),
        sa.Column("unrecovered_credits", sa.Float(), nullable=False),
        sa.Column(
            "reversal_ledger_id",
            sa.Integer(),
            sa.ForeignKey("credit_ledger.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "batch_key",
            "original_ledger_id",
            name="uq_referral_credit_repair_batch_ledger",
        ),
        sa.CheckConstraint(
            "amount_credits > 0",
            name="ck_referral_credit_repair_positive_amount",
        ),
        sa.CheckConstraint(
            "balance_debit_credits >= 0 AND unrecovered_credits >= 0",
            name="ck_referral_credit_repair_nonnegative_allocation",
        ),
        sa.CheckConstraint(
            "abs(amount_credits - balance_debit_credits - unrecovered_credits) <= 0.000001",
            name="ck_referral_credit_repair_allocation_total",
        ),
    )
    op.create_index(
        "ix_referral_credit_repair_rows_user",
        "referral_credit_repair_rows",
        ["user_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_referral_repair_row_insert()
            RETURNS trigger AS $$
            BEGIN
                IF current_setting('apix.referral_repair_batch', true) IS DISTINCT FROM NEW.batch_key
                   OR NOT EXISTS (
                        SELECT 1
                        FROM referral_lineage_repair_batches b
                        WHERE b.batch_key = NEW.batch_key AND b.status = 'applying'
                   ) THEN
                    RAISE EXCEPTION 'referral repair evidence requires an applying batch';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table_name in (
            "referral_lineage_repair_rows",
            "referral_finance_repair_rows",
            "referral_credit_repair_rows",
        ):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_insert_guard
                BEFORE INSERT ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION enforce_referral_repair_row_insert()
                """
            )
        op.execute(
            """
            CREATE TRIGGER trg_referral_credit_repair_rows_append_only
            BEFORE UPDATE OR DELETE ON referral_credit_repair_rows
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
                       OR NEW.invalid_credit_credits <> OLD.invalid_credit_credits
                       OR NEW.balance_debit_rub < 0
                       OR NEW.unrecovered_rub < 0
                       OR NEW.balance_debit_credits < 0
                       OR NEW.unrecovered_credits < 0
                       OR abs(
                            NEW.invalid_credit_credits
                            - NEW.balance_debit_credits
                            - NEW.unrecovered_credits
                          ) > 0.000001
                       OR abs(
                            NEW.invalid_credit_credits
                            - COALESCE((
                                SELECT sum(r.amount_credits)
                                FROM referral_credit_repair_rows r
                                WHERE r.batch_key = NEW.batch_key
                              ), 0)
                          ) > 0.000001
                       OR abs(
                            NEW.balance_debit_credits
                            - COALESCE((
                                SELECT sum(r.balance_debit_credits)
                                FROM referral_credit_repair_rows r
                                WHERE r.batch_key = NEW.batch_key
                              ), 0)
                          ) > 0.000001
                       OR abs(
                            NEW.unrecovered_credits
                            - COALESCE((
                                SELECT sum(r.unrecovered_credits)
                                FROM referral_credit_repair_rows r
                                WHERE r.batch_key = NEW.batch_key
                              ), 0)
                          ) > 0.000001
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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM referral_credit_repair_rows)")).scalar():
        raise RuntimeError(
            "Cannot downgrade after a referral credit repair: retain immutable audit evidence"
        )
    if bind.dialect.name == "postgresql":
        for table_name in (
            "referral_lineage_repair_rows",
            "referral_finance_repair_rows",
            "referral_credit_repair_rows",
        ):
            op.execute(
                f"DROP TRIGGER IF EXISTS trg_{table_name}_insert_guard ON {table_name}"
            )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_referral_credit_repair_rows_append_only "
            "ON referral_credit_repair_rows"
        )
        op.execute("DROP FUNCTION IF EXISTS enforce_referral_repair_row_insert()")
    op.drop_index(
        "ix_referral_credit_repair_rows_user", table_name="referral_credit_repair_rows"
    )
    op.drop_table("referral_credit_repair_rows")
    if bind.dialect.name == "postgresql":
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
    for column_name in (
        "unrecovered_credits",
        "balance_debit_credits",
        "invalid_credit_credits",
    ):
        op.drop_column("referral_lineage_repair_batches", column_name)

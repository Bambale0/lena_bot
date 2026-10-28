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
            "original_ledger_id",
            name="uq_referral_credit_repair_original_ledger",
        ),
        sa.UniqueConstraint(
            "reversal_ledger_id",
            name="uq_referral_credit_repair_reversal_ledger",
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
                       OR EXISTS (
                            SELECT 1
                            FROM referral_credit_repair_rows r
                            JOIN credit_ledger original ON original.id = r.original_ledger_id
                            JOIN credit_ledger reversal ON reversal.id = r.reversal_ledger_id
                            JOIN users repaired_user ON repaired_user.id = r.user_id
                            WHERE r.batch_key = NEW.batch_key
                              AND (
                                original.user_id <> r.user_id
                                OR original.entry_type <> r.entry_type
                                OR abs(original.delta - r.amount_credits) > 0.000001
                                OR original.entry_type NOT IN (
                                    'referral_first_topup_bonus', 'referral_signup_bonus'
                                )
                                OR NOT EXISTS (
                                    SELECT 1
                                    FROM referral_lineage_repair_rows lineage
                                    JOIN users invalid_child ON invalid_child.id = lineage.user_id
                                    WHERE lineage.batch_key = NEW.batch_key
                                      AND lineage.reason = 'impossible_direct_referrer'
                                      AND lineage.old_referrer_id = r.user_id
                                      AND (
                                        (
                                          original.entry_type = 'referral_first_topup_bonus'
                                          AND original.source_type IS NOT DISTINCT FROM 'referral_user'
                                          AND original.source_id IS NOT DISTINCT FROM lineage.user_id::text
                                        )
                                        OR (
                                          original.entry_type = 'referral_signup_bonus'
                                          AND original.source_type IS NOT DISTINCT FROM 'user'
                                          AND original.source_id IS NOT DISTINCT FROM lineage.user_id::text
                                        )
                                        OR (
                                          original.entry_type = 'referral_signup_bonus'
                                          AND original.source_type IS NOT DISTINCT FROM 'user'
                                          AND invalid_child.tg_id > 0
                                          AND original.source_id IS NOT DISTINCT FROM invalid_child.tg_id::text
                                        )
                                      )
                                )
                                OR (
                                  original.entry_type = 'referral_signup_bonus'
                                  AND EXISTS (
                                    SELECT 1
                                    FROM users source_owner
                                    WHERE (
                                      source_owner.id::text = original.source_id
                                      OR (
                                        source_owner.tg_id > 0
                                        AND source_owner.tg_id::text = original.source_id
                                      )
                                    )
                                    AND NOT EXISTS (
                                      SELECT 1
                                      FROM referral_lineage_repair_rows owner_lineage
                                      WHERE owner_lineage.batch_key = NEW.batch_key
                                        AND owner_lineage.reason = 'impossible_direct_referrer'
                                        AND owner_lineage.old_referrer_id = r.user_id
                                        AND owner_lineage.user_id = source_owner.id
                                    )
                                  )
                                )
                                OR reversal.user_id <> r.user_id
                                OR reversal.entry_type <> 'referral_bonus_reversal'
                                OR reversal.source_type IS DISTINCT FROM 'referral_lineage_repair'
                                OR reversal.source_id IS DISTINCT FROM (
                                    NEW.batch_key || ':' || r.original_ledger_id::text
                                )
                                OR abs(reversal.delta + r.balance_debit_credits) > 0.000001
                                OR abs(
                                    reversal.balance_after
                                    - repaired_user.credits
                                    - COALESCE((
                                        SELECT sum(later.balance_debit_credits)
                                        FROM referral_credit_repair_rows later
                                        WHERE later.batch_key = r.batch_key
                                          AND later.user_id = r.user_id
                                          AND later.reversal_ledger_id > r.reversal_ledger_id
                                      ), 0)
                                  ) > 0.000001
                              )
                          )
                       OR EXISTS (
                            SELECT 1
                            FROM referral_lineage_repair_rows lineage
                            JOIN users invalid_child ON invalid_child.id = lineage.user_id
                            JOIN credit_ledger bonus
                              ON bonus.user_id = lineage.old_referrer_id
                             AND bonus.delta > 0
                            WHERE lineage.batch_key = NEW.batch_key
                              AND lineage.reason = 'impossible_direct_referrer'
                              AND (
                                (
                                  bonus.entry_type = 'referral_first_topup_bonus'
                                  AND bonus.source_type IS NOT DISTINCT FROM 'referral_user'
                                  AND bonus.source_id IS NOT DISTINCT FROM lineage.user_id::text
                                )
                                OR (
                                  bonus.entry_type = 'referral_signup_bonus'
                                  AND bonus.source_type IS NOT DISTINCT FROM 'user'
                                  AND bonus.source_id IS NOT DISTINCT FROM lineage.user_id::text
                                  AND NOT EXISTS (
                                    SELECT 1
                                    FROM users source_owner
                                    WHERE (
                                      source_owner.id::text = bonus.source_id
                                      OR (
                                        source_owner.tg_id > 0
                                        AND source_owner.tg_id::text = bonus.source_id
                                      )
                                    )
                                    AND NOT EXISTS (
                                      SELECT 1
                                      FROM referral_lineage_repair_rows owner_lineage
                                      WHERE owner_lineage.batch_key = NEW.batch_key
                                        AND owner_lineage.reason = 'impossible_direct_referrer'
                                        AND owner_lineage.old_referrer_id = bonus.user_id
                                        AND owner_lineage.user_id = source_owner.id
                                    )
                                  )
                                )
                                OR (
                                  bonus.entry_type = 'referral_signup_bonus'
                                  AND bonus.source_type IS NOT DISTINCT FROM 'user'
                                  AND invalid_child.tg_id > 0
                                  AND bonus.source_id IS NOT DISTINCT FROM invalid_child.tg_id::text
                                  AND NOT EXISTS (
                                    SELECT 1
                                    FROM users source_owner
                                    WHERE (
                                      source_owner.id::text = bonus.source_id
                                      OR (
                                        source_owner.tg_id > 0
                                        AND source_owner.tg_id::text = bonus.source_id
                                      )
                                    )
                                    AND NOT EXISTS (
                                      SELECT 1
                                      FROM referral_lineage_repair_rows owner_lineage
                                      WHERE owner_lineage.batch_key = NEW.batch_key
                                        AND owner_lineage.reason = 'impossible_direct_referrer'
                                        AND owner_lineage.old_referrer_id = bonus.user_id
                                        AND owner_lineage.user_id = source_owner.id
                                    )
                                  )
                                )
                              )
                              AND NOT EXISTS (
                                SELECT 1
                                FROM referral_credit_repair_rows repaired
                                WHERE repaired.batch_key = NEW.batch_key
                                  AND repaired.original_ledger_id = bonus.id
                              )
                          )
                       OR NEW.summary_json IS NULL
                       OR (NEW.summary_json::jsonb ->> 'invalid_credit_credits') IS NULL
                       OR (NEW.summary_json::jsonb ->> 'balance_debit_credits') IS NULL
                       OR (NEW.summary_json::jsonb ->> 'unrecovered_credits') IS NULL
                       OR abs(
                            (NEW.summary_json::jsonb ->> 'invalid_credit_credits')::double precision
                            - NEW.invalid_credit_credits
                          ) > 0.000001
                       OR abs(
                            (NEW.summary_json::jsonb ->> 'balance_debit_credits')::double precision
                            - NEW.balance_debit_credits
                          ) > 0.000001
                       OR abs(
                            (NEW.summary_json::jsonb ->> 'unrecovered_credits')::double precision
                            - NEW.unrecovered_credits
                          ) > 0.000001
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
            CREATE OR REPLACE FUNCTION protect_finalized_referral_credit_ledger()
            RETURNS trigger AS $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM referral_credit_repair_rows r
                    JOIN referral_lineage_repair_batches b ON b.batch_key = r.batch_key
                    WHERE b.status = 'applied'
                      AND (r.original_ledger_id = OLD.id OR r.reversal_ledger_id = OLD.id)
                ) THEN
                    RAISE EXCEPTION 'finalized referral credit evidence is immutable';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_credit_ledger_finalized_referral_evidence
            BEFORE UPDATE OR DELETE ON credit_ledger
            FOR EACH ROW EXECUTE FUNCTION protect_finalized_referral_credit_ledger()
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM referral_credit_repair_rows)")).scalar():
        raise RuntimeError(
            "Cannot downgrade after a referral credit repair: retain immutable audit evidence"
        )
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_credit_ledger_finalized_referral_evidence "
            "ON credit_ledger"
        )
        op.execute("DROP FUNCTION IF EXISTS protect_finalized_referral_credit_ledger()")
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

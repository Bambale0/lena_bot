"""Database-managed, audited Tribute catalog with retained historical offers."""
import sqlalchemy as sa
from alembic import op

revision = "046_tribute_catalog"
down_revision = "045_atomic_payment_refunds"
branch_labels = None
depends_on = None

# One-time transfer of the previously live source mapping. Runtime never reads it.
SEED = (
    ("credits_15", 152362, "DDs", 200), ("credits_25", 152363, "DDt", 300),
    ("credits_50", 152364, "DDu", 590), ("credits_100_999", 152365, "DDv", 1200),
    ("credits_200", 152366, "DDw", 2400), ("credits_500", 152367, "DDx", 5800),
)


def upgrade():
    op.create_table("tribute_products",
        sa.Column("product_id", sa.BigInteger(), primary_key=True),
        sa.Column("plan_key", sa.String(64), sa.ForeignKey("price_plans.key"), nullable=False),
        sa.Column("payment_url", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("credits", sa.Float(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tribute_products_plan_key", "tribute_products", ["plan_key"])
    op.create_index("uq_tribute_active_plan", "tribute_products", ["plan_key"], unique=True, postgresql_where=sa.text("enabled"))
    op.create_table("tribute_product_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("tribute_products.product_id"), nullable=False),
        sa.Column("previous", sa.JSON()), sa.Column("current", sa.JSON(), nullable=False),
        sa.Column("admin_tg_id", sa.BigInteger()), sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tribute_product_audit_product_id", "tribute_product_audit", ["product_id"])
    for plan, product, slug, minor in SEED:
        op.get_bind().execute(sa.text("""
            INSERT INTO tribute_products (product_id, plan_key, payment_url, currency,
                amount_minor, credits, amount_rub, enabled, revision)
            SELECT :product, key, :url, 'usd', :minor, credits, price_rub, is_active, 1
            FROM price_plans WHERE key = :plan
        """), {"product": product, "url": "https://web.tribute.tg/p/" + slug, "minor": minor, "plan": plan})
    op.execute("""INSERT INTO tribute_product_audit(product_id, current, source)
        SELECT product_id, to_jsonb(tribute_products), 'migration' FROM tribute_products""")


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM tribute_product_audit WHERE source <> 'migration')")).scalar():
        raise RuntimeError("Retain changed catalog/audit and roll forward")
    op.drop_table("tribute_product_audit")
    op.drop_table("tribute_products")

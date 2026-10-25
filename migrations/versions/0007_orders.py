"""Payments (BUILD_PLAN module 13): the orders table and projects.payment_status.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
ORDER_STATUSES = ("created", "paid", "failed", "refunded")
PAYMENT_STATUSES = ("unpaid", "pilot", "paid", "refunded")


def _in(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade():
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer),
        sa.Column("product", sa.Text, nullable=False),
        sa.Column("amount_paise", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False, server_default="INR"),
        sa.Column("provider", sa.Text, nullable=False, server_default="razorpay"),
        sa.Column("provider_ref", sa.String(64), nullable=False),
        sa.Column("provider_payment_id", sa.String(64)),
        sa.Column("status", sa.Text, nullable=False, server_default="created"),
        sa.Column("failure_reason", sa.Text),
        sa.Column("invoice_number", sa.String(32)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("refunded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_orders_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_orders_user_id_users", ondelete="SET NULL"),
        sa.UniqueConstraint("provider_ref", name="uq_orders_provider_ref"),
        sa.UniqueConstraint("invoice_number", name="uq_orders_invoice_number"),
        sa.CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),
    )
    op.create_index("ix_orders_project_id", "orders", ["project_id"])
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("payment_status", sa.Text, nullable=False, server_default="unpaid"))
        batch.create_check_constraint("payment_status", _in("payment_status", PAYMENT_STATUSES))
    # Every book made so far was made during the free pilot.
    op.execute("UPDATE projects SET payment_status = 'pilot'")


def downgrade():
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("payment_status", type_="check")
        batch.drop_column("payment_status")
    op.drop_table("orders")

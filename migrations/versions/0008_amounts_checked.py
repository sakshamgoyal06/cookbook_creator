"""The amounts step before approval (Saksham's test, 2026-10-26): recipes.amounts_checked_at.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("recipes") as batch:
        batch.add_column(sa.Column("amounts_checked_at", sa.DateTime(timezone=True)))


def downgrade():
    with op.batch_alter_table("recipes") as batch:
        batch.drop_column("amounts_checked_at")

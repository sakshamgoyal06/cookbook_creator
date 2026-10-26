"""Photo crops: how each photo sits in its spot in the book.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("photo_crops", JSONType))
    with op.batch_alter_table("recipes") as batch:
        batch.add_column(sa.Column("photo_crop", JSONType))


def downgrade():
    with op.batch_alter_table("recipes") as batch:
        batch.drop_column("photo_crop")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("photo_crops")

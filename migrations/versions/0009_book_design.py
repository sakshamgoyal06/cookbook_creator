"""Book design (module 18): size, accent, cover layout and photos for the book and each recipe.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("book_size", sa.Text(), nullable=False, server_default="a4"))
        batch.add_column(sa.Column("book_accent", sa.Text()))
        batch.add_column(sa.Column("cover_layout", sa.Text(), nullable=False, server_default="photo"))
        batch.add_column(sa.Column("cook_photo_key", sa.Text()))
        batch.add_column(sa.Column("family_photo_key", sa.Text()))
    with op.batch_alter_table("recipes") as batch:
        batch.add_column(sa.Column("photo_key", sa.Text()))


def downgrade():
    with op.batch_alter_table("recipes") as batch:
        batch.drop_column("photo_key")
    with op.batch_alter_table("projects") as batch:
        for name in ("family_photo_key", "cook_photo_key", "cover_layout", "book_accent", "book_size"):
            batch.drop_column(name)

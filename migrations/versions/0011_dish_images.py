"""Dish photos from the internet: the shared dish_images library and each recipe's photo credit.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade():
    op.create_table(
        "dish_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dish_key", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("creator", sa.Text),
        sa.Column("license", sa.Text, nullable=False),
        sa.Column("license_url", sa.Text),
        sa.Column("landing_url", sa.Text),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("use_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source", "source_id", name="uq_dish_images_source_id"),
    )
    op.create_index("ix_dish_images_dish_key", "dish_images", ["dish_key"])
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("photo_credit", sa.Text))
        batch.add_column(sa.Column("photo_image_id", sa.Integer))
        batch.create_foreign_key("fk_recipes_photo_image_id_dish_images", "dish_images", ["photo_image_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("fk_recipes_photo_image_id_dish_images", type_="foreignkey")
        batch.drop_column("photo_image_id")
        batch.drop_column("photo_credit")
    op.drop_index("ix_dish_images_dish_key", "dish_images")
    op.drop_table("dish_images")

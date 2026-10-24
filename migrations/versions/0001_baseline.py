"""Baseline: the schema init_db() created before migrations existed.

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text),
        sa.Column("auth_provider", sa.Text, server_default="email"),
        sa.Column("auth_provider_id", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("subtitle", sa.Text, server_default=""),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("theme", sa.Text, server_default="classic"),
        sa.Column("max_recipes", sa.Integer, server_default="50"),
        sa.Column("max_pages", sa.Integer, server_default="100"),
        sa.Column("acknowledgement", sa.Text, server_default=""),
        sa.Column("about_author", sa.Text, server_default=""),
        sa.Column("dedication", sa.Text, server_default=""),
        sa.Column("introduction", sa.Text, server_default=""),
        sa.Column("cover_note", sa.Text, server_default=""),
        sa.Column("status", sa.Text, server_default="draft"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_projects_user_id_users"),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("recipe_id", sa.Text, nullable=False),
        sa.Column("audio_filename", sa.Text),
        sa.Column("raw_transcript", sa.Text),
        sa.Column("recipe_title", sa.Text),
        sa.Column("alternate_names_json", sa.Text, server_default="[]"),
        sa.Column("category", sa.Text),
        sa.Column("family_note", sa.Text),
        sa.Column("serves", sa.Text),
        sa.Column("prep_time_minutes", sa.Integer),
        sa.Column("cook_time_minutes", sa.Integer),
        sa.Column("difficulty", sa.Text),
        sa.Column("ingredients_json", sa.Text, server_default="[]"),
        sa.Column("method_steps_json", sa.Text, server_default="[]"),
        sa.Column("moms_tips_json", sa.Text, server_default="[]"),
        sa.Column("serving_suggestion", sa.Text),
        sa.Column("storage_notes", sa.Text),
        sa.Column("unclear_items_for_review_json", sa.Text, server_default="[]"),
        sa.Column("status", sa.Text, server_default="uploaded"),
        sa.Column("pdf_filename", sa.Text),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_recipes_project_id_projects"),
        sa.UniqueConstraint("recipe_id", name="uq_recipes_recipe_id"),
    )


def downgrade():
    op.drop_table("recipes")
    op.drop_table("projects")
    op.drop_table("users")

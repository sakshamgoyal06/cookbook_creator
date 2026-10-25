"""Follow-up questions about a recipe's unclear bits (BUILD_PLAN module 10).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

QUESTION_STATUSES = ("open", "answered", "kept", "skipped", "expired")


def _in(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade():
    op.create_table(
        "recipe_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="1"),
        sa.Column("about", sa.Text, nullable=False, server_default=""),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("options", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
                  nullable=False, server_default="[]"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("answer_text", sa.Text),
        sa.Column("answer_via", sa.Text),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_recipe_questions_recipe_id_recipes",
                                ondelete="CASCADE"),
        sa.CheckConstraint(_in("status", QUESTION_STATUSES), name="ck_recipe_questions_status"),
    )
    op.create_index("ix_recipe_questions_recipe_id", "recipe_questions", ["recipe_id"])


def downgrade():
    op.drop_table("recipe_questions")

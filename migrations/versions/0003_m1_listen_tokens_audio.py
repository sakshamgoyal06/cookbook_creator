"""M1 QR voice playback: listen and book tokens, recipe_audio, listen_events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade():
    _add_token("projects", "book_token")
    _add_token("recipes", "listen_token")
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("listen_revoked_at", TZ))

    op.create_table(
        "recipe_audio",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text),
        sa.Column("duration_s", sa.Integer),
        sa.Column("kind", sa.Text, nullable=False, server_default="original"),
        sa.Column("play_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source", sa.Text, nullable=False, server_default="web"),
        sa.Column("wa_message_id", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_recipe_audio_recipe_id_recipes",
                                ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('original', 'followup', 'story')", name="ck_recipe_audio_kind"),
    )
    op.create_index("ix_recipe_audio_recipe_id", "recipe_audio", ["recipe_id"])
    op.execute(
        "INSERT INTO recipe_audio (recipe_id, storage_key, kind, play_order, source, created_at) "
        "SELECT id, audio_filename, 'original', 1, 'web', created_at FROM recipes "
        "WHERE audio_filename IS NOT NULL AND audio_filename <> ''"
    )
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_column("audio_filename")

    op.create_table(
        "listen_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, nullable=False),
        sa.Column("played_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_listen_events_recipe_id_recipes",
                                ondelete="CASCADE"),
    )
    op.create_index("ix_listen_events_recipe_id", "listen_events", ["recipe_id"])


def _add_token(table, column):
    """Add a unique token column and give every existing row its own token."""
    with op.batch_alter_table(table, naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column(column, sa.String(32)))
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text(f"SELECT id FROM {table}"))]
    for row_id in ids:
        bind.execute(
            sa.text(f"UPDATE {table} SET {column} = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(16), "id": row_id},
        )
    with op.batch_alter_table(table, naming_convention=NAMING_CONVENTION) as batch:
        batch.alter_column(column, existing_type=sa.String(32), nullable=False)
        batch.create_unique_constraint(f"uq_{table}_{column}", [column])


def downgrade():
    op.drop_table("listen_events")
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("audio_filename", sa.Text))
    op.execute(
        "UPDATE recipes SET audio_filename = (SELECT a.storage_key FROM recipe_audio a "
        "WHERE a.recipe_id = recipes.id ORDER BY a.play_order, a.id LIMIT 1)"
    )
    op.drop_table("recipe_audio")
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("uq_recipes_listen_token", type_="unique")
        batch.drop_column("listen_revoked_at")
        batch.drop_column("listen_token")
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("uq_projects_book_token", type_="unique")
        batch.drop_column("book_token")

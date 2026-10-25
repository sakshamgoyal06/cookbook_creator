"""Mobile UX v1 data model: cook and gift fields, dishes, family members,
upload sessions, analytics events, listen sources (BUILD_PLAN module 4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
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
COOK_MODES = ("whatsapp", "self", "assisted")
LANGUAGES = ("hi", "hinglish", "en")
DISH_SOURCES = ("buyer", "family", "cook")
DISH_STATUSES = ("wishlist", "in_progress", "done", "skipped")
MEMBER_ROLES = ("buyer", "cook", "member")
UPLOAD_STATUSES = ("open", "complete", "abandoned")
ACTORS = ("buyer", "cook", "family", "system", "anon")
LISTEN_SOURCES = ("qr", "link", "book", "app")


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _created_at():
    return sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now())


def upgrade():
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("cook_mode", sa.Text, nullable=False, server_default="whatsapp"))
        batch.add_column(sa.Column("storyteller_name", sa.Text))
        batch.add_column(sa.Column("storyteller_address_as", sa.Text))
        batch.add_column(sa.Column("storyteller_phone", sa.Text))
        batch.add_column(sa.Column("storyteller_language", sa.Text, nullable=False, server_default="hinglish"))
        batch.add_column(sa.Column("occasion", sa.Text))
        batch.add_column(sa.Column("reveal_date", sa.Date))
        batch.add_column(sa.Column("share_pages_as_ready", sa.Boolean, nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("tier", sa.Text, nullable=False, server_default="top10"))
        batch.add_column(sa.Column("setup_step", sa.Text))
        batch.add_column(sa.Column("invite_sent_at", TZ))
        batch.add_column(sa.Column("consent_at", TZ))
        batch.add_column(sa.Column("reminders_paused_until", TZ))
        batch.add_column(sa.Column("revealed_at", TZ))
        batch.add_column(sa.Column("cook_token", sa.String(32)))
        batch.add_column(sa.Column("cook_token_revoked_at", TZ))
        batch.create_check_constraint("cook_mode", _in("cook_mode", COOK_MODES))
        batch.create_check_constraint("storyteller_language", _in("storyteller_language", LANGUAGES))

    bind = op.get_bind()
    # Every project so far was made through web upload.
    bind.execute(sa.text("UPDATE projects SET cook_mode = 'self'"))
    for (project_id,) in bind.execute(sa.text("SELECT id FROM projects")).fetchall():
        bind.execute(sa.text("UPDATE projects SET cook_token = :t WHERE id = :id"),
                     {"t": secrets.token_urlsafe(16), "id": project_id})
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.alter_column("cook_token", existing_type=sa.String(32), nullable=False)
        batch.create_unique_constraint("uq_projects_cook_token", ["cook_token"])

    op.create_table(
        "family_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="member"),
        sa.Column("user_id", sa.Integer),
        sa.Column("joined_at", TZ),
        sa.Column("removed_at", TZ),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_family_members_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_family_members_user_id_users",
                                ondelete="SET NULL"),
        sa.CheckConstraint(_in("role", MEMBER_ROLES), name="ck_family_members_role"),
    )
    op.create_index("ix_family_members_project_id", "family_members", ["project_id"])

    op.create_table(
        "dishes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.Text, nullable=False, server_default="buyer"),
        sa.Column("requested_by_member_id", sa.Integer),
        sa.Column("requested_by_label", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="wishlist"),
        sa.Column("recipe_id", sa.Integer),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_dishes_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_member_id"], ["family_members.id"],
                                name="fk_dishes_requested_by_member_id_family_members", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_dishes_recipe_id_recipes",
                                ondelete="SET NULL"),
        sa.UniqueConstraint("recipe_id", name="uq_dishes_recipe_id"),
        sa.CheckConstraint(_in("source", DISH_SOURCES), name="ck_dishes_source"),
        sa.CheckConstraint(_in("status", DISH_STATUSES), name="ck_dishes_status"),
    )
    op.create_index("ix_dishes_project_id", "dishes", ["project_id"])

    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("cook_name", sa.Text))

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("client_upload_id", sa.String(64), nullable=False),
        sa.Column("dish_id", sa.Integer),
        sa.Column("kind", sa.Text, nullable=False, server_default="original"),
        sa.Column("content_type", sa.Text),
        sa.Column("chunks_received", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bytes_received", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("recipe_id", sa.Integer),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_upload_sessions_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_upload_sessions_dish_id_dishes",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_upload_sessions_recipe_id_recipes",
                                ondelete="SET NULL"),
        sa.UniqueConstraint("client_upload_id", name="uq_upload_sessions_client_upload_id"),
        sa.CheckConstraint(_in("status", UPLOAD_STATUSES), name="ck_upload_sessions_status"),
    )
    op.create_index("ix_upload_sessions_project_id", "upload_sessions", ["project_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("project_id", sa.Integer),
        sa.Column("recipe_id", sa.Integer),
        sa.Column("actor", sa.Text, nullable=False, server_default="system"),
        sa.Column("channel", sa.Text, nullable=False, server_default="web"),
        sa.Column("props", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
                  nullable=False, server_default="{}"),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_events_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_events_recipe_id_recipes",
                                ondelete="CASCADE"),
        sa.CheckConstraint(_in("actor", ACTORS), name="ck_events_actor"),
    )
    op.create_index("ix_events_name_created_at", "events", ["name", "created_at"])
    op.create_index("ix_events_project_id_created_at", "events", ["project_id", "created_at"])

    with op.batch_alter_table("listen_events", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("source", sa.Text, nullable=False, server_default="link"))
        batch.add_column(sa.Column("is_owner", sa.Boolean, nullable=False, server_default=sa.false()))
        batch.create_check_constraint("source", _in("source", LISTEN_SOURCES))

    # Backfill: a buyer member per project, and a dish per existing recipe.
    bind.execute(sa.text(
        "INSERT INTO family_members (project_id, name, role, user_id, joined_at, created_at) "
        "SELECT p.id, u.name, 'buyer', u.id, p.created_at, p.created_at "
        "FROM projects p JOIN users u ON u.id = p.user_id"
    ))
    bind.execute(sa.text(
        "INSERT INTO dishes (project_id, title, position, source, status, recipe_id, created_at) "
        "SELECT project_id, COALESCE(NULLIF(recipe_title, ''), 'Recipe'), id, 'buyer', "
        "CASE WHEN status = 'approved' THEN 'done' ELSE 'in_progress' END, id, created_at FROM recipes"
    ))


def downgrade():
    with op.batch_alter_table("listen_events", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("source", type_="check")
        batch.drop_column("is_owner")
        batch.drop_column("source")
    op.drop_table("events")
    op.drop_table("upload_sessions")
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_column("cook_name")
    op.drop_table("dishes")
    op.drop_table("family_members")
    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("uq_projects_cook_token", type_="unique")
        batch.drop_constraint("cook_mode", type_="check")
        batch.drop_constraint("storyteller_language", type_="check")
        for column in ("cook_token_revoked_at", "cook_token", "revealed_at", "reminders_paused_until",
                       "consent_at", "invite_sent_at", "setup_step", "tier", "share_pages_as_ready",
                       "reveal_date", "occasion", "storyteller_language", "storyteller_phone",
                       "storyteller_address_as", "storyteller_name", "cook_mode"):
            batch.drop_column(column)

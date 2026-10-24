"""M0 foundations: time zones, indexes, cascades, recipe status flow,
generated_files and pipeline_runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TIMESTAMP_COLUMNS = {
    "users": ["created_at"],
    "projects": ["created_at", "updated_at"],
    "recipes": ["created_at", "updated_at"],
}
JSON_COLUMNS = [
    "alternate_names_json",
    "ingredients_json",
    "method_steps_json",
    "moms_tips_json",
    "unclear_items_for_review_json",
]
TZ = sa.DateTime(timezone=True)

# Copied, not imported, so this migration stays the same when models/schema.py changes.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
JSONType = sa.JSON().with_variant(JSONB(), "postgresql")
RECIPE_STATUSES = ("received", "transcribed", "structured", "awaiting_mom", "needs_review", "approved", "failed")
GENERATED_FILE_KINDS = ("recipe_pdf", "book_pdf", "page_png", "card_png")
PIPELINE_STAGES = ("transcribe", "structure", "questions", "render")
PIPELINE_STATUSES = ("queued", "running", "succeeded", "failed")


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _is_postgres():
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    _clean_existing_data()

    with op.batch_alter_table("users", naming_convention=NAMING_CONVENTION) as batch:
        batch.alter_column("created_at", type_=TZ, nullable=False, server_default=sa.func.now(),
                           postgresql_using="created_at AT TIME ZONE 'UTC'")
        batch.add_column(sa.Column("updated_at", TZ, nullable=False, server_default=sa.func.now()))
        batch.create_unique_constraint("uq_users_auth_provider_id", ["auth_provider", "auth_provider_id"])

    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        _timestamps_to_tz(batch, "projects")
        batch.drop_constraint("fk_projects_user_id_users", type_="foreignkey")
        batch.create_foreign_key("fk_projects_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_projects_user_id", ["user_id"])

    if _is_postgres():
        for column in JSON_COLUMNS:
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} DROP DEFAULT")
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} TYPE JSONB USING {column}::jsonb")
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} SET DEFAULT '[]'::jsonb")

    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        _timestamps_to_tz(batch, "recipes")
        if not _is_postgres():
            for column in JSON_COLUMNS:
                batch.alter_column(column, type_=JSONType, existing_server_default="[]")
        batch.alter_column("status", nullable=False, server_default="received")
        batch.add_column(sa.Column("section", sa.Text))
        batch.add_column(sa.Column("approved_at", TZ))
        batch.create_check_constraint("status", _in("status", RECIPE_STATUSES))
        batch.drop_constraint("fk_recipes_project_id_projects", type_="foreignkey")
        batch.create_foreign_key(
            "fk_recipes_project_id_projects", "projects", ["project_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_recipes_project_id", ["project_id"])

    op.execute("UPDATE recipes SET approved_at = updated_at WHERE status = 'approved'")

    op.create_table(
        "generated_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("recipe_id", sa.Integer),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_generated_files_project_id_projects",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_generated_files_recipe_id_recipes",
                                ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_generated_files_storage_key"),
        sa.CheckConstraint(_in("kind", GENERATED_FILE_KINDS), name="ck_generated_files_kind"),
    )
    op.create_index("ix_generated_files_project_id", "generated_files", ["project_id"])
    op.create_index("ix_generated_files_recipe_id", "generated_files", ["recipe_id"])
    op.execute(
        "INSERT INTO generated_files (project_id, recipe_id, kind, storage_key, created_at) "
        "SELECT project_id, id, 'recipe_pdf', pdf_filename, updated_at FROM recipes "
        "WHERE pdf_filename IS NOT NULL AND pdf_filename <> ''"
    )
    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_column("pdf_filename")

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipe_id", sa.Integer, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("provider", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("audio_seconds", sa.Integer),
        sa.Column("cost_paise", sa.Integer),
        sa.Column("started_at", TZ),
        sa.Column("finished_at", TZ),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name="fk_pipeline_runs_recipe_id_recipes",
                                ondelete="CASCADE"),
        sa.CheckConstraint(_in("stage", PIPELINE_STAGES), name="ck_pipeline_runs_stage"),
        sa.CheckConstraint(_in("status", PIPELINE_STATUSES), name="ck_pipeline_runs_status"),
    )
    op.create_index("ix_pipeline_runs_recipe_id", "pipeline_runs", ["recipe_id"])
    op.create_index("ix_pipeline_runs_status_created_at", "pipeline_runs", ["status", "created_at"])


def _clean_existing_data():
    """Make old rows fit the new constraints before they are added."""
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.execute(f"UPDATE {table} SET {column} = CURRENT_TIMESTAMP WHERE {column} IS NULL")
            if not _is_postgres():
                # Python wrote ISO strings ("2026-10-24T17:00:00.123+00:00", always UTC);
                # SQLite wrote "2026-10-24 17:00:00". Store them all the SQLite way.
                op.execute(
                    f"UPDATE {table} SET {column} = replace(substr({column}, 1, 19), 'T', ' ') "
                    f"WHERE {column} LIKE '%T%'"
                )

    # Old flow: uploaded -> needs_review -> approved -> pdf_generated.
    op.execute("UPDATE recipes SET status = 'received' WHERE status IS NULL OR status = 'uploaded'")
    op.execute("UPDATE recipes SET status = 'approved' WHERE status = 'pdf_generated'")
    op.execute(f"UPDATE recipes SET status = 'needs_review' WHERE NOT ({_in('status', RECIPE_STATUSES)})")
    for column in JSON_COLUMNS:
        op.execute(f"UPDATE recipes SET {column} = '[]' WHERE {column} IS NULL OR {column} = ''")


def _timestamps_to_tz(batch, table):
    for column in TIMESTAMP_COLUMNS[table]:
        batch.alter_column(column, type_=TZ, nullable=False, server_default=sa.func.now(),
                           postgresql_using=f"{column} AT TIME ZONE 'UTC'")


def downgrade():
    op.drop_table("pipeline_runs")

    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.add_column(sa.Column("pdf_filename", sa.Text))
    op.execute(
        "UPDATE recipes SET pdf_filename = (SELECT max(g.storage_key) FROM generated_files g "
        "WHERE g.recipe_id = recipes.id AND g.kind = 'recipe_pdf')"
    )
    op.drop_table("generated_files")

    with op.batch_alter_table("recipes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_index("ix_recipes_project_id")
        batch.drop_constraint("fk_recipes_project_id_projects", type_="foreignkey")
        batch.create_foreign_key("fk_recipes_project_id_projects", "projects", ["project_id"], ["id"])
        batch.drop_constraint("status", type_="check")
        batch.drop_column("approved_at")
        batch.drop_column("section")
        batch.alter_column("status", nullable=True, server_default="uploaded")
        for column in TIMESTAMP_COLUMNS["recipes"]:
            batch.alter_column(column, type_=sa.DateTime, nullable=True,
                               server_default=sa.func.current_timestamp())
        if not _is_postgres():
            for column in JSON_COLUMNS:
                batch.alter_column(column, type_=sa.Text, existing_server_default="[]")
    if _is_postgres():
        for column in JSON_COLUMNS:
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} DROP DEFAULT")
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} TYPE TEXT USING {column}::text")
            op.execute(f"ALTER TABLE recipes ALTER COLUMN {column} SET DEFAULT '[]'")
    op.execute("UPDATE recipes SET status = 'uploaded' WHERE status = 'received'")

    with op.batch_alter_table("projects", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_index("ix_projects_user_id")
        batch.drop_constraint("fk_projects_user_id_users", type_="foreignkey")
        batch.create_foreign_key("fk_projects_user_id_users", "users", ["user_id"], ["id"])
        for column in TIMESTAMP_COLUMNS["projects"]:
            batch.alter_column(column, type_=sa.DateTime, nullable=True,
                               server_default=sa.func.current_timestamp())

    with op.batch_alter_table("users", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("uq_users_auth_provider_id", type_="unique")
        batch.drop_column("updated_at")
        batch.alter_column("created_at", type_=sa.DateTime, nullable=True,
                           server_default=sa.func.current_timestamp())

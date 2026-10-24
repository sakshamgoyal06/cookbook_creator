"""Table definitions for the current schema (Alembic head).

Migrations in migrations/versions/ are the source of truth for how the database
gets here; keep this file in step with them (tests/test_database.py checks it).
"""
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

RECIPE_STATUSES = (
    "received",
    "transcribed",
    "structured",
    "awaiting_mom",
    "needs_review",
    "approved",
    "failed",
)
AUDIO_KINDS = ("original", "followup", "story")
GENERATED_FILE_KINDS = ("recipe_pdf", "book_pdf", "page_png", "card_png")
PIPELINE_STAGES = ("transcribe", "structure", "questions", "render")
PIPELINE_STATUSES = ("queued", "running", "succeeded", "failed")

# JSONB on Postgres, JSON text on SQLite.
JSONType = JSON().with_variant(JSONB(), "postgresql")

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _in(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _created_at():
    return Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at():
    return Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now())


users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("password_hash", Text),
    Column("auth_provider", Text, server_default="email"),
    Column("auth_provider_id", Text),
    _created_at(),
    _updated_at(),
    UniqueConstraint("auth_provider", "auth_provider_id", name="uq_users_auth_provider_id"),
)

projects = Table(
    "projects",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("title", Text, nullable=False),
    Column("subtitle", Text, server_default=""),
    Column("description", Text, server_default=""),
    Column("theme", Text, server_default="classic"),
    Column("max_recipes", Integer, server_default="50"),
    Column("max_pages", Integer, server_default="100"),
    Column("acknowledgement", Text, server_default=""),
    Column("about_author", Text, server_default=""),
    Column("dedication", Text, server_default=""),
    Column("introduction", Text, server_default=""),
    Column("cover_note", Text, server_default=""),
    Column("status", Text, server_default="draft"),
    # Public token for the family cookbook page /b/<token> (QR-8).
    Column("book_token", String(32), nullable=False, unique=True),
    _created_at(),
    _updated_at(),
)

recipes = Table(
    "recipes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    # Random id used as the PDF filename prefix until files move to object storage.
    Column("recipe_id", Text, nullable=False, unique=True),
    Column("raw_transcript", Text),
    Column("recipe_title", Text),
    Column("alternate_names_json", JSONType, server_default="[]"),
    Column("category", Text),
    Column("family_note", Text),
    Column("serves", Text),
    Column("prep_time_minutes", Integer),
    Column("cook_time_minutes", Integer),
    Column("difficulty", Text),
    Column("ingredients_json", JSONType, server_default="[]"),
    Column("method_steps_json", JSONType, server_default="[]"),
    Column("moms_tips_json", JSONType, server_default="[]"),
    Column("serving_suggestion", Text),
    Column("storage_notes", Text),
    Column("unclear_items_for_review_json", JSONType, server_default="[]"),
    Column("status", Text, nullable=False, server_default="received"),
    Column("section", Text),
    Column("sort_order", Integer, server_default="0"),
    Column("approved_at", DateTime(timezone=True)),
    # Public token for the listen page /l/<token> (QR-3); revoking keeps the row.
    Column("listen_token", String(32), nullable=False, unique=True),
    Column("listen_revoked_at", DateTime(timezone=True)),
    _created_at(),
    _updated_at(),
    CheckConstraint(_in("status", RECIPE_STATUSES), name="status"),
)

recipe_audio = Table(
    "recipe_audio",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("storage_key", Text, nullable=False),
    Column("content_type", Text),
    Column("duration_s", Integer),
    Column("kind", Text, nullable=False, server_default="original"),
    Column("play_order", Integer, nullable=False, server_default="1"),
    Column("source", Text, nullable=False, server_default="web"),
    Column("wa_message_id", Text),
    _created_at(),
    CheckConstraint(_in("kind", AUDIO_KINDS), name="kind"),
)

listen_events = Table(
    "listen_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("played_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

generated_files = Table(
    "generated_files",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), index=True),
    Column("kind", Text, nullable=False),
    Column("storage_key", Text, nullable=False, unique=True),
    _created_at(),
    CheckConstraint(_in("kind", GENERATED_FILE_KINDS), name="kind"),
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("stage", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="queued"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Column("provider", Text),
    Column("model", Text),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("audio_seconds", Integer),
    Column("cost_paise", Integer),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    _created_at(),
    CheckConstraint(_in("stage", PIPELINE_STAGES), name="stage"),
    CheckConstraint(_in("status", PIPELINE_STATUSES), name="status"),
    Index("ix_pipeline_runs_status_created_at", "status", "created_at"),
)

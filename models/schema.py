"""Table definitions for the current schema (Alembic head).

Migrations in migrations/versions/ are the source of truth for how the database
gets here; keep this file in step with them (tests/test_database.py checks it).
"""
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
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
    false,
    func,
    true,
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
COOK_MODES = ("whatsapp", "self", "assisted")
LANGUAGES = ("hi", "hinglish", "en")
DISH_SOURCES = ("buyer", "family", "cook")
DISH_STATUSES = ("requested", "wishlist", "in_progress", "done", "skipped")
MEMBER_ROLES = ("buyer", "cook", "member")
UPLOAD_STATUSES = ("open", "complete", "abandoned")
ACTORS = ("buyer", "cook", "family", "system", "anon")
LISTEN_SOURCES = ("qr", "link", "book", "app")
ORDER_STATUSES = ("created", "paid", "failed", "refunded")
PAYMENT_STATUSES = ("unpaid", "pilot", "paid", "refunded")
QUESTION_STATUSES = ("open", "answered", "kept", "skipped", "expired")

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
    # Who records: the cook on WhatsApp, the owner themselves, or the owner recording the cook.
    Column("cook_mode", Text, nullable=False, server_default="whatsapp"),
    Column("storyteller_name", Text),
    # What the buyer calls her (Mummy, Maa, Dadi); used in the buyer's own invite and UI copy.
    Column("storyteller_address_as", Text),
    Column("storyteller_phone", Text),
    Column("storyteller_language", Text, nullable=False, server_default="hinglish"),
    Column("occasion", Text),
    Column("reveal_date", Date),
    Column("share_pages_as_ready", Boolean, nullable=False, server_default=true()),
    Column("tier", Text, nullable=False, server_default="top10"),
    # Last finished onboarding step, so a buyer who leaves mid-setup resumes there.
    Column("setup_step", Text),
    Column("invite_sent_at", DateTime(timezone=True)),
    Column("consent_at", DateTime(timezone=True)),
    Column("reminders_paused_until", DateTime(timezone=True)),
    Column("revealed_at", DateTime(timezone=True)),
    # Public token for the cook's page /m/<token> (module 15).
    Column("cook_token", String(32), nullable=False, unique=True),
    Column("cook_token_revoked_at", DateTime(timezone=True)),
    # unpaid until checkout succeeds (module 13); "pilot" books were made free during the invite-only pilot.
    Column("payment_status", Text, nullable=False, server_default="unpaid"),
    # Book design (module 18): the style is `theme`; these pick the size, colour, cover and photos.
    Column("book_size", Text, nullable=False, server_default="a4"),
    Column("book_accent", Text),
    Column("cover_layout", Text, nullable=False, server_default="photo"),
    Column("cook_photo_key", Text),
    Column("family_photo_key", Text),
    # How each photo sits in its spot: {"cook": {"x", "y", "zoom"}, "family": {...}} (photo_service).
    Column("photo_crops", JSONType),
    _created_at(),
    _updated_at(),
    CheckConstraint(_in("cook_mode", COOK_MODES), name="cook_mode"),
    CheckConstraint(_in("payment_status", PAYMENT_STATUSES), name="payment_status"),
    CheckConstraint(_in("storyteller_language", LANGUAGES), name="storyteller_language"),
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
    # When the buyer went through the amounts step (vague or missing quantities), the step before approval.
    Column("amounts_checked_at", DateTime(timezone=True)),
    # Public token for the listen page /l/<token> (QR-3); revoking keeps the row.
    Column("listen_token", String(32), nullable=False, unique=True),
    Column("listen_revoked_at", DateTime(timezone=True)),
    # Set in assisted mode when the person speaking isn't the project's storyteller.
    Column("cook_name", Text),
    Column("photo_key", Text),
    Column("photo_crop", JSONType),
    # A photo picked from the internet or the shared library: its credit line, and where it came from.
    Column("photo_credit", Text),
    Column("photo_image_id", Integer, ForeignKey("dish_images.id", ondelete="SET NULL")),
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
    Column("source", Text, nullable=False, server_default="link"),
    # Plays by the project owner are excluded from counts shown to the cook and from the voice metric.
    Column("is_owner", Boolean, nullable=False, server_default=false()),
    CheckConstraint(_in("source", LISTEN_SOURCES), name="source"),
)

family_members = Table(
    "family_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("name", Text, nullable=False),
    Column("role", Text, nullable=False, server_default="member"),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")),
    Column("joined_at", DateTime(timezone=True)),
    Column("removed_at", DateTime(timezone=True)),
    _created_at(),
    CheckConstraint(_in("role", MEMBER_ROLES), name="role"),
)

# One ordered list per project: the buyer's wishlist and family requests (replaces PRD dish_requests).
dishes = Table(
    "dishes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("title", Text, nullable=False),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("source", Text, nullable=False, server_default="buyer"),
    Column("requested_by_member_id", Integer, ForeignKey("family_members.id", ondelete="SET NULL")),
    Column("requested_by_label", Text),
    Column("status", Text, nullable=False, server_default="wishlist"),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="SET NULL"), unique=True),
    _created_at(),
    CheckConstraint(_in("source", DISH_SOURCES), name="source"),
    CheckConstraint(_in("status", DISH_STATUSES), name="status"),
)

# Dish photos with a free licence, shared by every book (module 18). Each was picked once from a
# photo search; later cooks of the same dish see it first and reuse the stored copy, no search needed.
dish_images = Table(
    "dish_images",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("dish_key", Text, nullable=False, index=True),
    Column("source", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("title", Text),
    Column("creator", Text),
    Column("license", Text, nullable=False),
    Column("license_url", Text),
    Column("landing_url", Text),
    Column("storage_key", Text, nullable=False),
    Column("width", Integer),
    Column("height", Integer),
    Column("use_count", Integer, nullable=False, server_default="0"),
    _created_at(),
    UniqueConstraint("source", "source_id", name="uq_dish_images_source_id"),
)

# Chunked, resumable uploads from the in-app recorder (module 7).
upload_sessions = Table(
    "upload_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("client_upload_id", String(64), nullable=False, unique=True),
    Column("dish_id", Integer, ForeignKey("dishes.id", ondelete="SET NULL")),
    Column("kind", Text, nullable=False, server_default="original"),
    Column("content_type", Text),
    Column("chunks_received", Integer, nullable=False, server_default="0"),
    Column("bytes_received", Integer, nullable=False, server_default="0"),
    Column("status", Text, nullable=False, server_default="open"),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="SET NULL")),
    _created_at(),
    CheckConstraint(_in("status", UPLOAD_STATUSES), name="status"),
)

# Follow-up questions about a recipe's unclear bits (module 10). At most 3 per recipe.
recipe_questions = Table(
    "recipe_questions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("position", Integer, nullable=False, server_default="1"),
    Column("about", Text, nullable=False, server_default=""),
    Column("question", Text, nullable=False),
    Column("options", JSONType, nullable=False, server_default="[]"),
    Column("status", Text, nullable=False, server_default="open"),
    Column("answer_text", Text),
    # chip | text | voice | keep ("leave it as I said it")
    Column("answer_via", Text),
    Column("answered_at", DateTime(timezone=True)),
    _created_at(),
    CheckConstraint(_in("status", QUESTION_STATUSES), name="status"),
)

# Analytics events (module 3). No personal data in props.
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE")),
    Column("recipe_id", Integer, ForeignKey("recipes.id", ondelete="CASCADE")),
    Column("actor", Text, nullable=False, server_default="system"),
    Column("channel", Text, nullable=False, server_default="web"),
    Column("props", JSONType, nullable=False, server_default="{}"),
    _created_at(),
    CheckConstraint(_in("actor", ACTORS), name="actor"),
    Index("ix_events_name_created_at", "name", "created_at"),
    Index("ix_events_project_id_created_at", "project_id", "created_at"),
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


# One checkout attempt for a book (module 13). provider_ref is the Razorpay order id.
orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")),
    Column("product", Text, nullable=False),
    Column("amount_paise", Integer, nullable=False),
    Column("currency", Text, nullable=False, server_default="INR"),
    Column("provider", Text, nullable=False, server_default="razorpay"),
    Column("provider_ref", String(64), nullable=False, unique=True),
    Column("provider_payment_id", String(64)),
    Column("status", Text, nullable=False, server_default="created"),
    Column("failure_reason", Text),
    Column("invoice_number", String(32), unique=True),
    Column("paid_at", DateTime(timezone=True)),
    Column("refunded_at", DateTime(timezone=True)),
    _created_at(),
    CheckConstraint(_in("status", ORDER_STATUSES), name="status"),
)

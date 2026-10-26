import os
from dotenv import load_dotenv

load_dotenv()

# Transcription (OpenAI). Leave the base URL empty for the default endpoint.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "") or "https://api.openai.com/v1"
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")

# Recipe structuring (Anthropic). Leave the base URL empty for the default endpoint.
# Effort: low | medium | high | xhigh | max; leave empty to use the API default
# (models before Claude 4.6, such as Sonnet 4.5, reject it, so leave it empty there).
# Temperature: leave empty to not send it. Sonnet 5.5 rejects any non-default value,
# and API version 2026-10-21 rejects it on every model.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "") or "https://api.anthropic.com"
ANTHROPIC_RECIPE_MODEL = os.getenv("ANTHROPIC_RECIPE_MODEL", "claude-sonnet-5-5")
ANTHROPIC_RECIPE_MAX_TOKENS = int(os.getenv("ANTHROPIC_RECIPE_MAX_TOKENS", "16000"))
ANTHROPIC_RECIPE_EFFORT = os.getenv("ANTHROPIC_RECIPE_EFFORT", "medium").strip() or None
_recipe_temperature = os.getenv("ANTHROPIC_RECIPE_TEMPERATURE", "").strip()
ANTHROPIC_RECIPE_TEMPERATURE = float(_recipe_temperature) if _recipe_temperature else None

# The app refuses to start with a placeholder secret key unless FLASK_DEBUG is on.
PLACEHOLDER_SECRET_KEYS = {"", "dev-secret-key", "change-me-to-a-random-string"}
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
# Hosts such as Railway set PORT; FLASK_PORT is for local runs.
FLASK_PORT = int(os.getenv("PORT") or os.getenv("FLASK_PORT", "5000"))
# User-facing product name (working name; trademark/domain not checked yet).
APP_NAME = os.getenv("APP_NAME", "Andaaz").strip() or "Andaaz"

FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}

# File storage: "local" (uploads/ and outputs/ folders) or "s3" (AWS S3 or an
# S3-compatible store such as Cloudflare R2; for R2 set the endpoint to
# https://<account-id>.r2.cloudflarestorage.com and the region to "auto").
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "") or None
S3_REGION = os.getenv("S3_REGION", "auto")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_KEY_PREFIX = os.getenv("S3_KEY_PREFIX", "")
S3_SIGNED_URL_SECONDS = int(os.getenv("S3_SIGNED_URL_SECONDS", "900"))

# Public base URL printed into QR codes, e.g. https://cookbook.example.com. Printed QRs
# can't be updated, so set this to a domain you will keep (PRD QR-4). Empty = the URL
# the request came in on, which is fine for local testing.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Raise on invalid analytics events instead of logging them (tests turn this on).
EVENTS_STRICT = os.getenv("EVENTS_STRICT", "false").lower() in {"1", "true", "yes"}

# Background jobs (RQ). Empty = run the transcribe -> structure pipeline inside the
# upload request, which is fine for local development. With a worker in a separate
# container, use STORAGE_BACKEND=s3 so the worker can read the uploaded audio.
REDIS_URL = os.getenv("REDIS_URL", "")
PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE", "pipeline")
PIPELINE_JOB_TIMEOUT_SECONDS = int(os.getenv("PIPELINE_JOB_TIMEOUT_SECONDS", "600"))

# Google OAuth (optional, for SSO)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
PROMPTS_FOLDER = os.path.join(BASE_DIR, "prompts")
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, "cookbook.db")
# Postgres when hosted (postgresql://user:pass@host/db). Empty = local SQLite file.
DATABASE_URL = os.getenv("DATABASE_URL", "") or f"sqlite:///{DATABASE_PATH}"

# Books a buyer can pick (UX R3). price_inr is what Razorpay charges (module 13); USD is display-only.
TIERS = {
    "top10": {"label": "Top 10", "recipes": 10, "price_inr": 1200, "price_usd": 22, "available": True},
    "family": {"label": "Family Edition", "recipes": 25, "price_inr": None, "price_usd": None, "available": False},
}
# While true, onboarding skips payment (invite-only pilot).
PILOT_FREE = os.getenv("PILOT_FREE", "true").strip().lower() in ("1", "true", "yes")

# Razorpay Checkout (module 13). Used only when PILOT_FREE is off and both keys are set.
# Test-mode keys (rzp_test_…) take no real money.
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
RAZORPAY_API_URL = os.getenv("RAZORPAY_API_URL", "https://api.razorpay.com/v1").rstrip("/")

# Who the invoice is from. With no GSTIN it is a plain receipt; with one, a tax invoice
# that splits out GST at GST_RATE_PERCENT (prices are GST-inclusive).
SELLER_NAME = os.getenv("SELLER_NAME", "").strip() or APP_NAME
SELLER_ADDRESS = os.getenv("SELLER_ADDRESS", "").strip()
SELLER_GSTIN = os.getenv("SELLER_GSTIN", "").strip()
SELLER_SAC = os.getenv("SELLER_SAC", "").strip()
SELLER_STATE = os.getenv("SELLER_STATE", "").strip()
GST_RATE_PERCENT = float(os.getenv("GST_RATE_PERCENT", "18"))
INVOICE_PREFIX = os.getenv("INVOICE_PREFIX", "AZ").strip() or "AZ"

# The legacy /projects pages list these; the book styles themselves live in services/book_design.py.
COOKBOOK_THEMES = {
    "classic": {"name": "Heirloom"},
    "rustic": {"name": "Rasoi diary"},
    "modern": {"name": "Modern kitchen"},
    "festive": {"name": "Utsav"},
}

import os
from dotenv import load_dotenv

load_dotenv()

# Transcription (OpenAI). Leave the base URL empty for the default endpoint.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "") or "https://api.openai.com/v1"
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")

# Recipe structuring (Anthropic). Leave the base URL empty for the default endpoint.
# Leave the temperature empty to not send it (required on API version 2026-10-21).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "") or "https://api.anthropic.com"
ANTHROPIC_RECIPE_MODEL = os.getenv("ANTHROPIC_RECIPE_MODEL", "claude-sonnet-4-5-20250929")
ANTHROPIC_RECIPE_MAX_TOKENS = int(os.getenv("ANTHROPIC_RECIPE_MAX_TOKENS", "4096"))
_recipe_temperature = os.getenv("ANTHROPIC_RECIPE_TEMPERATURE", "0.3").strip()
ANTHROPIC_RECIPE_TEMPERATURE = float(_recipe_temperature) if _recipe_temperature else None

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() in {"1", "true", "yes"}

# Google OAuth (optional, for SSO)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
PROMPTS_FOLDER = os.path.join(BASE_DIR, "prompts")
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, "cookbook.db")

COOKBOOK_THEMES = {
    "classic": {"name": "Classic Indian", "primary": "#5c1a1a", "accent": "#d4a84b", "bg": "#fdf8f0"},
    "modern": {"name": "Modern Minimal", "primary": "#2c3e50", "accent": "#e74c3c", "bg": "#ffffff"},
    "rustic": {"name": "Rustic Warmth", "primary": "#6b4226", "accent": "#d4a017", "bg": "#faf3e8"},
    "elegant": {"name": "Elegant Gold", "primary": "#1a1a2e", "accent": "#c9a961", "bg": "#f8f6f0"},
    "fresh": {"name": "Fresh & Green", "primary": "#2d6a4f", "accent": "#95d5b2", "bg": "#f0faf5"},
}

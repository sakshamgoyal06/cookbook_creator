import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
ANTHROPIC_RECIPE_MODEL = os.getenv("ANTHROPIC_RECIPE_MODEL", "claude-sonnet-4-20250514")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Google OAuth (optional, for SSO)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
PROMPTS_FOLDER = os.path.join(BASE_DIR, "prompts")
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, "cookbook.db")

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".mp4", ".wav", ".ogg"}

COOKBOOK_THEMES = {
    "classic": {"name": "Classic Indian", "primary": "#5c1a1a", "accent": "#d4a84b", "bg": "#fdf8f0"},
    "modern": {"name": "Modern Minimal", "primary": "#2c3e50", "accent": "#e74c3c", "bg": "#ffffff"},
    "rustic": {"name": "Rustic Warmth", "primary": "#6b4226", "accent": "#d4a017", "bg": "#faf3e8"},
    "elegant": {"name": "Elegant Gold", "primary": "#1a1a2e", "accent": "#c9a961", "bg": "#f8f6f0"},
    "fresh": {"name": "Fresh & Green", "primary": "#2d6a4f", "accent": "#95d5b2", "bg": "#f0faf5"},
}

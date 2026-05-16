import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
OPENAI_RECIPE_MODEL = os.getenv("OPENAI_RECIPE_MODEL", "gpt-4.1")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
PROMPTS_FOLDER = os.path.join(BASE_DIR, "prompts")
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, "cookbook.db")

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg"}

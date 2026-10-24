"""Production entry point: `gunicorn wsgi:app` (see Dockerfile).

Migrations run once before gunicorn starts (`python wsgi.py migrate`), not here,
so several workers never migrate the database at the same time.
"""
import os
import sys

import config
from app import app  # noqa: F401
from models.database import init_db

for folder in (config.UPLOAD_FOLDER, config.OUTPUT_FOLDER, config.INSTANCE_FOLDER):
    os.makedirs(folder, exist_ok=True)

if __name__ == "__main__" and sys.argv[1:] == ["migrate"]:
    init_db()
    print("Database is up to date.")

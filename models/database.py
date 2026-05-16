import sqlite3
import os
import config


def get_connection():
    os.makedirs(config.INSTANCE_FOLDER, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id TEXT UNIQUE NOT NULL,
            audio_filename TEXT,
            raw_transcript TEXT,
            recipe_title TEXT,
            alternate_names_json TEXT DEFAULT '[]',
            category TEXT,
            family_note TEXT,
            serves TEXT,
            prep_time_minutes INTEGER,
            cook_time_minutes INTEGER,
            difficulty TEXT,
            ingredients_json TEXT DEFAULT '[]',
            method_steps_json TEXT DEFAULT '[]',
            moms_tips_json TEXT DEFAULT '[]',
            serving_suggestion TEXT,
            storage_notes TEXT,
            unclear_items_for_review_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'uploaded',
            pdf_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

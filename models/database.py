import sqlite3
import os
import config


def get_connection():
    os.makedirs(config.INSTANCE_FOLDER, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT,
            auth_provider TEXT DEFAULT 'email',
            auth_provider_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT DEFAULT '',
            description TEXT DEFAULT '',
            theme TEXT DEFAULT 'classic',
            max_recipes INTEGER DEFAULT 50,
            max_pages INTEGER DEFAULT 100,
            acknowledgement TEXT DEFAULT '',
            about_author TEXT DEFAULT '',
            dedication TEXT DEFAULT '',
            introduction TEXT DEFAULT '',
            cover_note TEXT DEFAULT '',
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
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
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    conn.commit()
    conn.close()

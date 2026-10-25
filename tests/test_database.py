"""Migration tests. They run on SQLite always, and on Postgres too when
TEST_POSTGRES_URL points at a throwaway database (CI sets it)."""
import json
import os
import sqlite3

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from models.database import alembic_config, get_engine, init_db, normalize_url
from models.schema import metadata

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "")

# The tables exactly as the pre-migration init_db() made them.
LEGACY_SQLITE_DDL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    password_hash TEXT, auth_provider TEXT DEFAULT 'email', auth_provider_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL,
    subtitle TEXT DEFAULT '', description TEXT DEFAULT '', theme TEXT DEFAULT 'classic',
    max_recipes INTEGER DEFAULT 50, max_pages INTEGER DEFAULT 100, acknowledgement TEXT DEFAULT '',
    about_author TEXT DEFAULT '', dedication TEXT DEFAULT '', introduction TEXT DEFAULT '',
    cover_note TEXT DEFAULT '', status TEXT DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id));
CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, recipe_id TEXT UNIQUE NOT NULL,
    audio_filename TEXT, raw_transcript TEXT, recipe_title TEXT, alternate_names_json TEXT DEFAULT '[]',
    category TEXT, family_note TEXT, serves TEXT, prep_time_minutes INTEGER, cook_time_minutes INTEGER,
    difficulty TEXT, ingredients_json TEXT DEFAULT '[]', method_steps_json TEXT DEFAULT '[]',
    moms_tips_json TEXT DEFAULT '[]', serving_suggestion TEXT, storage_notes TEXT,
    unclear_items_for_review_json TEXT DEFAULT '[]', status TEXT DEFAULT 'uploaded', pdf_filename TEXT,
    sort_order INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (project_id) REFERENCES projects(id));
"""


def _reset_postgres(url):
    with get_engine(url).begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")


@pytest.fixture(params=["sqlite", "postgres"])
def db_url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'migrations.db'}"
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL not set")
    url = normalize_url(POSTGRES_URL)
    _reset_postgres(url)
    return url


def _schema_diffs(url):
    with get_engine(url).connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), metadata)
    # SQLite reports INTEGER PRIMARY KEY as nullable; it can't hold NULL, so ignore that.
    return [
        d for d in diffs
        if not (isinstance(d, list) and d[0][0] == "modify_nullable" and d[0][3] == "id")
    ]


def _seed_legacy_rows(conn):
    conn.execute("INSERT INTO users (email, name) VALUES ('a@example.com', 'Aarav')")
    conn.execute("INSERT INTO projects (user_id, title, updated_at) VALUES (1, 'Book', "
                 "'2026-10-20T10:11:12.123456+00:00')")
    rows = [
        ("u1", "a.m4a", "uploaded", None),
        ("u2", "b.m4a", "needs_review", None),
        ("u3", "c.m4a", "pdf_generated", "u3_dal.pdf"),
        ("u4", None, "approved", None),
    ]
    for recipe_id, audio, status, pdf in rows:
        conn.execute(
            "INSERT INTO recipes (project_id, recipe_id, audio_filename, ingredients_json, status, pdf_filename) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (recipe_id, audio, json.dumps([{"item": "दाल"}]), status, pdf),
        )


def test_migrations_match_schema(db_url):
    init_db(db_url)
    assert _schema_diffs(db_url) == []


def test_downgrade_to_baseline_and_back(db_url):
    init_db(db_url)
    cfg = alembic_config(db_url)
    command.downgrade(cfg, "0001")
    command.upgrade(cfg, "head")
    assert _schema_diffs(db_url) == []


def test_legacy_sqlite_database_is_upgraded(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SQLITE_DDL)
    _seed_legacy_rows(conn)
    conn.commit()
    conn.close()

    url = f"sqlite:///{path}"
    init_db(url)

    assert _schema_diffs(url) == []
    with get_engine(url).connect() as conn:
        statuses = conn.execute(sa.text("SELECT recipe_id, status FROM recipes ORDER BY id")).all()
        audio = conn.execute(sa.text("SELECT recipe_id, storage_key FROM recipe_audio ORDER BY recipe_id")).all()
        pdfs = conn.execute(sa.text("SELECT recipe_id, storage_key FROM generated_files")).all()
        tokens = conn.execute(sa.text("SELECT listen_token FROM recipes")).scalars().all()
        updated = conn.execute(sa.text("SELECT updated_at FROM projects")).scalar_one()
        ingredients = conn.execute(sa.text("SELECT ingredients_json FROM recipes WHERE id = 1")).scalar_one()
    assert [s for _, s in statuses] == ["received", "needs_review", "approved", "approved"]
    assert audio == [(1, "a.m4a"), (2, "b.m4a"), (3, "c.m4a")]
    assert pdfs == [(3, "u3_dal.pdf")]
    assert len(set(tokens)) == 4 and all(len(t) >= 22 for t in tokens)
    assert updated == "2026-10-20 10:11:12"
    assert json.loads(ingredients) == [{"item": "दाल"}]
    with get_engine(url).connect() as conn:
        modes = conn.execute(sa.text("SELECT cook_mode, cook_token FROM projects")).all()
        buyers = conn.execute(sa.text("SELECT role FROM family_members")).scalars().all()
        dishes = conn.execute(sa.text("SELECT recipe_id, status FROM dishes ORDER BY recipe_id")).all()
    assert [m for m, _ in modes] == ["self"] and all(len(t) >= 22 for _, t in modes)
    assert buyers == ["buyer"]
    assert [s for _, s in dishes] == ["in_progress", "in_progress", "done", "done"]


def test_constraints(db_url):
    init_db(db_url)
    engine = get_engine(db_url)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO users (email, name) VALUES ('a@example.com', 'A')"))
        conn.execute(sa.text(
            "INSERT INTO projects (user_id, title, book_token, cook_token) VALUES (1, 'B', 'bt', 'ct')"
        ))
        conn.execute(sa.text(
            "INSERT INTO recipes (project_id, recipe_id, listen_token, status) VALUES (1, 'r', 'lt', 'received')"
        ))
        conn.execute(sa.text("INSERT INTO recipe_audio (recipe_id, storage_key) VALUES (1, 'a.m4a')"))

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE recipes SET status = 'pdf_generated'"))

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO recipes (project_id, recipe_id, listen_token) VALUES (1, 'r2', 'lt')"
            ))

    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM projects"))
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM recipes")).scalar_one() == 0
        assert conn.execute(sa.text("SELECT count(*) FROM recipe_audio")).scalar_one() == 0

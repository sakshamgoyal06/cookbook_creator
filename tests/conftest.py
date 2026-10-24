import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from models.database import get_connection, init_db  # noqa: E402

SAMPLE_RECIPE = {
    "recipe_title": "Rajma",
    "alternate_names": ["Rajma Masala"],
    "category": "Main",
    "family_note": "Sunday lunch",
    "serves": "4",
    "prep_time_minutes": None,
    "cook_time_minutes": 40,
    "difficulty": "Easy",
    "ingredients": [{"item": "rajma", "quantity": "1", "unit": "cup", "preparation_note": "soaked overnight"}],
    "method_steps": [
        {"step_number": 1, "instruction": "Pressure cook", "flame_level": "high", "timing": "5 whistles",
         "sensory_cue": ""}
    ],
    "moms_tips": ["Add ghee at the end"],
    "serving_suggestion": "With rice",
    "storage_notes": "",
    "unclear_items_for_review": ["thoda sa namak"],
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    # DATABASE_URL is what the upcoming database layer reads; DATABASE_PATH is what the
    # current SQLite code reads. Setting both keeps the fixture working across that change.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(config, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(config, "INSTANCE_FOLDER", str(tmp_path))
    for name in ("UPLOAD_FOLDER", "OUTPUT_FOLDER"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setattr(config, name, str(folder))

    import app as app_module

    init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email="mom@example.com", name="Aarav", password="secret123"):
    return client.post(
        "/register",
        data={"email": email, "name": name, "password": password, "confirm_password": password},
    )


@pytest.fixture
def auth_client(client):
    register(client)
    return client


def create_project(client, title="Mom's Kitchen"):
    response = client.post("/projects/new", data={"title": title})
    return int(response.headers["Location"].rstrip("/").split("/")[-1])


def insert_recipe(project_id, title="Rajma", status="needs_review"):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO recipes (project_id, recipe_id, recipe_title, status) VALUES (?, ?, ?, ?)",
        (project_id, f"r-{title}-{project_id}", title, status),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id

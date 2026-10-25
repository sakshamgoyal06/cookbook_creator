import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The app refuses to start with a placeholder secret key outside debug mode.
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

import config  # noqa: E402
from models.database import get_engine, init_db, new_token  # noqa: E402
from models.schema import recipes  # noqa: E402

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
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(config, "INSTANCE_FOLDER", str(tmp_path))
    monkeypatch.setattr(config, "EVENTS_STRICT", True)
    for name in ("UPLOAD_FOLDER", "OUTPUT_FOLDER"):
        folder = tmp_path / name.lower()
        folder.mkdir()
        monkeypatch.setattr(config, name, str(folder))

    import app as app_module

    init_db()
    app_module.app.config["TESTING"] = True
    # CSRF has its own tests (test_security.py); the other tests post forms without tokens.
    monkeypatch.setitem(app_module.app.config, "WTF_CSRF_ENABLED", False)
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
    with get_engine().begin() as conn:
        return conn.execute(
            recipes.insert()
            .values(
                project_id=project_id,
                recipe_id=f"r-{title}-{project_id}",
                listen_token=new_token(),
                recipe_title=title,
                status=status,
            )
            .returning(recipes.c.id)
        ).scalar_one()

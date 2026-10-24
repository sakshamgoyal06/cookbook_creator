import io

from conftest import SAMPLE_RECIPE, create_project
from sqlalchemy import select

from models.database import get_engine
from models.schema import pipeline_runs
from services import ai_service, recipe_service


def _upload(client, project_id, filename="note.m4a", mimetype="audio/m4a"):
    return client.post(
        f"/projects/{project_id}/upload",
        data={"audio_file": (io.BytesIO(b"fake audio"), filename, mimetype)},
        content_type="multipart/form-data",
    )


def test_upload_transcribes_structures_and_saves(auth_client, monkeypatch):
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma banane ke liye...")
    monkeypatch.setattr(ai_service, "structure_recipe", lambda transcript: SAMPLE_RECIPE)
    project_id = create_project(auth_client)

    response = _upload(auth_client, project_id)

    assert response.status_code == 302
    recipe_id = int(response.headers["Location"].rstrip("/").split("/")[-1])
    recipe = recipe_service.get_recipe(recipe_id)
    assert recipe["project_id"] == project_id
    assert recipe["recipe_title"] == "Rajma"
    assert recipe["raw_transcript"] == "Rajma banane ke liye..."
    assert recipe["unclear_items_for_review"] == ["thoda sa namak"]
    assert recipe["status"] == "needs_review"


def test_upload_rejects_non_audio(auth_client):
    project_id = create_project(auth_client)
    response = _upload(auth_client, project_id, filename="notes.txt", mimetype="text/plain")
    assert response.headers["Location"].endswith(f"/projects/{project_id}/upload")
    assert recipe_service.get_project_recipes(project_id) == []


def test_upload_failure_shows_friendly_message_and_logs_error(auth_client, monkeypatch):
    def fail(transcript):
        raise ValueError("The AI declined to structure this transcript.")

    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "some words")
    monkeypatch.setattr(ai_service, "structure_recipe", fail)
    project_id = create_project(auth_client)

    response = _upload(auth_client, project_id)
    assert response.headers["Location"].endswith(f"/projects/{project_id}/upload")
    page = auth_client.get(response.headers["Location"])
    assert b"couldn&#39;t turn this recording into a recipe" in page.data
    assert b"declined to structure" not in page.data

    [recipe] = recipe_service.get_project_recipes(project_id)
    assert recipe["status"] == "failed"
    assert recipe["raw_transcript"] == "some words"
    with get_engine().connect() as conn:
        runs = conn.execute(select(pipeline_runs).order_by(pipeline_runs.c.id)).mappings().all()
    assert [(r["stage"], r["status"]) for r in runs] == [("transcribe", "succeeded"), ("structure", "failed")]
    assert "declined to structure" in runs[1]["error"]

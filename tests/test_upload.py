import io

from conftest import SAMPLE_RECIPE, create_project
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


def test_upload_shows_structuring_error(auth_client, monkeypatch):
    def fail(transcript):
        raise ValueError("The AI declined to structure this transcript.")

    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "some words")
    monkeypatch.setattr(ai_service, "structure_recipe", fail)
    project_id = create_project(auth_client)

    response = _upload(auth_client, project_id)
    assert response.headers["Location"].endswith(f"/projects/{project_id}/upload")
    page = auth_client.get(response.headers["Location"])
    assert b"declined to structure" in page.data
    assert recipe_service.get_project_recipes(project_id) == []

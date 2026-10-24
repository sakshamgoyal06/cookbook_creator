import os
import re
import subprocess
import sys

import pytest

from conftest import SAMPLE_RECIPE, create_project, register
from services import recipe_service

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_pdf_recipe(client):
    project_id = create_project(client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    client.post(f"/projects/{project_id}/recipes/{row_id}/generate-pdf")
    return project_id, row_id, recipe_service.get_recipe(row_id)["pdf_filename"]


def test_other_user_cannot_download_pdf(client, monkeypatch):
    register(client, email="owner@example.com")
    project_id, row_id, pdf_filename = _make_pdf_recipe(client)
    client.get("/logout")

    register(client, email="intruder@example.com")
    response = client.get(f"/projects/{project_id}/recipes/{row_id}/pdf")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    # The old filename-based route is gone.
    assert client.get(f"/outputs/{pdf_filename}").status_code == 404


def test_pdf_route_without_pdf_redirects(auth_client):
    project_id = create_project(auth_client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    response = auth_client.get(f"/projects/{project_id}/recipes/{row_id}/pdf")
    assert response.headers["Location"].endswith(f"/projects/{project_id}")


@pytest.fixture
def csrf_client(app, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    return app.test_client()


def test_post_without_csrf_token_is_rejected(csrf_client):
    response = csrf_client.post(
        "/register",
        data={"email": "a@x.com", "name": "A", "password": "secret123", "confirm_password": "secret123"},
    )
    assert response.status_code == 400


def _token(page):
    match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert match, "form has no csrf_token field"
    return match.group(1).decode()


def test_forms_work_with_csrf_token(csrf_client):
    token = _token(csrf_client.get("/register"))
    response = csrf_client.post(
        "/register",
        data={"email": "a@x.com", "name": "A", "password": "secret123",
              "confirm_password": "secret123", "csrf_token": token},
    )
    assert response.headers["Location"].endswith("/dashboard")

    token = _token(csrf_client.get("/projects/new"))
    response = csrf_client.post("/projects/new", data={"title": "Mom's Kitchen", "csrf_token": token})
    project_id = int(response.headers["Location"].rstrip("/").split("/")[-1])
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)

    token = _token(csrf_client.get(f"/projects/{project_id}/recipes/{row_id}"))
    csrf_client.post(f"/projects/{project_id}/recipes/{row_id}/approve", data={"csrf_token": token})
    assert recipe_service.get_recipe(row_id)["status"] == "approved"


def _import_app(env):
    return subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("secret", ["dev-secret-key", "change-me-to-a-random-string", ""])
def test_placeholder_secret_key_refused_without_debug(secret):
    result = _import_app({"FLASK_DEBUG": "false", "FLASK_SECRET_KEY": secret})
    assert result.returncode != 0
    assert "FLASK_SECRET_KEY" in result.stderr


def test_placeholder_secret_key_allowed_in_debug():
    assert _import_app({"FLASK_DEBUG": "true", "FLASK_SECRET_KEY": "dev-secret-key"}).returncode == 0


def test_real_secret_key_starts_without_debug():
    assert _import_app({"FLASK_DEBUG": "false", "FLASK_SECRET_KEY": "x" * 64}).returncode == 0

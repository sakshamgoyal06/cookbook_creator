import json

from conftest import SAMPLE_RECIPE, create_project, insert_recipe, register
from services import project_service, recipe_service


def test_project_crud(auth_client):
    project_id = create_project(auth_client, "Mom's Kitchen")
    assert auth_client.get(f"/projects/{project_id}").status_code == 200
    assert auth_client.get(f"/projects/{project_id}/edit").status_code == 200

    response = auth_client.post(f"/projects/{project_id}/edit", data={"title": "Nani's Kitchen"})
    assert response.headers["Location"].endswith(f"/projects/{project_id}")
    assert project_service.get_project(project_id)["title"] == "Nani's Kitchen"

    auth_client.post(f"/projects/{project_id}/delete")
    assert project_service.get_project(project_id) is None


def test_project_requires_title(auth_client):
    response = auth_client.post("/projects/new", data={"title": "  "})
    assert response.headers["Location"].endswith("/projects/new")


def test_other_users_project_is_not_accessible(client):
    register(client, email="owner@example.com")
    project_id = create_project(client)
    recipe_id = insert_recipe(project_id)
    client.get("/logout")

    register(client, email="intruder@example.com")
    for path in (
        f"/projects/{project_id}",
        f"/projects/{project_id}/edit",
        f"/projects/{project_id}/upload",
        f"/projects/{project_id}/recipes/{recipe_id}",
        f"/projects/{project_id}/recipes/{recipe_id}/edit",
    ):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.headers["Location"].endswith("/dashboard"), path

    client.post(f"/projects/{project_id}/delete")
    client.post(f"/projects/{project_id}/recipes/{recipe_id}/approve")
    assert project_service.get_project(project_id) is not None
    assert recipe_service.get_recipe(recipe_id)["status"] == "needs_review"


def test_recipe_from_another_project_is_not_accessible(auth_client):
    first = create_project(auth_client, "First")
    second = create_project(auth_client, "Second")
    recipe_id = insert_recipe(first)

    response = auth_client.post(f"/projects/{second}/recipes/{recipe_id}/approve")
    assert response.headers["Location"].endswith(f"/projects/{second}")
    assert recipe_service.get_recipe(recipe_id)["status"] == "needs_review"


def test_recipe_view_edit_and_approve(auth_client):
    project_id = create_project(auth_client)
    recipe_id = insert_recipe(project_id)
    base = f"/projects/{project_id}/recipes/{recipe_id}"

    assert auth_client.get(base).status_code == 200
    assert auth_client.get(f"{base}/edit").status_code == 200

    form = {
        "recipe_title": "Rajma Chawal",
        "prep_time_minutes": "15",
        "ingredients_json": json.dumps([{"item": "rajma", "quantity": "1", "unit": "cup", "preparation_note": ""}]),
        "method_steps_json": "[]",
        "moms_tips_json": "[]",
        "unclear_items_for_review_json": "[]",
    }
    auth_client.post(f"{base}/edit", data=form)
    recipe = recipe_service.get_recipe(recipe_id)
    assert recipe["recipe_title"] == "Rajma Chawal"
    assert recipe["prep_time_minutes"] == 15
    assert recipe["ingredients"][0]["item"] == "rajma"

    auth_client.post(f"{base}/approve")
    assert recipe_service.get_recipe(recipe_id)["status"] == "approved"


def test_recipe_edit_rejects_invalid_json(auth_client):
    project_id = create_project(auth_client)
    recipe_id = insert_recipe(project_id)
    base = f"/projects/{project_id}/recipes/{recipe_id}"

    response = auth_client.post(f"{base}/edit", data={"recipe_title": "X", "ingredients_json": "not json"})
    assert response.headers["Location"].endswith(f"{base}/edit")
    assert recipe_service.get_recipe(recipe_id)["recipe_title"] == "Rajma"


def test_generate_pdf(auth_client):
    project_id = create_project(auth_client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)

    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/generate-pdf")

    recipe = recipe_service.get_recipe(row_id)
    assert recipe["pdf_filename"]
    response = auth_client.get(f"/projects/{project_id}/recipes/{row_id}/pdf")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")

from conftest import SAMPLE_RECIPE, create_project
from services import recipe_service


def test_save_and_read_back(auth_client):
    project_id = create_project(auth_client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "transcript", SAMPLE_RECIPE)

    recipe = recipe_service.get_recipe(row_id)
    assert [clip["storage_key"] for clip in recipe["audio_clips"]] == ["abc.m4a"]
    assert len(recipe["listen_token"]) >= 22
    assert recipe["alternate_names"] == ["Rajma Masala"]
    assert recipe["ingredients"] == SAMPLE_RECIPE["ingredients"]
    assert recipe["method_steps"] == SAMPLE_RECIPE["method_steps"]
    assert recipe["prep_time_minutes"] is None
    assert recipe["cook_time_minutes"] == 40
    assert [r["id"] for r in recipe_service.get_project_recipes(project_id)] == [row_id]


def test_missing_recipe_returns_none(app):
    assert recipe_service.get_recipe(999) is None


def test_mark_pdf_generated(auth_client):
    project_id = create_project(auth_client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    recipe_service.mark_pdf_generated(row_id, "rajma.pdf")
    recipe = recipe_service.get_recipe(row_id)
    # A PDF is a file, not a review state: the recipe keeps its status.
    assert recipe["status"] == "needs_review"
    assert recipe["pdf_filename"] == "rajma.pdf"

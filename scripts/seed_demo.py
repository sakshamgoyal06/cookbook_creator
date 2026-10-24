"""Create a demo login with one project and three recipes.

    python3 scripts/seed_demo.py        # then log in as demo@example.com / demo1234
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import init_db  # noqa: E402
from services import project_service, recipe_service, user_service  # noqa: E402

EMAIL = "demo@example.com"
PASSWORD = "demo1234"

RECIPES = [
    {
        "recipe_title": "Rajma",
        "category": "Main",
        "serves": "4",
        "cook_time_minutes": 40,
        "ingredients": [{"item": "rajma", "quantity": "1", "unit": "cup", "preparation_note": "soaked overnight"}],
        "method_steps": [{"step_number": 1, "instruction": "Pressure cook for 5 whistles"}],
        "moms_tips": ["Add ghee at the end"],
        "unclear_items_for_review": ["thoda sa namak"],
    },
    {
        "recipe_title": "Aloo Paratha",
        "category": "Breakfast",
        "serves": "3",
        "ingredients": [{"item": "potato", "quantity": "4", "unit": "", "preparation_note": "boiled"}],
        "method_steps": [{"step_number": 1, "instruction": "Mash the potatoes with spices"}],
    },
    {
        "recipe_title": "Kheer",
        "category": "Dessert",
        "serves": "6",
        "ingredients": [{"item": "milk", "quantity": "1", "unit": "litre", "preparation_note": "full cream"}],
        "method_steps": [{"step_number": 1, "instruction": "Simmer the rice in milk until thick"}],
    },
]


def main():
    init_db()
    if user_service.get_user_by_email(EMAIL):
        print(f"{EMAIL} already exists; nothing to do.")
        return
    user = user_service.create_user(EMAIL, "Demo Buyer", PASSWORD)
    project_id = project_service.create_project(user["id"], "Mummy's Kitchen", subtitle="Volume 1")
    for recipe in RECIPES:
        recipe_service.save_uploaded_recipe(project_id, None, "Demo transcript", recipe)
    print(f"Log in as {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()

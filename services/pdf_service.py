import os
import re
from flask import render_template
from weasyprint import HTML
import config


def generate_recipe_pdf(recipe: dict) -> str:
    html_content = render_template("cookbook_recipe_template.html", recipe=recipe)

    slug = _slugify(recipe.get("recipe_title", "recipe"))
    recipe_id = recipe.get("recipe_id", "unknown")
    filename = f"{recipe_id}_{slug}.pdf"
    output_path = os.path.join(config.OUTPUT_FOLDER, filename)

    css_path = os.path.join(config.BASE_DIR, "static", "cookbook.css")
    HTML(string=html_content).write_pdf(
        output_path,
        stylesheets=[css_path] if os.path.exists(css_path) else [],
    )
    return filename


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60]

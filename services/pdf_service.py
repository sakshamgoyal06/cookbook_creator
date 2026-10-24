import os
import re
import tempfile
from flask import render_template
from weasyprint import HTML
import config
from services import storage_service


def generate_recipe_pdf(recipe: dict) -> str:
    html_content = render_template("cookbook_recipe_template.html", recipe=recipe)

    slug = _slugify(recipe.get("recipe_title", "recipe"))
    recipe_id = recipe.get("recipe_id", "unknown")
    filename = f"{recipe_id}_{slug}.pdf"

    css_path = os.path.join(config.BASE_DIR, "static", "cookbook.css")
    handle, temp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    try:
        HTML(string=html_content).write_pdf(
            temp_path,
            stylesheets=[css_path] if os.path.exists(css_path) else [],
        )
        storage_service.save_file("pdfs", filename, temp_path, content_type="application/pdf")
    finally:
        os.remove(temp_path)
    return filename


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60]

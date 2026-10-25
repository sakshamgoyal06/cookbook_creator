import os
import re
import tempfile
import uuid
from flask import render_template
from weasyprint import HTML
import config
from services import listen_service, project_service, qr_service, storage_service


def generate_recipe_pdf(recipe: dict) -> str:
    listen_url = _listen_url(recipe)
    voice, label = _names(recipe.get("project_id"))
    html_content = render_template(
        "cookbook_recipe_template.html",
        recipe=recipe,
        listen_url=listen_url,
        qr_data_uri=_qr_for(recipe) if listen_url else None,
        voice_name=voice,
        cook_label=label,
    )

    slug = _slugify(recipe.get("recipe_title", "recipe"))
    recipe_id = recipe.get("recipe_id", "unknown")
    filename = f"{recipe_id}_{slug}.pdf"
    _write_pdf(html_content, filename)
    return filename


def generate_book_pdf(project: dict, recipes: list) -> str:
    """The whole book (BOOK-1/BOOK-2): cover, dedication, contents, one page per approved recipe, closing."""
    voice, label = _names(project["id"])
    pages = []
    for recipe in recipes:
        url = _listen_url(recipe)
        pages.append({"recipe": recipe, "listen_url": url, "qr": _qr_for(recipe) if url else None})
    html_content = render_template(
        "pdf/book.html", project=project, pages=pages, voice_name=voice, cook_label=label,
        book_qr=qr_service.make_qr_data_uri(listen_service.book_url(project["book_token"]), scale=10),
    )
    filename = f"book-{project['id']}-{uuid.uuid4().hex[:12]}_{_slugify(project['title'])}.pdf"
    _write_pdf(html_content, filename)
    return filename


def _listen_url(recipe):
    if recipe.get("listen_token") and not recipe.get("listen_revoked_at") and recipe.get("audio_clips"):
        return listen_service.listen_url(recipe["listen_token"])
    return None


def _names(project_id):
    """("Sunita ji", "Mummy") for the page's Listen line and tips heading."""
    project = project_service.get_project(project_id) if project_id else None
    if not project:
        return None, None
    voice = listen_service.voice_name({"storyteller_name": project.get("storyteller_name"),
                                       "cook_mode": project.get("cook_mode")})
    label = None if project.get("cook_mode") == "self" else (project.get("storyteller_address_as") or voice)
    return voice, label


def _write_pdf(html_content, filename):
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


def _qr_for(recipe):
    return qr_service.make_qr_data_uri(listen_service.listen_url(recipe["listen_token"], source="qr"), scale=10)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60]

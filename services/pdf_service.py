import os
import re
import tempfile
import uuid
from flask import render_template
from weasyprint import HTML
import config
from services import book_design, listen_service, photo_service, project_service, qr_service, storage_service

# A rough measure of how much of an A4 page a recipe fills (see _page); past this its photo
# moves to a page of its own instead of sharing the page.
PHOTO_SHARES_PAGE_UP_TO = 17
# Chapters (section dividers) only make sense once a book has a few recipes in more than one kind.
MIN_RECIPES_FOR_CHAPTERS = 4
# The order chapters appear in when the categories match; anything else follows in recipe order.
CHAPTER_ORDER = ("breakfast", "snack", "starter", "dal", "sabzi", "curry", "main", "rice", "bread", "roti",
                 "side", "chutney", "pickle", "achaar", "sweet", "dessert", "mithai", "drink")


def generate_recipe_pdf(recipe: dict) -> str:
    project = project_service.get_project(recipe["project_id"]) if recipe.get("project_id") else None
    voice, label = _names(project)
    html_content = render_template(
        "pdf/recipe.html", page=_page(recipe, project),
        voice_name=voice, cook_label=label,
        page_css=book_design.page_css(project), body_classes=book_design.body_classes(project),
    )
    slug = _slugify(recipe.get("recipe_title", "recipe"))
    filename = f"{recipe.get('recipe_id', 'unknown')}_{slug}.pdf"
    _write_pdf(html_content, filename, project)
    return filename


def generate_book_pdf(project: dict, recipes: list, print_ready=False) -> str:
    """The whole book (BOOK-1/BOOK-2, module 18) in the project's style and size.

    print_ready adds 3 mm bleed and crop marks for a print shop; the default is the screen PDF.
    """
    filename = f"book-{project['id']}-{uuid.uuid4().hex[:12]}_{_slugify(project['title'])}.pdf"
    _write_pdf(render_book_html(project, recipes, print_ready), filename, project)
    return filename


def render_book_html(project, recipes, print_ready=False):
    voice, label = _names(project)
    sections = _sections([_page(r, project) for r in recipes])
    reveal = project.get("reveal_date")
    layout = book_design.cover_layout(project)
    crops = project.get("photo_crops") or {}

    def photo(field, slot, place):
        return photo_service.data_uri(project.get(field), book_design.photo_frame(project, place), crops.get(slot))
    return render_template(
        "pdf/book.html", project=project, sections=sections,
        show_dividers=len(sections) > 1 and len(recipes) >= MIN_RECIPES_FOR_CHAPTERS,
        voice_name=voice, cook_label=label, cook_name=project.get("storyteller_name"),
        kicker=_kicker(project), year=reveal.year if reveal else None,
        layout=layout,
        cover_photo=photo("cook_photo_key", "cook", "cover") if layout == "photo" else None,
        about_photo=photo("cook_photo_key", "cook", "about"),
        family_photo=photo("family_photo_key", "family", "family"),
        book_qr=qr_service.make_qr_data_uri(listen_service.book_url(project["book_token"]), scale=10),
        page_css=book_design.page_css(project, print_ready), body_classes=book_design.body_classes(project),
    )


def dish_photo_place(project, recipe):
    """Where a dish photo goes: "dish_page" (a page of its own) or "dish" (a band on the recipe page).

    Always its own page in the wide book (photo on the left page, recipe on the right), and on A4
    when the recipe is too long to share its page.
    """
    if book_design.size_key(project) == "wide":
        return "dish_page"
    steps = recipe.get("method_steps") or []
    size = (len(recipe.get("ingredients") or []) + len(recipe.get("moms_tips") or [])
            + sum(1 + len(s.get("instruction") or "") // 90 for s in steps)
            + (2 if recipe.get("family_note") else 0) + (2 if recipe.get("serving_suggestion") else 0))
    return "dish_page" if size > PHOTO_SHARES_PAGE_UP_TO else "dish"


def _page(recipe, project):
    url = _listen_url(recipe)
    place = dish_photo_place(project, recipe)
    photo = photo_service.data_uri(recipe.get("photo_key"), book_design.photo_frame(project, place),
                                   recipe.get("photo_crop"))
    return {"recipe": recipe, "listen_url": url, "qr": _qr_for(recipe) if url else None, "photo": photo,
            "wide": book_design.size_key(project) == "wide", "photo_page": bool(photo) and place == "dish_page"}


def _sections(pages):
    """Recipes grouped into chapters by category, in kitchen order where the names allow."""
    groups = {}
    for page in pages:
        title = (page["recipe"].get("category") or "").strip().capitalize() or "More recipes"
        groups.setdefault(title, []).append(page)

    def rank(entry):
        index, (title, _) = entry
        name = title.lower()
        return next((i for i, word in enumerate(CHAPTER_ORDER) if word in name), len(CHAPTER_ORDER)), index

    ordered = sorted(enumerate(groups.items()), key=rank)
    return [{"title": title, "pages": group} for _, (title, group) in ordered]


def _kicker(project):
    occasion = project.get("occasion")
    if occasion and occasion != "Just because":
        return f"A family cookbook for {occasion}"
    return "A family cookbook"


def _listen_url(recipe):
    if recipe.get("listen_token") and not recipe.get("listen_revoked_at") and recipe.get("audio_clips"):
        return listen_service.listen_url(recipe["listen_token"])
    return None


def _names(project):
    """("Sunita ji", "Mummy") for the page's Listen line and tips heading."""
    if not project:
        return None, None
    voice = listen_service.voice_name({"storyteller_name": project.get("storyteller_name"),
                                       "cook_mode": project.get("cook_mode")})
    label = None if project.get("cook_mode") == "self" else (project.get("storyteller_address_as") or voice)
    return voice, label


def _write_pdf(html_content, filename, project=None):
    handle, temp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    try:
        HTML(string=html_content, base_url=config.BASE_DIR).write_pdf(
            temp_path, stylesheets=book_design.stylesheets(project))
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

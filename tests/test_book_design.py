import base64
import io
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfReader
from weasyprint import HTML

import config

from services import book_design, pdf_service, photo_service, project_service, recipe_service, storage_service
from conftest import register
from test_book import _approved_recipes
from test_screens import _onboard


def _photo(size=(3200, 2400), fmt="PNG", color=(200, 120, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    buffer.seek(0)
    return buffer


def _upload(client, url, data=None):
    return client.post(url, data={"photo": (data or _photo(), "IMG_0042.png", "image/png")},
                       content_type="multipart/form-data")


def test_design_screen_saves_style_size_colour_and_words(auth_client):
    pid = _onboard(auth_client)
    page = auth_client.get(f"/p/{pid}/design").data.decode()
    for style in book_design.STYLES.values():
        assert style["name"] in page
    assert "Wide hardcover" in page and "A4 portrait" in page

    auth_client.post(f"/p/{pid}/design", data={
        "theme": "festive", "book_size": "wide", "cover_layout": "title", "book_accent": "#0E5A66",
        "title": "Mummy ki Rasoi", "subtitle": "Forty years of Sunday lunches", "about_author": "Meerut se.",
        "dedication": "For Mummy", "acknowledgement": "With love"})
    project = project_service.get_project(pid)
    assert (project["theme"], project["book_size"], project["cover_layout"], project["book_accent"]) == \
        ("festive", "wide", "title", "#0E5A66")
    assert project["subtitle"] == "Forty years of Sunday lunches" and project["about_author"] == "Meerut se."

    # Unknown values are ignored; a new style drops the old style's colour; an empty title is kept.
    auth_client.post(f"/p/{pid}/design", data={"theme": "modern", "book_size": "a3", "book_accent": "#0E5A66",
                                               "title": " "})
    project = project_service.get_project(pid)
    assert project["theme"] == "modern" and project["book_size"] == "wide" and project["book_accent"] is None
    assert project["title"] == "Mummy ki Rasoi"
    assert book_design.accent(project) == "#D0553A"


def test_old_theme_names_still_get_a_style():
    assert book_design.style_key({"theme": "elegant"}) == "classic"
    assert book_design.style_key({"theme": "fresh"}) == "modern"
    assert book_design.style_key({"theme": "nonsense"}) == "classic"
    assert book_design.size_key({"book_size": "a3"}) == "a4"


def test_cook_photo_is_resized_to_print_size_and_can_be_removed(auth_client):
    pid = _onboard(auth_client)
    assert _upload(auth_client, f"/p/{pid}/photos/cook").status_code == 302
    key = project_service.get_project(pid)["cook_photo_key"]
    assert key.startswith(f"p{pid}-cook-") and key.endswith(".jpg")
    with storage_service.local_copy("photos", key) as path:
        image = Image.open(path)
        assert image.format == "JPEG" and max(image.size) == photo_service.MAX_SIDE
    served = auth_client.get(f"/p/{pid}/photos/cook.jpg")
    assert served.status_code == 200 and served.data[:2] == b"\xff\xd8"

    # A new photo replaces the old file; Remove clears it.
    _upload(auth_client, f"/p/{pid}/photos/cook", _photo((800, 600)))
    new_key = project_service.get_project(pid)["cook_photo_key"]
    assert new_key != key and not storage_service.exists("photos", key)
    auth_client.post(f"/p/{pid}/photos/cook", data={"remove": "1"})
    assert project_service.get_project(pid)["cook_photo_key"] is None
    assert not storage_service.exists("photos", new_key)
    assert auth_client.get(f"/p/{pid}/photos/cook.jpg").status_code == 404


def test_a_file_that_isnt_a_photo_is_refused(auth_client):
    pid = _onboard(auth_client)
    response = auth_client.post(f"/p/{pid}/photos/family", data={
        "photo": (io.BytesIO(b"not an image"), "notes.txt", "text/plain")},
        content_type="multipart/form-data", follow_redirects=True)
    assert b"isn&#39;t a photo we can read" in response.data
    assert project_service.get_project(pid)["family_photo_key"] is None
    assert auth_client.post(f"/p/{pid}/photos/other").status_code == 404


def test_photos_are_only_for_the_owner(app, auth_client):
    pid = _onboard(auth_client)
    _upload(auth_client, f"/p/{pid}/photos/cook")
    stranger = app.test_client()
    assert stranger.get(f"/p/{pid}/photos/cook.jpg").status_code == 302  # to sign in
    register(stranger, email="other@example.com")
    assert stranger.get(f"/p/{pid}/photos/cook.jpg").status_code == 302  # not their book
    assert project_service.get_project(pid)["cook_photo_key"]


def test_dish_photo_goes_on_the_page_and_goes_with_the_recipe(app, auth_client, monkeypatch):
    pid, (rid, other) = _approved_recipes(auth_client, monkeypatch)
    assert "Dish photo" in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    _upload(auth_client, f"/p/{pid}/r/{rid}/photo")
    key = recipe_service.get_recipe(rid)["photo_key"]
    assert key.startswith(f"p{pid}-r{rid}-")
    assert auth_client.get(f"/p/{pid}/photos/r{rid}.jpg").status_code == 200
    assert auth_client.get(f"/p/{pid}/photos/r999999.jpg").status_code == 404

    with app.test_request_context():
        html = pdf_service.render_book_html(project_service.get_project(pid),
                                            [recipe_service.get_recipe(rid), recipe_service.get_recipe(other)])
    assert html.count('class="recipe-photo"') == 1 and "data:image/jpeg;base64," in html

    recipe_service.delete_recipe(rid)
    assert not storage_service.exists("photos", key)


def test_book_follows_the_chosen_style_and_size(app, auth_client, monkeypatch):
    pid, ids = _approved_recipes(auth_client, monkeypatch)
    project_service.update_design(pid, theme="rustic", book_size="wide")
    project = project_service.get_project(pid)
    recipes = [recipe_service.get_recipe(r) for r in ids]
    with app.test_request_context():
        html = pdf_service.render_book_html(project, recipes)
        print_html = pdf_service.render_book_html(project, recipes, print_ready=True)
    assert 'class="style-rustic size-wide"' in html and "size: 297mm 210mm" in html
    assert "bleed" not in html and "bleed: 3mm; marks: crop;" in print_html
    assert book_design.stylesheets(project)[-1].endswith("rustic.css")


def test_chapters_appear_once_there_are_enough_recipes_of_different_kinds():
    def page(category):
        return {"recipe": {"category": category}}
    sections = pdf_service._sections([page("Sweets"), page("dal"), page(""), page("Breakfast"), page("Dal")])
    assert [s["title"] for s in sections] == ["Breakfast", "Dal", "Sweets", "More recipes"]
    assert len(sections[1]["pages"]) == 2


def test_long_recipes_put_their_photo_on_its_own_page(monkeypatch):
    frames = []
    monkeypatch.setattr(photo_service, "data_uri",
                        lambda key, frame, crop: frames.append(frame) or ("data:image/jpeg;base64,xx" if key else None))
    short = {"photo_key": "k", "ingredients": [{}] * 4, "method_steps": [{"instruction": "Mix."}] * 3}
    long = dict(short, ingredients=[{}] * 14, moms_tips=["a", "b"], family_note="Story")
    a4, wide = {"theme": "classic"}, {"theme": "classic", "book_size": "wide"}
    assert pdf_service._page(short, a4)["photo_page"] is False
    assert pdf_service._page(long, a4)["photo_page"] is True
    assert pdf_service._page(short, wide)["photo_page"] is True
    assert pdf_service._page(dict(long, photo_key=None), a4)["photo_page"] is False
    # Each photo is cut to the spot it lands in.
    assert [f["place"] for f in frames] == ["dish", "dish_page", "dish_page", "dish_page"]
    assert (frames[0]["width"], frames[0]["height"]) == (170, 60)


def test_print_shop_pdf_has_bleed(auth_client, monkeypatch):
    pid, ids = _approved_recipes(auth_client, monkeypatch, n=1)
    response = auth_client.get(f"/p/{pid}/book/print.pdf")
    assert response.status_code == 200 and response.data[:4] == b"%PDF"
    page = PdfReader(io.BytesIO(response.data)).pages[0]
    a4_width_pt = 210 / 25.4 * 72
    assert float(page.mediabox.width) > a4_width_pt + 10  # 3 mm bleed each side, plus crop marks


def test_recipe_pdf_uses_the_book_style(app, auth_client, monkeypatch):
    pid, (rid, _) = _approved_recipes(auth_client, monkeypatch)
    project_service.update_design(pid, theme="modern")
    captured = {}
    real = pdf_service.render_template

    def spy(name, **context):
        captured.update(context, name=name)
        return real(name, **context)

    monkeypatch.setattr(pdf_service, "render_template", spy)
    with app.test_request_context():
        pdf_service.generate_recipe_pdf(recipe_service.get_recipe(rid))
    assert captured["name"] == "pdf/recipe.html" and "style-modern" in captured["body_classes"]


def _photo_boxes(html, project):
    """{place: (width, height)} in mm of each photo as WeasyPrint lays the book out."""
    places = {"cover-photo": "cover", "about-photo": "about", "family-photo": "family", "recipe-photo": "dish"}
    found = {}

    def walk(box, figure=None, photo_page=False):
        element = getattr(box, "element", None)
        classes = (element.get("class") or "") if element is not None else ""
        photo_page = photo_page or "photo-page" in classes.split()
        if getattr(box, "element_tag", None) == "figure":
            figure = classes
        if getattr(box, "element_tag", None) == "img" and figure in places:
            place = "dish_page" if figure == "recipe-photo" and photo_page else places[figure]
            found.setdefault(place, (round(box.width * 25.4 / 96), round(box.height * 25.4 / 96)))
        for child in getattr(box, "children", None) or []:
            walk(child, figure, photo_page)

    for page in HTML(string=html, base_url=config.BASE_DIR).render(
            stylesheets=book_design.stylesheets(project)).pages:
        walk(page._page_box)
    return found


@pytest.mark.parametrize("style", sorted(book_design.STYLES))
def test_photo_frames_match_the_book_layout(app, style):
    from scripts import book_samples
    for size in book_design.SIZES:
        project = book_samples.sample_project(style, size)
        with app.test_request_context(), patch.object(photo_service, "data_uri", book_samples.sample_photo):
            html = pdf_service.render_book_html(project, book_samples.RECIPES)
        assert _photo_boxes(html, project) == book_design.PHOTO_FRAMES[style][size], (style, size)


def test_crop_box_fills_the_spot_and_stays_inside_the_photo():
    # A 4:3 photo in a square spot: the full height, centred.
    assert photo_service.crop_box(400, 300, 1.0) == (50, 0, 350, 300)
    # Zoomed in twice on the top left corner: as far left and up as the photo goes.
    assert photo_service.crop_box(400, 300, 1.0, {"x": 0, "y": 0, "zoom": 2}) == (0, 0, 150, 150)
    # A wide band from a tall photo takes the full width.
    assert photo_service.crop_box(300, 400, 3.0, {"x": 0.5, "y": 0.9}) == (0, 300, 300, 400)
    assert photo_service.clean_crop({"x": "nan", "y": 7, "zoom": "a"}) == {"x": 0.5, "y": 1.0, "zoom": 1.0}
    assert photo_service.clean_crop(None) == photo_service.DEFAULT_CROP


def test_a_new_photo_goes_to_fit_and_the_fit_is_used_in_the_book(app, auth_client):
    pid = _onboard(auth_client)
    response = _upload(auth_client, f"/p/{pid}/photos/cook", _photo((1600, 800)))
    assert f"/p/{pid}/photos/cook/fit" in response.headers["Location"]
    page = auth_client.get(response.headers["Location"]).data.decode()
    assert "Fit the photo" in page and "Cover" in page and "About the cook page" in page
    assert 'aspect-ratio: 92 / 118' in page and "shape-oval" in page  # Heirloom's oval cover photo

    fit = {"x": "0.1", "y": "0.5", "zoom": "1.5", "next": f"/p/{pid}/design#photos"}
    saved = auth_client.post(f"/p/{pid}/photos/cook/fit", data=fit)
    assert saved.headers["Location"].endswith(f"/p/{pid}/design#photos")
    project = project_service.get_project(pid)
    assert project["photo_crops"] == {"cook": {"x": 0.1, "y": 0.5, "zoom": 1.5}}

    with app.test_request_context():
        html = pdf_service.render_book_html(project, [])
    cover = html.split('class="cover-photo"><img src="data:image/jpeg;base64,')[1].split('"')[0]
    image = Image.open(io.BytesIO(base64.b64decode(cover)))
    assert abs(image.width / image.height - 92 / 118) < 0.01  # cut to the cover's oval

    # A new photo starts centred again.
    _upload(auth_client, f"/p/{pid}/photos/cook")
    assert project_service.get_project(pid)["photo_crops"] == {}


def test_dish_photo_fit_is_saved_on_the_recipe(auth_client, monkeypatch):
    pid, (rid, _) = _approved_recipes(auth_client, monkeypatch)
    _upload(auth_client, f"/p/{pid}/r/{rid}/photo")
    page = auth_client.get(f"/p/{pid}/photos/r{rid}/fit").data.decode()
    assert "Top of the recipe page" in page or "A full page beside the recipe" in page
    auth_client.post(f"/p/{pid}/photos/r{rid}/fit", data={"x": "0.3", "y": "0.7", "zoom": "9"})
    assert recipe_service.get_recipe(rid)["photo_crop"] == {"x": 0.3, "y": 0.7, "zoom": photo_service.MAX_ZOOM}
    assert auth_client.get(f"/p/{pid}/photos/r999999/fit").status_code == 404
    assert auth_client.get(f"/p/{pid}/photos/family/fit").status_code == 302  # no photo yet: back

import io
from datetime import date, timedelta

from pypdf import PdfReader
from sqlalchemy import select

from models.database import get_engine
from models.schema import events
from services import project_service, recipe_service, storage_service
from test_screens import _onboard, _stub_ai


def _approved_recipes(client, monkeypatch, n=2):
    _stub_ai(monkeypatch)
    pid = _onboard(client)
    ids = []
    for i in range(n):
        response = client.post(f"/p/{pid}/import", data={"new_dish": f"Dish {i}", "audio_files": [
            (io.BytesIO(b"x"), "n.m4a", "audio/mp4")]}, content_type="multipart/form-data")
        rid = int(response.headers["Location"].split("/")[-1])
        recipe_service.approve_recipe(rid)
        ids.append(rid)
    return pid, ids


def _names():
    with get_engine().connect() as conn:
        return conn.execute(select(events.c.name)).scalars().all()


def test_whole_book_pdf_has_cover_contents_and_a_page_per_approved_recipe(auth_client, monkeypatch, tmp_path):
    pid, ids = _approved_recipes(auth_client, monkeypatch)
    assert auth_client.get(f"/p/{pid}/book.pdf").status_code == 404
    auth_client.post(f"/p/{pid}/book/compile")
    latest = project_service.latest_book_pdf(pid)
    assert latest is not None
    with storage_service.local_copy("pdfs", latest["storage_key"]) as path:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() for page in reader.pages)
    assert "The Sharma Kitchen" in text and "Contents" in text and "Sunita ji" in text
    assert text.count("Listen to Sunita ji") == 2 and "Mummy's tips" in text
    assert len(reader.pages) >= 5  # cover, contents, 2 recipes, closing
    response = auth_client.get(f"/p/{pid}/book.pdf")
    assert response.status_code == 200 and response.data[:4] == b"%PDF"
    assert "book_compiled" in _names()


def test_compile_needs_an_approved_page(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    response = auth_client.post(f"/p/{pid}/book/compile", follow_redirects=True)
    assert b"Approve at least one page first" in response.data
    assert auth_client.post(f"/p/{pid}/reveal", follow_redirects=True).status_code == 200
    assert project_service.get_project(pid)["revealed_at"] is None


def test_surprise_until_reveal_with_owner_preview(app, auth_client, monkeypatch):
    pid, ids = _approved_recipes(auth_client, monkeypatch, n=1)
    project_service.update_setup(pid, share_pages_as_ready=False,
                                 reveal_date=date.today() + timedelta(days=10))
    auth_client.post(f"/p/{pid}/book/compile")
    token = project_service.get_project(pid)["book_token"]
    family = app.test_client()

    page = family.get(f"/b/{token}").data.decode()
    assert "a surprise" in page and "Rajma" not in page and "Download the book" not in page
    assert family.get(f"/b/{token}/book.pdf").status_code == 404
    owner = auth_client.get(f"/b/{token}").data.decode()
    assert "Preview: only you" in owner and "Rajma" in owner

    assert "Reveal now" in auth_client.get(f"/p/{pid}/reveal").data.decode()
    auth_client.post(f"/p/{pid}/reveal")
    assert project_service.get_project(pid)["revealed_at"] is not None
    page = family.get(f"/b/{token}").data.decode()
    assert "Rajma" in page and "Download the book" in page
    assert family.get(f"/b/{token}/book.pdf").data[:4] == b"%PDF"
    assert {"book_revealed", "book_page_viewed", "book_pdf_downloaded"} <= set(_names())


def test_reveal_date_opens_the_book_by_itself(app, auth_client, monkeypatch):
    pid, ids = _approved_recipes(auth_client, monkeypatch, n=1)
    project_service.update_setup(pid, share_pages_as_ready=False, reveal_date=date.today())
    token = project_service.get_project(pid)["book_token"]
    assert "Rajma" in app.test_client().get(f"/b/{token}").data.decode()


def test_reveal_screen_offers_the_family_message(auth_client, monkeypatch):
    pid, ids = _approved_recipes(auth_client, monkeypatch, n=1)
    page = auth_client.get(f"/p/{pid}/reveal").data.decode()
    assert "wa.me/?text=" in page and "Make the book PDF" in page

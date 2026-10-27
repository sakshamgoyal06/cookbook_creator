import io
import os
import re

from conftest import SAMPLE_RECIPE, create_project, register
from PIL import Image

import config
from models.database import get_engine
from models.schema import events, listen_events, projects
from services import listen_service, project_service, qr_service, recipe_service
from sqlalchemy import select
from test_storage_service import s3  # noqa: F401  (pytest fixture)


def _recipe_with_audio(client, audio=b"mom's voice"):
    project_id = create_project(client)
    with open(os.path.join(config.UPLOAD_FOLDER, "abc.m4a"), "wb") as f:
        f.write(audio)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    return project_id, row_id, recipe_service.get_recipe(row_id)["listen_token"]


def test_tokens_are_long_random_and_unique(auth_client):
    project_id = create_project(auth_client)
    tokens = {recipe_service.get_recipe(
        recipe_service.save_uploaded_recipe(project_id, f"{i}.m4a", "t", SAMPLE_RECIPE))["listen_token"]
        for i in range(20)}
    assert len(tokens) == 20
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{22}", t) for t in tokens)  # 128 bits, URL-safe


def test_listen_page_works_logged_out_and_has_no_db_ids(auth_client, client):
    project_id, row_id, token = _recipe_with_audio(auth_client)
    auth_client.get("/logout")

    page = client.get(f"/l/{token}")
    assert page.status_code == 200
    assert b"Rajma" in page.data
    assert f"/l/{token}/audio/1".encode() in page.data
    assert f"/projects/{project_id}".encode() not in page.data
    assert b"abc.m4a" not in page.data  # never by filename (QR-5)

    audio = client.get(f"/l/{token}/audio/1")
    assert audio.status_code == 200
    assert audio.get_data() == b"mom's voice"
    assert audio.headers["Cache-Control"] == "private, no-store"
    assert client.get(f"/l/{token}/audio/2").status_code == 404


def test_unknown_token_shows_private_page(client):
    response = client.get("/l/not-a-real-token")
    assert response.status_code == 404
    assert b"This recording is private" in response.data
    assert client.get("/l/not-a-real-token/audio/1").status_code == 404


def test_revoke_makes_old_qr_private_and_regenerate_issues_new_link(auth_client):
    project_id, row_id, token = _recipe_with_audio(auth_client)

    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/listen-link/revoke")
    revoked = auth_client.get(f"/l/{token}")
    assert revoked.status_code == 404 and b"This recording is private" in revoked.data
    assert auth_client.get(f"/l/{token}/audio/1").status_code == 404
    assert b"listen link is off" in auth_client.get(f"/projects/{project_id}/recipes/{row_id}").data

    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/listen-link/regenerate")
    new_token = recipe_service.get_recipe(row_id)["listen_token"]
    assert new_token != token
    assert auth_client.get(f"/l/{new_token}").status_code == 200
    assert auth_client.get(f"/l/{token}").status_code == 404


def test_other_user_cannot_manage_listen_link(client):
    register(client, email="owner@example.com")
    project_id, row_id, token = _recipe_with_audio(client)
    client.get("/logout")
    register(client, email="intruder@example.com")

    client.post(f"/projects/{project_id}/recipes/{row_id}/listen-link/revoke")
    assert client.get(f"/projects/{project_id}/recipes/{row_id}/qr.png").status_code == 302
    assert recipe_service.get_recipe(row_id)["listen_revoked_at"] is None


def test_plays_are_counted_without_owner_or_bots(app, auth_client):
    project_id, row_id, token = _recipe_with_audio(auth_client)
    assert auth_client.post(f"/l/{token}/played").status_code == 204  # owner: stored, not counted
    family = app.test_client()
    assert family.post(f"/l/{token}/played?s=qr").status_code == 204
    assert family.post(f"/l/{token}/played").status_code == 204
    assert family.post(f"/l/{token}/played", headers={"User-Agent": "WhatsApp/2.23"}).status_code == 204
    assert family.post("/l/nope/played").status_code == 404
    assert listen_service.play_count(row_id) == 2
    assert listen_service.play_count(row_id, days=7) == 2
    assert listen_service.project_play_count(project_id) == 2
    with get_engine().connect() as conn:
        rows = conn.execute(select(listen_events.c.source, listen_events.c.is_owner)
                            .order_by(listen_events.c.id)).all()
        plays = conn.execute(select(events.c.props).where(events.c.name == "qr_play")).scalars().all()
    assert [tuple(r) for r in rows] == [("link", True), ("qr", False), ("link", False)]
    assert [p["source"] for p in plays] == ["link", "qr", "link"]
    assert b"played 2 times" in auth_client.get(f"/projects/{project_id}/recipes/{row_id}").data


def test_listen_page_view_is_tracked_but_not_for_link_previews(app, auth_client):
    project_id, row_id, token = _recipe_with_audio(auth_client)
    family = app.test_client()
    family.get(f"/l/{token}?s=qr")
    family.get(f"/l/{token}", headers={"User-Agent": "facebookexternalhit/1.1"})
    with get_engine().connect() as conn:
        views = conn.execute(select(events.c.props).where(events.c.name == "listen_page_viewed")).scalars().all()
    assert views == [{"source": "qr"}]
    assert b"/played?s=qr" in family.get(f"/l/{token}?s=qr").data


def test_listen_audio_redirects_to_short_lived_signed_url_on_s3(auth_client, client, s3, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "S3_SIGNED_URL_SECONDS", 300)
    project_id = create_project(auth_client)
    s3.put_object(Bucket="cookbook-test", Key="prod/audio/abc.m4a", Body=b"voice")
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    token = recipe_service.get_recipe(row_id)["listen_token"]

    response = client.get(f"/l/{token}/audio/1")
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "X-Amz-Signature=" in location  # SigV4, which Railway buckets and R2 require
    assert int(re.search(r"X-Amz-Expires=(\d+)", location).group(1)) == 300


def test_qr_codes_encode_the_public_listen_url(auth_client, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://cookbook.example.com")
    project_id, row_id, token = _recipe_with_audio(auth_client)

    png = auth_client.get(f"/projects/{project_id}/recipes/{row_id}/qr.png?download=1")
    assert png.mimetype == "image/png"
    assert "attachment" in png.headers["Content-Disposition"]
    Image.open(io.BytesIO(png.data)).verify()
    svg = auth_client.get(f"/projects/{project_id}/recipes/{row_id}/qr.svg")
    assert svg.mimetype == "image/svg+xml" and b"<svg" in svg.data
    assert auth_client.get(f"/projects/{project_id}/recipes/{row_id}/qr.gif").status_code == 404

    page = auth_client.get(f"/projects/{project_id}/recipes/{row_id}").data
    assert f"https://cookbook.example.com/l/{token}".encode() in page

    qr = qr_service._qr(f"https://cookbook.example.com/l/{token}")
    assert qr.error in ("M", "Q", "H")


def test_pdf_includes_qr_and_listen_link(auth_client, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://cookbook.example.com")
    project_id, row_id, token = _recipe_with_audio(auth_client)
    captured = {}
    from services import pdf_service

    real_render = pdf_service.render_template

    def spy(name, **context):
        captured.update(context)
        return real_render(name, **context)

    monkeypatch.setattr(pdf_service, "render_template", spy)
    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/generate-pdf")
    assert captured["page"]["listen_url"] == f"https://cookbook.example.com/l/{token}"
    assert captured["page"]["qr"].startswith("data:image/svg+xml")


def test_book_page_lists_recipes_with_players(auth_client, client):
    project_id, row_id, token = _recipe_with_audio(auth_client)
    with get_engine().connect() as conn:
        book_token = conn.execute(select(projects.c.book_token).where(projects.c.id == project_id)).scalar_one()

    assert b"Rajma" not in client.get(f"/b/{book_token}").data  # not approved yet
    recipe_service.approve_recipe(row_id)
    page = client.get(f"/b/{book_token}")
    assert page.status_code == 200
    assert b"Rajma" in page.data and f"/l/{token}".encode() in page.data

    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/listen-link/revoke")
    assert f"/l/{token}".encode() not in client.get(f"/b/{book_token}").data
    assert client.get("/b/unknown").status_code == 404
    assert auth_client.get(f"/projects/{project_id}/qr.svg").status_code == 200


def test_listen_page_names_the_voice_and_links_the_written_page_once_approved(auth_client, client):
    project_id, row_id, token = _recipe_with_audio(auth_client)
    project_service.update_setup(project_id, storyteller_name="Sunita Sharma", cook_mode="whatsapp")
    recipe_service.add_clip(row_id, "story.m4a", kind="story")
    page = client.get(f"/l/{token}").data.decode()
    assert "In Sunita ji&#39;s voice" in page or "In Sunita ji's voice" in page
    assert "The story behind it" in page and "<noscript>" in page
    assert len(page.encode()) < 30_000  # F1 page budget before audio (PRD §13)
    assert "fonts.googleapis" not in page
    assert client.get(f"/l/{token}/recipe").status_code == 404 and "Read the recipe" not in page

    recipe_service.approve_recipe(row_id)
    assert "Read the recipe" in client.get(f"/l/{token}").data.decode()
    written = client.get(f"/l/{token}/recipe").data.decode()
    assert "Pressure cook" in written and "Add ghee at the end" in written
    listen_service.revoke(row_id)
    assert client.get(f"/l/{token}/recipe").status_code == 404


def test_private_page_is_bilingual(client):
    assert "यह रिकॉर्डिंग निजी है" in client.get("/l/nope").data.decode()


def test_surprise_mode_hides_the_book_until_the_reveal(app, auth_client):
    client = app.test_client()  # the family, not the logged-in owner (who gets a preview)
    project_id, row_id, token = _recipe_with_audio(auth_client)
    recipe_service.approve_recipe(row_id)
    project_service.update_setup(project_id, share_pages_as_ready=False)
    book_token = project_service.get_project(project_id)["book_token"]
    page = client.get(f"/b/{book_token}").data
    assert b"a surprise" in page and b"Rajma" not in page
    assert client.get(f"/l/{token}").status_code == 200  # printed QR codes keep working

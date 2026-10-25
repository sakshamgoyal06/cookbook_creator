import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import update
from test_screens import _onboard, _open_upload, _stub_ai

import config
from models.database import get_engine
from models.schema import upload_sessions
from services import project_service, recipe_service, upload_service


def _age_upload(cid, hours):
    old = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_engine().begin() as conn:
        conn.execute(update(upload_sessions).where(upload_sessions.c.client_upload_id == cid).values(created_at=old))
    folder = os.path.join(config.INSTANCE_FOLDER, "upload_chunks", cid)
    for path in [os.path.join(folder, name) for name in os.listdir(folder)] + [folder]:
        os.utime(path, (old.timestamp(), old.timestamp()))
    return folder


def test_stale_uploads_are_cleaned_up_and_the_phone_can_still_finish_them(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client, mode="assisted")
    _open_upload(auth_client, pid, cid="rec-stale-0001")
    _open_upload(auth_client, pid, cid="rec-fresh-0001")
    auth_client.post(f"/p/{pid}/uploads/rec-stale-0001/chunk/0", data=b"AAA")
    auth_client.post(f"/p/{pid}/uploads/rec-fresh-0001/chunk/0", data=b"ZZZ")
    folder = _age_upload("rec-stale-0001", hours=30)

    assert upload_service.cleanup_stale() == 1
    assert upload_service.get_session("rec-stale-0001")["status"] == "abandoned"
    assert upload_service.get_session("rec-fresh-0001")["status"] == "open"
    assert not os.path.exists(folder)

    # The phone comes back days later with its own copy: the server asks again for every part.
    base = f"/p/{pid}/uploads/rec-stale-0001"
    missing = auth_client.post(f"{base}/complete", json={"chunks": 2, "seconds": 9})
    assert missing.status_code == 409 and missing.json["missing"] == [0, 1]
    auth_client.post(f"{base}/chunk/0", data=b"AAA")
    auth_client.post(f"{base}/chunk/1", data=b"BBB")
    done = auth_client.post(f"{base}/complete", json={"chunks": 2, "seconds": 9})
    assert done.json["status"] == "complete" and done.json["redirect"]

    # A finished upload is never reopened by a late chunk, and is never "cleaned up".
    auth_client.post(f"{base}/chunk/1", data=b"late")
    assert upload_service.get_session("rec-stale-0001")["status"] == "complete"
    assert upload_service.cleanup_stale(max_age_hours=0) == 1  # only the fresh, still-open one
    assert upload_service.get_session("rec-stale-0001")["status"] == "complete"


def _quiet_for(pid, days):
    project_service.update_setup(pid, invite_sent_at=datetime.now(timezone.utc) - timedelta(days=days))


def test_home_offers_a_gentle_nudge_after_eight_quiet_days(auth_client):
    pid = _onboard(auth_client)
    _quiet_for(pid, 3)
    assert b"gentle nudge" not in auth_client.get(f"/p/{pid}").data

    _quiet_for(pid, 9)
    page = auth_client.get(f"/p/{pid}").data.decode()
    assert "Nothing from Mummy for 9 days" in page
    assert all(f'value="{do}"' in page for do in ("whatsapp", "call", "record", "later"))

    assert auth_client.post(f"/p/{pid}/nudge", data={"do": "shout"}).status_code == 400
    sent = auth_client.post(f"/p/{pid}/nudge", data={"do": "whatsapp"})
    link = urlparse(sent.headers["Location"])
    assert link.netloc == "wa.me" and link.path == "/919876543210"
    text = parse_qs(link.query)["text"][0]
    assert text.startswith("Mummy, jab time mile, Rajma banane ka tareeka")
    assert b"gentle nudge" not in auth_client.get(f"/p/{pid}").data  # the clock starts again


def test_not_now_snoozes_the_nudge_and_new_notes_reset_it(auth_client):
    pid = _onboard(auth_client)
    _quiet_for(pid, 12)
    later = auth_client.post(f"/p/{pid}/nudge", data={"do": "later"})
    assert later.headers["Location"].endswith(f"/p/{pid}")
    assert b"gentle nudge" not in auth_client.get(f"/p/{pid}").data
    _quiet_for(pid, 12)
    assert auth_client.post(f"/p/{pid}/nudge", data={"do": "call"}).headers["Location"] == "tel:+919876543210"
    assert auth_client.post(f"/p/{pid}/nudge", data={"do": "record"}).headers["Location"].endswith(f"/p/{pid}/record")

    pid2 = _onboard(auth_client)
    _quiet_for(pid2, 12)
    recipe_service.create_received_recipe(pid2, "note.ogg", source="import")
    assert b"gentle nudge" not in auth_client.get(f"/p/{pid2}").data


def test_home_refreshes_itself_while_a_recipe_is_being_written(auth_client):
    pid = _onboard(auth_client)
    assert b"data-autorefresh" not in auth_client.get(f"/p/{pid}").data
    recipe_service.create_received_recipe(pid, "note.ogg", source="import")
    assert b"data-autorefresh" in auth_client.get(f"/p/{pid}").data

import io
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from conftest import SAMPLE_RECIPE
from sqlalchemy import update
from test_screens import _onboard, _open_upload

import config
from models.database import get_engine
from models.schema import recipes
from services import ai_service, dish_service, recipe_service

VAGUE = dict(SAMPLE_RECIPE, ingredients=[
    {"item": "rajma", "quantity": "1", "unit": "katori", "preparation_note": ""},
    {"item": "namak", "quantity": "", "unit": "", "preparation_note": ""},
    {"item": "garam masala", "quantity": "thoda sa", "unit": "", "preparation_note": ""},
], unclear_items_for_review=["namak kitna", "garam masala ki matra", "kitni der pakana"])


def _import(client, pid, recipe=VAGUE, monkeypatch=None, name="n.opus"):
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma ...")
    monkeypatch.setattr(ai_service, "structure_recipe", lambda t, **kw: dict(recipe))
    dish = dish_service.list_dishes(pid)[0]
    response = client.post(f"/p/{pid}/import", data={"dish_id": str(dish["id"]), "audio_files": [
        (io.BytesIO(b"voice"), name, "audio/ogg")]}, content_type="multipart/form-data")
    return int(response.headers["Location"].split("/")[-1])


def test_vague_amounts_are_one_step_before_approval(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    rid = _import(auth_client, pid, monkeypatch=monkeypatch)
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert "Step 1 of 2" in page and "said “thoda sa”" in page
    assert 'name="qty_1"' in page and 'name="qty_2"' in page and 'name="qty_0"' not in page  # rajma is clear
    ask = urlparse("https://wa.me/" + page.split('href="https://wa.me/')[1].split('"')[0].replace("&amp;", "&"))
    text = parse_qs(ask.query)["text"][0]
    assert text.startswith("Mummy, Rajma ka page poora karne ke liye") and "namak, garam masala" in text

    # Approving straight away isn't possible while the amounts step is open.
    auth_client.post(f"/p/{pid}/r/{rid}", data={"action": "approve", "ing_item": ["rajma"]})
    assert recipe_service.get_recipe(rid)["status"] == "needs_review"

    auth_client.post(f"/p/{pid}/r/{rid}/amounts",
                     data={"qty_1": "1", "unit_1": "chhota chammach", "qty_2": "", "unit_2": ""})
    recipe = recipe_service.get_recipe(rid)
    assert [(i["quantity"], i["unit"]) for i in recipe["ingredients"]] == [
        ("1", "katori"), ("1", "chhota chammach"), ("thoda sa", "")]
    assert recipe["unclear_items_for_review"] == ["kitni der pakana"]  # the amount notes are dealt with
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert "Step 2 of 2" in page and "Looks right, approve" in page

    auth_client.post(f"/p/{pid}/r/{rid}/amounts/edit")
    assert "Step 1 of 2" in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()


def test_clear_amounts_skip_the_step_and_blank_ones_keep_andaaze_se(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    rid = _import(auth_client, pid, recipe=SAMPLE_RECIPE, monkeypatch=monkeypatch)
    assert "Step 1 of 2" not in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    rid2 = _import(auth_client, pid, monkeypatch=monkeypatch)
    auth_client.post(f"/p/{pid}/r/{rid2}/amounts", data={})
    assert recipe_service.get_recipe(rid2)["ingredients"][1]["quantity"] == "andaaze se"


def test_recipe_page_pdf_is_on_the_recipe(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    rid = _import(auth_client, pid, recipe=SAMPLE_RECIPE, monkeypatch=monkeypatch)
    assert f"/p/{pid}/r/{rid}/page.pdf" in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    draft = auth_client.get(f"/p/{pid}/r/{rid}/page.pdf")
    assert draft.status_code == 200 and draft.data.startswith(b"%PDF")


def test_stuck_recipe_can_be_retried_restarted_or_deleted(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    monkeypatch.setattr(config, "REDIS_URL", "")
    rid = recipe_service.create_received_recipe(pid, "lost.ogg", source="import", title="Rajma")
    assert "taking much longer" not in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    with get_engine().begin() as conn:
        conn.execute(update(recipes).where(recipes.c.id == rid)
                     .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=30)))
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert "taking much longer" in page and "Upload a voice note instead" in page and "Delete this recipe" in page

    # Its file is gone (a redeploy), so trying again fails and says so plainly.
    auth_client.post(f"/p/{pid}/r/{rid}/retry")
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert "We lost the voice note" in page and "Try again</button>" not in page

    dish = next(d for d in dish_service.list_dishes(pid) if d["recipe_id"] == rid)
    assert dish["title"] == "Rajma"  # the typed name matched the list: no second "Rajma"
    assert sum(d["title"] == "Rajma" for d in dish_service.list_dishes(pid)) == 1
    auth_client.post(f"/p/{pid}/r/{rid}/delete")
    assert recipe_service.get_recipe(rid) is None
    assert dish_service.get_dish(pid, dish["id"])["status"] == "wishlist"


def test_restart_rewrites_from_the_voice_note(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    rid = _import(auth_client, pid, recipe=SAMPLE_RECIPE, monkeypatch=monkeypatch)
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Second take")
    auth_client.post(f"/p/{pid}/r/{rid}/restart")
    recipe = recipe_service.get_recipe(rid)
    assert recipe["status"] == "needs_review" and recipe["raw_transcript"] == "Second take"


def test_a_new_upload_or_recording_replaces_a_failed_recipes_voice_note(auth_client, monkeypatch):
    pid = _onboard(auth_client)
    rid = _import(auth_client, pid, recipe=SAMPLE_RECIPE, monkeypatch=monkeypatch)
    old_key = recipe_service.get_recipe(rid)["audio_clips"][0]["storage_key"]
    recipe_service.set_status(rid, "failed")
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert f"/p/{pid}/import?replace={rid}" in page and f"kind=replace&amp;recipe={rid}" in page
    assert "A new voice note for" in auth_client.get(f"/p/{pid}/import?replace={rid}").data.decode()

    seen = []
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: seen.append(path) or "New take")
    auth_client.post(f"/p/{pid}/import", data={"replace": str(rid), "audio_files": [
        (io.BytesIO(b"again"), "again.m4a", "audio/mp4")]}, content_type="multipart/form-data")
    recipe = recipe_service.get_recipe(rid)
    assert recipe["status"] == "needs_review" and recipe["raw_transcript"] == "New take"
    assert [c["storage_key"] for c in recipe["audio_clips"]] != [old_key] and len(recipe["audio_clips"]) == 1
    assert not os.path.exists(os.path.join(config.UPLOAD_FOLDER, old_key))
    assert len(recipe_service.get_project_recipes(pid)) == 1  # replaced, not a second recipe

    # Recording again in the app does the same.
    assert "Recording again" in auth_client.get(f"/p/{pid}/record?kind=replace&recipe={rid}").data.decode()
    _open_upload(auth_client, pid, cid="rec-redo-0001", kind="replace", recipe_id=rid)
    auth_client.post(f"/p/{pid}/uploads/rec-redo-0001/chunk/0", data=b"redo")
    done = auth_client.post(f"/p/{pid}/uploads/rec-redo-0001/complete", json={"chunks": 1, "seconds": 5})
    assert done.json["redirect"].endswith(f"/r/{rid}")
    recipe = recipe_service.get_recipe(rid)
    assert len(recipe["audio_clips"]) == 1 and recipe["audio_clips"][0]["source"] == "app"
    assert len(recipe_service.get_project_recipes(pid)) == 1

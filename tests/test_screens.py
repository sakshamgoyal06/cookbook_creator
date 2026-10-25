import io
import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from conftest import SAMPLE_RECIPE, register
from sqlalchemy import select

from models.database import get_engine
from models.schema import dishes, events
from services import ai_service, copy, dish_service, listen_service, project_service, recipe_service
from services.ui import normalize_phone


def _event_names():
    with get_engine().connect() as conn:
        return conn.execute(select(events.c.name).order_by(events.c.id)).scalars().all()


def _start(client, mode):
    response = client.post("/start", data={"cook_mode": mode})
    assert response.status_code == 302
    return int(response.headers["Location"].split("/")[2])


def _onboard(client, mode="whatsapp", dishes_text="Rajma\nAloo paratha\nrajma\n", finish=True):
    pid = _start(client, mode)
    steps = [
        ("tier", {"tier": "top10"}),
        ("cook", {"storyteller_address_as": "Mummy", "storyteller_name": "Sunita Sharma",
                  "storyteller_phone": "098765 43210", "storyteller_language": "hinglish"}),
        ("occasion", {"title": "The Sharma Kitchen", "occasion": "Diwali",
                      "reveal_date": (date.today() + timedelta(days=40)).isoformat()}),
        ("dishes", {"dishes": dishes_text}),
        ("pay", {}),
    ]
    for step, data in steps:
        response = client.post(f"/p/{pid}/setup/{step}", data=data)
        assert response.status_code == 302, step
    if finish:
        client.post(f"/p/{pid}/setup/invite")  # "I'll send it later"
    return pid


def _stub_ai(monkeypatch, transcripts=None):
    seen = []

    def transcribe(path):
        seen.append(path)
        return (transcripts or {}).get(len(seen), f"part {len(seen)}")

    monkeypatch.setattr(ai_service, "transcribe_audio", transcribe)
    monkeypatch.setattr(ai_service, "structure_recipe", lambda transcript, **kw: dict(SAMPLE_RECIPE, raw=transcript))
    return seen


def test_whatsapp_onboarding_saves_answers_and_opens_whatsapp_invite(auth_client):
    assert auth_client.get("/start").status_code == 200
    pid = _onboard(auth_client, finish=False)
    project = project_service.get_project(pid)
    assert project["max_recipes"] == 10 and project["tier"] == "top10"
    assert project["storyteller_phone"] == "+919876543210"
    assert project["title"] == "The Sharma Kitchen"
    assert [d["title"] for d in dish_service.list_dishes(pid)] == ["Rajma", "Aloo paratha"]  # deduped, in order
    assert project["setup_step"] == "pay"

    # Home resumes at the step after the last finished one.
    assert auth_client.get(f"/p/{pid}").headers["Location"].endswith(f"/p/{pid}/setup/invite")
    page = auth_client.get(f"/p/{pid}/setup/invite").data.decode()
    assert "Pehli recipe: Rajma" in page and "Mummy," in page

    response = auth_client.post(f"/p/{pid}/invite")
    link = urlparse(response.headers["Location"])
    assert link.netloc == "wa.me" and link.path == "/919876543210"
    assert "Pehli recipe: Rajma" in parse_qs(link.query)["text"][0]
    project = project_service.get_project(pid)
    assert project["setup_step"] == "done" and project["invite_sent_at"] is not None

    home = auth_client.get(f"/p/{pid}")
    assert home.status_code == 200
    assert b"0/10" in home.data and b"Add voice notes" in home.data  # needs-you: import her notes
    assert {"onboarding_started", "cook_mode_chosen", "tier_chosen", "cook_details_saved", "reveal_date_set",
            "dish_list_saved", "invite_shared"} <= set(_event_names())


def test_onboarding_rejects_bad_answers(auth_client):
    pid = _start(auth_client, "whatsapp")
    assert auth_client.post(f"/p/{pid}/setup/tier", data={"tier": "family"}).headers["Location"].endswith("/tier")
    auth_client.post(f"/p/{pid}/setup/tier", data={"tier": "top10"})
    bad_phone = auth_client.post(f"/p/{pid}/setup/cook", data={"storyteller_address_as": "Maa",
                                                               "storyteller_phone": "12345"}, follow_redirects=True)
    assert b"phone number doesn" in bad_phone.data
    auth_client.post(f"/p/{pid}/setup/cook", data={"storyteller_address_as": "Maa"})
    past = auth_client.post(f"/p/{pid}/setup/occasion", data={"title": "Book", "reveal_date": "2020-01-01"},
                            follow_redirects=True)
    assert b"needs to be in the future" in past.data
    auth_client.post(f"/p/{pid}/setup/occasion", data={"title": "Book"})
    empty = auth_client.post(f"/p/{pid}/setup/dishes", data={"dishes": "  \n"}, follow_redirects=True)
    assert b"at least one dish" in empty.data
    assert auth_client.get(f"/p/{pid}/setup/nonsense").status_code == 404
    assert auth_client.post("/start", data={"cook_mode": "robot"}).headers["Location"].endswith("/start")


def test_self_mode_skips_invite_and_lands_in_the_kitchen(auth_client):
    pid = _start(auth_client, "self")
    auth_client.post(f"/p/{pid}/setup/tier", data={"tier": "top10"})
    assert b"About you" in auth_client.get(f"/p/{pid}/setup/cook").data
    auth_client.post(f"/p/{pid}/setup/cook", data={"storyteller_name": "Aarav", "storyteller_language": "en"})
    auth_client.post(f"/p/{pid}/setup/occasion", data={"title": "Aarav's Kitchen"})
    auth_client.post(f"/p/{pid}/setup/dishes", data={"dishes": ""})  # optional when you're the cook
    response = auth_client.post(f"/p/{pid}/setup/pay")
    assert response.headers["Location"].endswith(f"/p/{pid}")
    kitchen = auth_client.get(f"/p/{pid}").data
    assert b"What shall we record?" in kitchen and b"Kitchen" in kitchen
    assert auth_client.get(f"/p/{pid}/setup/invite").status_code == 404


def test_other_users_cannot_open_someone_elses_book(client):
    register(client, email="owner@example.com")
    pid = _onboard(client)
    client.get("/logout")
    register(client, email="intruder@example.com")
    for path in (f"/p/{pid}", f"/p/{pid}/setup/cook", f"/p/{pid}/family", f"/p/{pid}/book", f"/p/{pid}/import"):
        response = client.get(path)
        assert response.status_code == 302 and response.headers["Location"].endswith("/home"), path
    client.post(f"/p/{pid}/setup/occasion", data={"title": "Hacked"})
    assert project_service.get_project(pid)["title"] == "The Sharma Kitchen"


def test_import_groups_several_notes_into_one_dish_and_transcribes_them_in_order(auth_client, monkeypatch):
    seen = _stub_ai(monkeypatch, {1: "Rajma bhigo do.", 2: "Phir tadka lagao."})
    pid = _onboard(auth_client)
    rajma = dish_service.list_dishes(pid)[0]
    response = auth_client.post(
        f"/p/{pid}/import",
        data={"dish_id": str(rajma["id"]),
              "audio_files": [(io.BytesIO(b"one"), "PTT-1.opus", "audio/ogg"),
                              (io.BytesIO(b"two"), "PTT-2.opus", "audio/ogg")]},
        content_type="multipart/form-data",
    )
    recipe_id = int(response.headers["Location"].split("/")[-1])
    recipe = recipe_service.get_recipe(recipe_id)
    assert [c["play_order"] for c in recipe["audio_clips"]] == [1, 2]
    assert all(c["source"] == "import" for c in recipe["audio_clips"])
    assert len(seen) == 2 and recipe["raw_transcript"] == "Rajma bhigo do.\n\nPhir tadka lagao."
    assert recipe["status"] == "needs_review" and recipe["cook_name"] == "Sunita Sharma"
    assert dish_service.get_dish(pid, rajma["id"])["recipe_id"] == recipe_id

    # The owner can play every clip, even after the public link is turned off.
    listen_service.revoke(recipe_id)
    assert auth_client.get(f"/p/{pid}/r/{recipe_id}/audio/2").get_data() == b"two"
    assert auth_client.get(f"/p/{pid}/r/{recipe_id}/audio/3").status_code == 404


def test_import_rejects_non_audio_and_names_new_dishes(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    bad = auth_client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "photo.jpg", "image/jpeg")]},
                           content_type="multipart/form-data", follow_redirects=True)
    assert b"isn&#39;t a voice note" in bad.data or b"isn't a voice note" in bad.data
    auth_client.post(f"/p/{pid}/import", data={"dish_id": "", "new_dish": "Kadhi",
                                               "audio_files": [(io.BytesIO(b"x"), "k.m4a", "audio/mp4")]},
                     content_type="multipart/form-data")
    titles = [d["title"] for d in dish_service.list_dishes(pid)]
    assert "Kadhi" in titles and len(titles) == 3


def test_review_edits_rows_keeps_step_details_and_approves(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    rajma = dish_service.list_dishes(pid)[0]
    response = auth_client.post(f"/p/{pid}/import", data={"dish_id": str(rajma["id"]), "audio_files": [
        (io.BytesIO(b"one"), "n.m4a", "audio/mp4")]}, content_type="multipart/form-data")
    rid = int(response.headers["Location"].split("/")[-1])
    page = auth_client.get(f"/p/{pid}/r/{rid}").data
    assert b"thoda sa namak" in page and b"Ready to review" in page

    step_extra = json.dumps({"flame_level": "high", "timing": "5 whistles", "sensory_cue": ""})
    auth_client.post(f"/p/{pid}/r/{rid}", data={
        "recipe_title": "Sunday Rajma", "serves": "4",
        "ing_qty": ["1", "", ""], "ing_unit": ["katori", "", ""], "ing_item": ["rajma", "namak", ""],
        "ing_note": ["", "andaaze se", ""],
        "step_text": ["Pressure cook", ""], "step_extra": [step_extra, ""],
        "tips": "Ghee at the end\n\n", "family_note": "", "clear_flags": "1", "action": "approve",
    })
    recipe = recipe_service.get_recipe(rid)
    assert recipe["status"] == "approved" and recipe["recipe_title"] == "Sunday Rajma"
    assert recipe["ingredients"][0]["unit"] == "katori"
    assert recipe["ingredients"][1] == {"item": "namak", "quantity": "", "unit": "", "preparation_note": "andaaze se"}
    assert recipe["method_steps"] == [{"flame_level": "high", "timing": "5 whistles", "sensory_cue": "",
                                       "step_number": 1, "instruction": "Pressure cook"}]
    assert recipe["moms_tips"] == ["Ghee at the end"] and recipe["unclear_items_for_review"] == []
    assert recipe["pdf_filename"]  # approving makes the printable page
    assert dish_service.get_dish(pid, rajma["id"])["status"] == "done"
    assert {"recipe_edited", "recipe_approved"} <= set(_event_names())
    assert b"1/10" in auth_client.get(f"/p/{pid}").data
    assert b"Sunday Rajma" in auth_client.get(f"/p/{pid}/book").data


def test_failed_recipe_can_be_retried(auth_client, monkeypatch):
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "  ")
    pid = _onboard(auth_client)
    response = auth_client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "n.m4a", "audio/mp4")]},
                                content_type="multipart/form-data")
    rid = int(response.headers["Location"].split("/")[-1])
    assert recipe_service.get_recipe(rid)["status"] == "failed"
    assert b"couldn&#39;t hear" in auth_client.get(f"/p/{pid}").data or b"couldn't hear" in auth_client.get(
        f"/p/{pid}").data

    _stub_ai(monkeypatch)
    auth_client.post(f"/p/{pid}/r/{rid}/retry")
    assert recipe_service.get_recipe(rid)["status"] == "needs_review"
    assert "recipe_retry_requested" in _event_names()


def test_voice_screen_manages_the_listen_link(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    response = auth_client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "n.m4a", "audio/mp4")]},
                                content_type="multipart/form-data")
    rid = int(response.headers["Location"].split("/")[-1])
    token = recipe_service.get_recipe(rid)["listen_token"]
    assert f"/l/{token}".encode() in auth_client.get(f"/p/{pid}/r/{rid}/voice").data
    back = auth_client.post(f"/projects/{pid}/recipes/{rid}/listen-link/revoke",
                            data={"next": f"/p/{pid}/r/{rid}/voice"})
    assert back.headers["Location"].endswith(f"/p/{pid}/r/{rid}/voice")
    assert b"This recording is private" in auth_client.get(f"/p/{pid}/r/{rid}/voice").data
    evil = auth_client.post(f"/projects/{pid}/recipes/{rid}/listen-link/regenerate", data={"next": "//evil.com"})
    assert "evil.com" not in evil.headers["Location"]


def test_family_screen_shares_the_book_and_toggles_surprise_mode(auth_client):
    pid = _onboard(auth_client)
    auth_client.post(f"/p/{pid}/invite")
    assert b"Aarav" in auth_client.get(f"/p/{pid}/family").data
    share = auth_client.post(f"/p/{pid}/family/share")
    assert share.headers["Location"].startswith("https://wa.me/?text=")
    assert "family_link_shared" in _event_names()
    auth_client.post(f"/p/{pid}/family", data={})
    assert project_service.get_project(pid)["share_pages_as_ready"] is False


def test_wishlist_edits_keep_recorded_dishes(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    rajma = dish_service.list_dishes(pid)[0]
    auth_client.post(f"/p/{pid}/import", data={"dish_id": str(rajma["id"]), "audio_files": [
        (io.BytesIO(b"x"), "n.m4a", "audio/mp4")]}, content_type="multipart/form-data")
    auth_client.post(f"/p/{pid}/setup/dishes", data={"dishes": "Chole\nRajma"})
    with get_engine().connect() as conn:
        rows = conn.execute(select(dishes.c.title, dishes.c.status).where(dishes.c.project_id == pid)
                            .order_by(dishes.c.position)).all()
    assert [tuple(r) for r in rows] == [("Rajma", "in_progress"), ("Chole", "wishlist")]


def test_logged_out_home_is_the_welcome_page(client):
    page = client.get("/")
    assert page.status_code == 200 and b"Start a cookbook" in page.data


def test_phone_numbers_and_invite_copy():
    assert normalize_phone("98765 43210") == "+919876543210"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("5876543210") is None and normalize_phone("") is None
    project = {"storyteller_language": "hi", "storyteller_address_as": "Dadi", "title": "T"}
    text = copy.invite_text(project, "Kadhi")
    assert text.startswith("Dadi,") and "Kadhi" in text and "बनाती" not in text  # no gendered verbs
    assert copy.wa_link("a b&c", "+919876543210") == "https://wa.me/919876543210?text=a%20b%26c"


def test_editing_an_approved_page_asks_for_approval_again(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    response = auth_client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "n.m4a", "audio/mp4")]},
                                content_type="multipart/form-data")
    rid = int(response.headers["Location"].split("/")[-1])
    recipe_service.approve_recipe(rid)
    form = {"recipe_title": "Rajma", "serves": "4", "ing_qty": ["1"], "ing_unit": ["cup"], "ing_item": ["rajma"],
            "ing_note": ["soaked overnight"], "step_text": ["Pressure cook"],
            "step_extra": [json.dumps({"flame_level": "high", "timing": "5 whistles", "sensory_cue": ""})],
            "tips": "Add ghee at the end", "family_note": "Sunday lunch", "action": "save"}
    auth_client.post(f"/p/{pid}/r/{rid}", data=form)
    assert recipe_service.get_recipe(rid)["status"] == "approved"  # nothing changed
    auth_client.post(f"/p/{pid}/r/{rid}", data=dict(form, serves="6"))
    assert recipe_service.get_recipe(rid)["status"] == "needs_review"


def test_a_full_book_still_keeps_new_voice_notes(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    pid = _onboard(auth_client)
    project_service.update_setup(pid, max_recipes=1)
    for _ in range(2):
        last = auth_client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "n.m4a", "audio/mp4")]},
                                content_type="multipart/form-data", follow_redirects=True)
    assert b"saved as an extra" in last.data
    assert len(recipe_service.get_project_recipes(pid)) == 2


def test_status_chips_cover_every_status():
    from models.schema import RECIPE_STATUSES
    from services.ui import cook_display_name, cook_label, status_chip
    assert all(status_chip(s)["style"] in ("writing", "waiting", "review", "approved", "failed")
               for s in RECIPE_STATUSES)
    assert status_chip("awaiting_mom", "Dadi")["label"] == "Waiting on Dadi"
    project = {"storyteller_name": "Sunita Sharma", "storyteller_address_as": "Mummy"}
    assert cook_display_name(project) == "Sunita ji" and cook_label(project) == "Mummy"


def _open_upload(client, pid, cid="rec-0001-abcd", **body):
    return client.post(f"/p/{pid}/uploads", json={"client_upload_id": cid, "content_type": "audio/webm;codecs=opus",
                                                  **body})


def test_recording_uploads_in_chunks_out_of_order_and_retries_safely(auth_client, monkeypatch):
    seen = _stub_ai(monkeypatch)
    pid = _onboard(auth_client, mode="assisted")
    page = auth_client.get(f"/p/{pid}/record").data
    assert b"Recording Mummy" in page and b"data-recorder" in page
    rajma = dish_service.list_dishes(pid)[0]

    assert _open_upload(auth_client, pid, dish_id=rajma["id"]).json["status"] == "open"
    assert _open_upload(auth_client, pid, dish_id=rajma["id"]).status_code == 200  # opening again is fine
    base = f"/p/{pid}/uploads/rec-0001-abcd"
    auth_client.post(f"{base}/chunk/1", data=b"BBB")
    auth_client.post(f"{base}/chunk/0", data=b"xx")
    auth_client.post(f"{base}/chunk/0", data=b"AAA")  # a retried chunk replaces the first copy
    early = auth_client.post(f"{base}/complete", json={"chunks": 3, "seconds": 14})
    assert early.status_code == 409 and early.json["missing"] == [2]
    auth_client.post(f"{base}/chunk/2", data=b"CCC")

    done = auth_client.post(f"{base}/complete", json={"chunks": 3, "seconds": 14})
    recipe_id = int(done.json["redirect"].split("/")[-1])
    assert auth_client.post(f"{base}/complete", json={"chunks": 3}).json["redirect"] == done.json["redirect"]
    assert len(recipe_service.get_project_recipes(pid)) == 1  # the repeat didn't make a second recipe
    recipe = recipe_service.get_recipe(recipe_id)
    assert recipe["audio_clips"][0]["storage_key"].endswith(".webm")
    assert recipe["audio_clips"][0]["source"] == "app" and recipe["recipe_title"] == "Rajma"
    assert auth_client.get(f"/p/{pid}/r/{recipe_id}/audio/1").get_data() == b"AAABBBCCC"
    assert len(seen) == 1 and recipe["status"] == "needs_review"
    assert dish_service.get_dish(pid, rajma["id"])["recipe_id"] == recipe_id
    assert {"recording_started", "recording_finished", "recipe_created"} <= set(_event_names())


def test_story_clip_joins_the_recipe_without_reprocessing(auth_client, monkeypatch):
    seen = _stub_ai(monkeypatch)
    pid = _onboard(auth_client, mode="self")
    _open_upload(auth_client, pid, cid="rec-recipe-0001")
    auth_client.post(f"/p/{pid}/uploads/rec-recipe-0001/chunk/0", data=b"recipe")
    rid = int(auth_client.post(f"/p/{pid}/uploads/rec-recipe-0001/complete",
                               json={"chunks": 1}).json["redirect"].split("/")[-1])
    assert b"Add the story behind this dish" in auth_client.get(f"/p/{pid}/r/{rid}").data
    assert b"The story behind" in auth_client.get(f"/p/{pid}/record?kind=story&recipe={rid}").data

    _open_upload(auth_client, pid, cid="rec-story-0001", kind="story", recipe_id=rid)
    auth_client.post(f"/p/{pid}/uploads/rec-story-0001/chunk/0", data=b"story")
    auth_client.post(f"/p/{pid}/uploads/rec-story-0001/complete", json={"chunks": 1})
    clips = recipe_service.get_recipe(rid)["audio_clips"]
    assert [(c["kind"], c["play_order"]) for c in clips] == [("original", 1), ("story", 2)]
    assert len(seen) == 1


def test_uploads_are_validated_and_private(client, monkeypatch):
    _stub_ai(monkeypatch)
    register(client, email="owner@example.com")
    pid = _onboard(client)
    assert _open_upload(client, pid, cid="../../etc").status_code == 400
    assert _open_upload(client, pid, cid="rec-story-9999", kind="story", recipe_id=999).status_code == 404
    _open_upload(client, pid, cid="rec-mine-0001")
    assert client.post(f"/p/{pid}/uploads/rec-mine-0001/chunk/0", data=b"").status_code == 400
    assert client.post(f"/p/{pid}/uploads/nope-nope-nope/chunk/0", data=b"x").status_code == 404
    client.get("/logout")
    register(client, email="intruder@example.com")
    other = _onboard(client)
    assert client.post(f"/p/{pid}/uploads/rec-mine-0001/chunk/0", data=b"x").status_code == 302
    # Someone else's upload id can't be reused in your own book either.
    assert _open_upload(client, other, cid="rec-mine-0001").status_code == 400
    assert client.post(f"/p/{other}/uploads/rec-mine-0001/chunk/0", data=b"x").status_code == 404


def test_sharing_voice_notes_from_whatsapp_adds_them_to_the_latest_book(auth_client, monkeypatch):
    _stub_ai(monkeypatch)
    assert auth_client.post("/share", data={}).headers["Location"].endswith("/start")
    pid = _onboard(auth_client)
    response = auth_client.post("/share", data={"text": "", "audio_files": [
        (io.BytesIO(b"a"), "PTT-20261025-WA0001.opus", "audio/ogg"), (io.BytesIO(b"b"), "x.jpg", "image/jpeg")]},
        content_type="multipart/form-data")
    rid = int(response.headers["Location"].split("/")[-1])
    assert len(recipe_service.get_recipe(rid)["audio_clips"]) == 1
    assert recipe_service.get_recipe(rid)["project_id"] == pid

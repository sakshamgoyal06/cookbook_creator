import io

from conftest import SAMPLE_RECIPE
from sqlalchemy import select

from models.database import get_engine
from models.schema import events
from services import ai_service, question_service, recipe_service
from test_screens import _onboard

QUESTIONS = [
    {"about": "namak", "question": "Page poora karne ke liye ek baat poochni thi: namak kitna daalti hain?",
     "options": ["1 chammach", "2 chutki", "andaaze se"]},
    {"about": "rajma bhigona", "question": "Rajma kitni der bhigoti hain?", "options": ["Raat bhar", "4 ghante"]},
    {"about": "a", "question": "Teesra?", "options": []},
    {"about": "b", "question": "Chautha sawaal?", "options": []},
    {"about": "c", "question": "   ", "options": []},
]


def _recipe(client, monkeypatch, questions=QUESTIONS):
    seen = []

    def structure(transcript, language="hinglish"):
        seen.append((transcript, language))
        return dict(SAMPLE_RECIPE, follow_up_questions=questions if len(seen) == 1 else [{"question": "New?"}])

    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma bhigo do, namak thoda sa.")
    monkeypatch.setattr(ai_service, "structure_recipe", structure)
    pid = _onboard(client)
    response = client.post(f"/p/{pid}/import", data={"audio_files": [(io.BytesIO(b"x"), "n.m4a", "audio/mp4")]},
                           content_type="multipart/form-data")
    return pid, int(response.headers["Location"].split("/")[-1]), seen


def test_questions_are_stored_once_capped_at_three_and_shown_one_at_a_time(auth_client, monkeypatch):
    pid, rid, seen = _recipe(auth_client, monkeypatch)
    assert seen[0][1] == "hinglish"
    questions = question_service.list_questions(rid)
    assert [q["about"] for q in questions] == ["namak", "rajma bhigona", "a"]
    page = auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert "namak kitna daalti hain?" in page and "2 chutki" in page and "Quick questions (3)" in page
    assert "Rajma kitni der" not in page  # one at a time
    assert "wa.me/919876543210" in page  # whatsapp mode: ask her from your own WhatsApp
    assert "quick questions before" in auth_client.get(f"/p/{pid}").data.decode()


def test_answers_rewrite_the_page_once_every_question_is_resolved(auth_client, monkeypatch):
    pid, rid, seen = _recipe(auth_client, monkeypatch)
    q1, q2, q3 = question_service.list_questions(rid)
    auth_client.post(f"/p/{pid}/r/{rid}/q/{q1['id']}", data={"via": "chip", "answer": "2 chutki"})
    auth_client.post(f"/p/{pid}/r/{rid}/q/{q2['id']}", data={"via": "text", "answer": "  Raat   bhar "})
    assert len(seen) == 1  # not until the last one
    again = auth_client.post(f"/p/{pid}/r/{rid}/q/{q2['id']}", data={"via": "text", "answer": "again"})
    assert again.status_code == 302
    auth_client.post(f"/p/{pid}/r/{rid}/q/{q3['id']}", data={"via": "keep"})

    assert len(seen) == 2
    rewritten = seen[1][0]
    assert rewritten.startswith("Rajma bhigo do") and "- namak: 2 chutki" in rewritten and "Raat bhar" in rewritten
    assert "Teesra" not in rewritten
    assert recipe_service.get_recipe(rid)["status"] == "needs_review"
    assert len(question_service.list_questions(rid)) == 3  # no new questions on the rewrite
    assert [q["status"] for q in question_service.list_questions(rid)] == ["answered", "answered", "kept"]
    with get_engine().connect() as conn:
        names = conn.execute(select(events.c.name)).scalars().all()
    assert names.count("question_sent") == 3 and names.count("question_answered") == 2
    assert "question_skipped" in names


def test_keeping_every_answer_as_said_does_not_rewrite(auth_client, monkeypatch):
    pid, rid, seen = _recipe(auth_client, monkeypatch, questions=QUESTIONS[:1])
    q = question_service.list_questions(rid)[0]
    assert auth_client.post(f"/p/{pid}/r/{rid}/q/{q['id']}", data={"via": "text", "answer": " "},
                            follow_redirects=True).status_code == 200
    assert question_service.list_questions(rid)[0]["status"] == "open"
    auth_client.post(f"/p/{pid}/r/{rid}/q/{q['id']}", data={"via": "keep"})
    assert len(seen) == 1 and "Quick question" not in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()
    assert auth_client.post(f"/p/{pid}/r/{rid}/q/{q['id']}", data={"via": "hack"}).status_code == 400


def test_no_unclear_items_means_no_questions(auth_client, monkeypatch):
    pid, rid, _ = _recipe(auth_client, monkeypatch, questions=[])
    assert question_service.list_questions(rid) == []
    assert "Quick question" not in auth_client.get(f"/p/{pid}/r/{rid}").data.decode()

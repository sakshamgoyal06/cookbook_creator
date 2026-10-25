"""Follow-up questions about a recipe's unclear bits (BUILD_PLAN module 10, AI-5/AI-6).

The structuring call proposes up to 3 questions. They're asked once per recipe; answers
go back into the next structuring run, and the page is rewritten with them.
"""
from sqlalchemy import func, insert, select, update

from models.database import get_engine
from models.schema import recipe_questions

MAX_QUESTIONS = 3
MAX_ANSWER = 300


def list_questions(recipe_id):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(recipe_questions).where(recipe_questions.c.recipe_id == recipe_id)
            .order_by(recipe_questions.c.position, recipe_questions.c.id)
        ).mappings().all()
    return [dict(r) for r in rows]


def open_questions(recipe_id):
    return [q for q in list_questions(recipe_id) if q["status"] == "open"]


def save_questions(recipe_id, proposed):
    """Store the AI's questions the first time a recipe is structured. Returns how many were stored."""
    if list_questions(recipe_id):
        return 0  # asked once per recipe; later runs only use the answers
    clean = []
    for q in proposed or []:
        text = " ".join((q.get("question") or "").split())
        if text:
            options = [" ".join(o.split())[:40] for o in (q.get("options") or []) if o and o.strip()][:4]
            clean.append({"about": (q.get("about") or "").strip()[:80], "question": text[:300], "options": options})
    clean = clean[:MAX_QUESTIONS]
    with get_engine().begin() as conn:
        for position, q in enumerate(clean, start=1):
            conn.execute(insert(recipe_questions).values(recipe_id=recipe_id, position=position, **q))
    return len(clean)


def answer(recipe_id, question_id, text, via):
    """Record an answer (via chip, text or voice), or keep the cook's words as said (via "keep").

    Returns None if the question was already resolved, else whether this resolved the last open one.
    """
    if via == "keep":
        values = {"status": "kept", "answer_text": None}
    elif via == "skip":
        values = {"status": "skipped", "answer_text": None}
    else:
        text = " ".join((text or "").split())[:MAX_ANSWER]
        if not text:
            raise ValueError("Empty answer.")
        values = {"status": "answered", "answer_text": text}
    with get_engine().begin() as conn:
        changed = conn.execute(
            update(recipe_questions)
            .where(recipe_questions.c.id == question_id, recipe_questions.c.recipe_id == recipe_id,
                   recipe_questions.c.status == "open")
            .values(**values, answer_via=via, answered_at=func.now())
        ).rowcount
    if not changed:
        return None
    return not open_questions(recipe_id)


def has_answers(recipe_id):
    return any(q["status"] == "answered" for q in list_questions(recipe_id))


def answers_block(recipe_id):
    """Answers appended to the transcript for the next structuring run."""
    lines = [f"- {q['about'] or q['question']}: {q['answer_text']}"
             for q in list_questions(recipe_id) if q["status"] == "answered"]
    if not lines:
        return ""
    return "\n\nAnswers the cook gave to follow-up questions:\n" + "\n".join(lines)

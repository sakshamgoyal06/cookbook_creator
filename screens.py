"""The mobile app screens (MOBILE_UX_SPEC §2; BUILD_PLAN modules 5, 6 and 7).

R = requester (the buyer), S = same person (the cook records in the app). The older
/projects pages stay for now; these routes are what the PWA opens.
"""
import json
import os
import tempfile
from datetime import date, datetime, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import config
from services import (
    copy,
    dish_service,
    events_service,
    listen_service,
    pdf_service,
    pipeline_service,
    project_service,
    question_service,
    recipe_service,
    storage_service,
    upload_service,
)
from services.audio_utils import SUPPORTED_FORMATS_LABEL, build_storage_filename, is_allowed_audio
from services.ui import cook_label, days_until, normalize_phone

bp = Blueprint("screens", __name__)

SETUP_STEPS = {
    "whatsapp": ("tier", "cook", "occasion", "dishes", "pay", "invite"),
    "assisted": ("tier", "cook", "occasion", "dishes", "pay"),
    "self": ("tier", "cook", "occasion", "dishes", "pay"),
}
ADDRESS_OPTIONS = ("Mummy", "Maa", "Mumma", "Dadi", "Nani", "Papa")
OCCASIONS = ("Diwali", "Birthday", "Mother's Day", "Anniversary", "Wedding", "Just because")
DISH_SUGGESTIONS = ("Rajma", "Dal makhani", "Aloo paratha", "Kadhi pakora", "Chole", "Gajar ka halwa",
                    "Bhindi masala", "Paneer butter masala", "Besan ladoo", "Khichdi")
MAX_IMPORT_FILES = 10


def owned_project(view):
    """Load the project named in the URL for its owner; anyone else is sent home."""
    @wraps(view)
    def wrapper(project_id, *args, **kwargs):
        project = project_service.get_project(project_id)
        if not project or project["user_id"] != current_user.id:
            flash("We couldn't find that book.", "error")
            return redirect(url_for("screens.home_redirect"))
        return view(project, *args, **kwargs)
    return login_required(wrapper)


def _recipe_or_404(project, recipe_id):
    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None or recipe["project_id"] != project["id"]:
        abort(404)
    return recipe


def _tabs(project, current):
    pid = project["id"]
    if project["cook_mode"] == "self":
        items = [("home", "pot", "Kitchen"), ("record", "mic", "Record"), ("family", "users", "Family"),
                 ("book", "book", "Book")]
    else:
        items = [("home", "home", "Home"), ("recipes", "list", "Recipes"), ("record", "mic", "Record"),
                 ("family", "users", "Family"), ("book", "book", "Book")]
    return [{"href": url_for(f"screens.{name}", project_id=pid), "icon": icon, "label": label,
             "on": name == current} for name, icon, label in items]


def _render(template, project=None, tab=None, **context):
    if project is not None:
        context.setdefault("tabs", _tabs(project, tab) if project.get("setup_step") == "done" else None)
        context.setdefault("cook", cook_label(project))
    return render_template(template, project=project, **context)


# ─── Entry ──────────────────────────────────────────────────────

@bp.route("/home")
@login_required
def home_redirect():
    projects = project_service.get_user_projects(current_user.id)
    if not projects:
        return redirect(url_for("screens.start"))
    return redirect(url_for("screens.home", project_id=projects[0]["id"]))


@bp.route("/start", methods=["GET", "POST"])
@login_required
def start():
    """R2: whose recipes? Picking an answer creates the book."""
    if request.method == "GET":
        events_service.track("onboarding_started", actor="buyer")
        return _render("app/start.html", back_url=url_for("screens.home_redirect")
                       if project_service.get_user_projects(current_user.id) else None)

    mode = request.form.get("cook_mode")
    if mode not in SETUP_STEPS:
        flash("Please pick one of the three.", "error")
        return redirect(url_for("screens.start"))
    project_id = project_service.create_project(current_user.id, "Our family cookbook", cook_mode=mode)
    events_service.track("cook_mode_chosen", project_id=project_id, actor="buyer", mode=mode)
    return redirect(url_for("screens.setup", project_id=project_id, step="tier"))


# ─── Onboarding R3–R8 ───────────────────────────────────────────

def _next_step(project, step):
    steps = SETUP_STEPS[project["cook_mode"]]
    i = steps.index(step)
    return steps[i + 1] if i + 1 < len(steps) else None


def resume_step(project):
    """The first onboarding step the buyer hasn't finished, or None when setup is done."""
    if project.get("setup_step") == "done":
        return None
    steps = SETUP_STEPS[project["cook_mode"]]
    if project.get("setup_step") in steps:
        return _next_step(project, project["setup_step"]) or steps[-1]
    return steps[0]


@bp.route("/p/<int:project_id>/setup/<step>", methods=["GET", "POST"])
@owned_project
def setup(project, step):
    steps = SETUP_STEPS[project["cook_mode"]]
    if step not in steps:
        abort(404)
    editing = project.get("setup_step") == "done"
    number = steps.index(step) + 1
    back = (url_for("screens.home", project_id=project["id"]) if editing
            else url_for("screens.setup", project_id=project["id"], step=steps[number - 2]) if number > 1
            else url_for("screens.start"))

    if request.method == "POST":
        error = SAVE_STEP[step](project)
        if error:
            flash(error, "error")
            return redirect(url_for("screens.setup", project_id=project["id"], step=step))
        nxt = _next_step(project, step)
        if editing:
            flash("Saved.", "success")
            return redirect(url_for("screens.home", project_id=project["id"]))
        if nxt is None:
            project_service.update_setup(project["id"], setup_step="done")
            return redirect(url_for("screens.home", project_id=project["id"]))
        project_service.update_setup(project["id"], setup_step=step)
        return redirect(url_for("screens.setup", project_id=project["id"], step=nxt))

    dishes = dish_service.list_dishes(project["id"])
    context = {
        "step": step, "number": number, "total": len(steps), "editing": editing, "back_url": back,
        "tiers": config.TIERS, "address_options": ADDRESS_OPTIONS, "occasions": OCCASIONS,
        "dish_suggestions": DISH_SUGGESTIONS, "dishes": dishes, "today": date.today().isoformat(),
    }
    if step == "invite":
        first = next((d["title"] for d in dishes if d["status"] == "wishlist"), None)
        context["invite_text"] = copy.invite_text(project, first)
    return _render(f"app/setup_{step}.html", project, **context)


def _save_tier(project):
    tier = request.form.get("tier")
    if tier not in config.TIERS or not config.TIERS[tier]["available"]:
        return "Please pick a book."
    project_service.update_setup(project["id"], tier=tier, max_recipes=config.TIERS[tier]["recipes"])
    events_service.track("tier_chosen", project_id=project["id"], actor="buyer", tier=tier)


def _save_cook(project):
    form = request.form
    language = form.get("storyteller_language", "hinglish")
    if language not in ("hi", "hinglish", "en"):
        language = "hinglish"
    name = " ".join(form.get("storyteller_name", "").split())[:60]
    values = {"storyteller_language": language, "storyteller_name": name or None}
    if project["cook_mode"] == "self":
        if not name:
            return "Please add the name you'd like on the book."
    else:
        address = form.get("address_as_other", "").strip() or form.get("storyteller_address_as", "").strip()
        if not address:
            return "Please tell us what you call them."
        values["storyteller_address_as"] = address[:30]
        raw_phone = form.get("storyteller_phone", "").strip()
        phone = normalize_phone(raw_phone)
        if raw_phone and not phone:
            return ("That phone number doesn't look right. Use a 10-digit Indian number, "
                    "or start with + and the country code.")
        values["storyteller_phone"] = phone
    project_service.update_setup(project["id"], **values)
    events_service.track("cook_details_saved", project_id=project["id"], actor="buyer", language=language)


def _save_occasion(project):
    form = request.form
    title = " ".join(form.get("title", "").split())[:80]
    if not title:
        return "Please give the book a title."
    reveal = None
    if form.get("reveal_date"):
        try:
            reveal = date.fromisoformat(form["reveal_date"])
        except ValueError:
            return "Please pick a real date."
        if reveal <= date.today():
            return "The reveal date needs to be in the future."
    occasion = form.get("occasion_other", "").strip() or form.get("occasion", "").strip()
    project_service.update_setup(project["id"], title=title, occasion=occasion[:40] or None, reveal_date=reveal,
                                 dedication=form.get("dedication", "").strip()[:500])
    if reveal:
        events_service.track("reveal_date_set", project_id=project["id"], actor="buyer",
                             days_away=days_until(reveal))
        if days_until(reveal) < 21:
            flash("That's soon. Ten recipes usually take three to four weeks, "
                  "so start with the dishes that matter most.", "info")


def _save_dishes(project):
    titles = dish_service.clean_titles(request.form.get("dishes", "").splitlines())
    if not titles and project["cook_mode"] != "self" and not dish_service.list_dishes(project["id"]):
        return "Add at least one dish, so the invite can name it."
    dish_service.save_wishlist(project["id"], titles)
    events_service.track("dish_list_saved", project_id=project["id"], actor="buyer", count=len(titles))
    quota = project.get("max_recipes") or 10
    if len(titles) > quota:
        flash(f"Your book holds {quota} recipes. The rest stay on the wishlist for a second volume.", "info")


def _save_pay(project):
    if not config.PILOT_FREE:
        return "Payments open soon. You're on the pilot list, and we'll message you."


def _save_invite(project):
    return None


SAVE_STEP = {"tier": _save_tier, "cook": _save_cook, "occasion": _save_occasion, "dishes": _save_dishes,
             "pay": _save_pay, "invite": _save_invite}


@bp.route("/p/<int:project_id>/invite", methods=["POST"])
@owned_project
def send_invite(project):
    """R8: open the buyer's own WhatsApp with the invite ready, and remember that they sent it."""
    first = dish_service.next_dish(project["id"])
    text = copy.invite_text(project, first["title"] if first else None)
    project_service.update_setup(project["id"], invite_sent_at=datetime.now(timezone.utc), setup_step="done")
    events_service.track("invite_shared", project_id=project["id"], actor="buyer",
                         language=project["storyteller_language"])
    return redirect(copy.wa_link(text, project.get("storyteller_phone")))


# ─── Home R9 / Kitchen S1 ───────────────────────────────────────

@bp.route("/p/<int:project_id>")
@owned_project
def home(project):
    step = resume_step(project)
    if step:
        return redirect(url_for("screens.setup", project_id=project["id"], step=step))

    recipes = recipe_service.get_project_recipes(project["id"])
    dishes = dish_service.list_dishes(project["id"])
    quota = project.get("max_recipes") or 10
    approved = sum(r["status"] == "approved" for r in recipes)
    context = {
        "recipes": recipes,
        "approved": approved,
        "quota": quota,
        "up_next": [d for d in dishes if d["status"] == "wishlist"][:3],
        "next_dish": next((d for d in dishes if d["status"] == "wishlist"), None),
        "days_left": days_until(project.get("reveal_date")),
        "needs_you": _needs_you(project, recipes),
        "plays_week": listen_service.project_play_count(project["id"], days=7),
    }
    template = "app/kitchen.html" if project["cook_mode"] == "self" else "app/home.html"
    return _render(template, project, tab="home", **context)


def _needs_you(project, recipes):
    """The one card that needs the buyer now (UX R9), most urgent first."""
    pid = project["id"]
    failed = next((r for r in recipes if r["status"] == "failed"), None)
    if failed:
        return {"text": f"We couldn't hear “{failed['recipe_title']}” clearly. Try once more, or record it again.",
                "action": url_for("screens.review", project_id=pid, recipe_id=failed["id"]),
                "label": "See what happened"}
    ready = next((r for r in recipes if r["status"] == "needs_review"), None)
    if ready and question_service.open_questions(ready["id"]):
        n = len(question_service.open_questions(ready["id"]))
        return {"text": f"“{ready['recipe_title']}” has {n} quick question{'s' if n != 1 else ''} before it's done.",
                "action": url_for("screens.review", project_id=pid, recipe_id=ready["id"]), "label": "Answer them"}
    if ready:
        return {"text": f"“{ready['recipe_title']}” is written up and ready for you to check.",
                "action": url_for("screens.review", project_id=pid, recipe_id=ready["id"]), "label": "Review the page"}
    if project["cook_mode"] == "whatsapp" and not project.get("invite_sent_at"):
        return {"text": f"Send {cook_label(project)} the invite from your WhatsApp.",
                "action": url_for("screens.setup", project_id=pid, step="invite"), "label": "Send the invite"}
    if project["cook_mode"] == "whatsapp" and not recipes:
        return {"text": f"When {cook_label(project)} sends you voice notes, forward or save them and add them here.",
                "action": url_for("screens.import_notes", project_id=pid), "label": "Add voice notes"}
    return None


@bp.route("/p/<int:project_id>/recipes")
@owned_project
def recipes(project):
    return _render("app/recipes.html", project, tab="recipes" if project["cook_mode"] != "self" else "home",
                   recipes=recipe_service.get_project_recipes(project["id"]),
                   dishes=[d for d in dish_service.list_dishes(project["id"]) if d["status"] == "wishlist"],
                   back_url=url_for("screens.home", project_id=project["id"]))


@bp.route("/p/<int:project_id>/dishes", methods=["POST"])
@owned_project
def add_dish(project):
    if dish_service.add_dish(project["id"], request.form.get("title", "")) is None:
        flash("Please type a dish name.", "error")
    return redirect(request.form.get("next") if _safe_next(request.form.get("next"))
                    else url_for("screens.recipes", project_id=project["id"]))


def _safe_next(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


# ─── Review R10 / S5 ────────────────────────────────────────────

@bp.route("/p/<int:project_id>/r/<int:recipe_id>", methods=["GET", "POST"])
@owned_project
def review(project, recipe_id):
    recipe = _recipe_or_404(project, recipe_id)
    if request.method == "POST":
        if recipe["status"] not in ("needs_review", "approved"):
            flash("This page is still being written.", "error")
            return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
        data = _review_form_data(recipe)
        changed = _count_changes(recipe, data)
        recipe_service.update_recipe(recipe_id, data)
        if changed:
            events_service.track("recipe_edited", project_id=project["id"], recipe_id=recipe_id, actor="buyer",
                                 fields_changed=changed)
        if recipe["status"] == "approved" and changed and request.form.get("action") != "approve":
            recipe_service.set_status(recipe_id, "needs_review")
            flash("Saved. Approve it again to update the printed page.", "success")
            return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
        if request.form.get("action") == "approve":
            recipe_service.approve_recipe(recipe_id)
            events_service.track("recipe_approved", project_id=project["id"], recipe_id=recipe_id, actor="buyer",
                                 edits=changed)
            _make_pdf(recipe_id)
            flash("Approved. This page is in the book.", "success")
        else:
            flash("Saved.", "success")
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))

    clips = [url_for("screens.clip", project_id=project["id"], recipe_id=recipe_id, clip_number=n)
             for n in range(1, len(recipe["audio_clips"]) + 1)]
    return _render("app/review.html", project, tab="recipes" if project["cook_mode"] != "self" else "home",
                   recipe=recipe, clip_urls=clips,
                   back_url=url_for("screens.recipes" if project["cook_mode"] != "self" else "screens.home",
                                    project_id=project["id"]),
                   blank_rows=3, questions=_questions_for(project, recipe))


def _questions_for(project, recipe):
    """S4: open follow-up questions, each with a WhatsApp link to ask the cook when she isn't in the app."""
    if recipe["status"] != "needs_review":
        return []
    questions = question_service.open_questions(recipe["id"])
    if project["cook_mode"] == "whatsapp":
        for q in questions:
            q["ask_link"] = copy.wa_link(copy.question_text(project, recipe["recipe_title"], q["question"]),
                                         project.get("storyteller_phone"))
    return questions


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/q/<int:question_id>", methods=["POST"])
@owned_project
def answer_question(project, recipe_id, question_id):
    recipe = _recipe_or_404(project, recipe_id)
    via = request.form.get("via", "text")
    if via not in ("chip", "text", "keep"):
        abort(400)
    try:
        last = question_service.answer(recipe_id, question_id, request.form.get("answer"), via)
    except ValueError:
        flash("Please type an answer, or tap “Leave it as said”.", "error")
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
    if last is None:  # already answered (a double tap, or another tab)
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
    actor = _actor(project)
    if via == "keep":
        events_service.track("question_skipped", project_id=project["id"], recipe_id=recipe_id, actor=actor)
    else:
        events_service.track("question_answered", project_id=project["id"], recipe_id=recipe_id, actor=actor,
                             via=via)
    if last and question_service.has_answers(recipe_id) and recipe["status"] == "needs_review":
        # Rewrite the page with the answers; the transcript is kept, so only structuring runs again.
        recipe_service.set_status(recipe_id, "transcribed")
        pipeline_service.enqueue_processing(recipe_id)
        flash("Thank you. We're updating the page with the answers.", "success")
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/audio/<int:clip_number>")
@owned_project
def clip(project, recipe_id, clip_number):
    """The owner's own copy of a clip; works even when the public listen link is off."""
    recipe = _recipe_or_404(project, recipe_id)
    if not 1 <= clip_number <= len(recipe["audio_clips"]):
        abort(404)
    response = storage_service.send("audio", recipe["audio_clips"][clip_number - 1]["storage_key"])
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _review_form_data(recipe):
    form = request.form
    ingredients = []
    for item, qty, unit, note in zip(form.getlist("ing_item"), form.getlist("ing_qty"), form.getlist("ing_unit"),
                                     form.getlist("ing_note")):
        if item.strip():
            ingredients.append({"item": item.strip(), "quantity": qty.strip(), "unit": unit.strip(),
                                "preparation_note": note.strip()})
    steps = []
    for text, extra in zip(form.getlist("step_text"), form.getlist("step_extra")):
        if text.strip():
            try:
                kept = json.loads(extra) if extra else {}
            except json.JSONDecodeError:
                kept = {}
            steps.append({**{k: v for k, v in kept.items() if k in ("flame_level", "timing", "sensory_cue")},
                          "step_number": len(steps) + 1, "instruction": text.strip()})
    tips = [t.strip() for t in form.get("tips", "").splitlines() if t.strip()]
    kept = ("category", "difficulty", "serving_suggestion", "storage_notes")
    data = {field: recipe.get(field) or "" for field in kept}
    data.update({
        "recipe_title": form.get("recipe_title", "").strip() or recipe["recipe_title"],
        "serves": form.get("serves", "").strip(),
        "family_note": form.get("family_note", "").strip(),
        "prep_time_minutes": recipe.get("prep_time_minutes"),
        "cook_time_minutes": recipe.get("cook_time_minutes"),
        "ingredients_json": json.dumps(ingredients, ensure_ascii=False),
        "method_steps_json": json.dumps(steps, ensure_ascii=False),
        "moms_tips_json": json.dumps(tips, ensure_ascii=False),
    })
    if form.get("clear_flags"):
        data["unclear_items_for_review_json"] = "[]"
    return data


def _count_changes(recipe, data):
    changed = 0
    for field, value in data.items():
        if field.endswith("_json"):
            changed += json.loads(recipe.get(field) or "[]") != json.loads(value)
        else:
            changed += (recipe.get(field) or "") != (value or "")
    return changed


def _make_pdf(recipe_id):
    try:
        pdf_filename = pdf_service.generate_recipe_pdf(recipe_service.get_recipe(recipe_id))
        recipe_service.mark_pdf_generated(recipe_id, pdf_filename)
    except Exception:  # the page is approved either way; the PDF can be made again from the Book tab
        current_app.logger.exception("PDF generation failed for recipe %s", recipe_id)


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/retry", methods=["POST"])
@owned_project
def retry(project, recipe_id):
    recipe = _recipe_or_404(project, recipe_id)
    if recipe["status"] == "failed":
        recipe_service.set_status(recipe_id, "transcribed" if recipe.get("raw_transcript") else "received")
        events_service.track("recipe_retry_requested", project_id=project["id"], recipe_id=recipe_id, actor="buyer",
                             stage="structure" if recipe.get("raw_transcript") else "transcribe")
        pipeline_service.enqueue_processing(recipe_id)
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/pdf", methods=["POST"])
@owned_project
def make_pdf(project, recipe_id):
    _recipe_or_404(project, recipe_id)
    _make_pdf(recipe_id)
    return redirect(url_for("screens.book", project_id=project["id"]))


# ─── Voice link and QR R13 ──────────────────────────────────────

@bp.route("/p/<int:project_id>/r/<int:recipe_id>/voice")
@owned_project
def voice(project, recipe_id):
    recipe = _recipe_or_404(project, recipe_id)
    live = recipe["listen_revoked_at"] is None
    return _render("app/voice.html", project, tab="recipes" if project["cook_mode"] != "self" else "home",
                   recipe=recipe, live=live,
                   listen_url=listen_service.listen_url(recipe["listen_token"]) if live else None,
                   plays_week=listen_service.play_count(recipe_id, days=7),
                   plays_total=listen_service.play_count(recipe_id),
                   back_url=url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


# ─── Import voice notes S3 ──────────────────────────────────────

@bp.route("/p/<int:project_id>/import", methods=["GET", "POST"])
@owned_project
def import_notes(project):
    """S3: add voice notes that already exist (forwarded from WhatsApp, or files). One upload = one dish."""
    pid = project["id"]
    wishlist = [d for d in dish_service.list_dishes(pid) if d["status"] == "wishlist"]
    if request.method == "GET":
        return _render("app/import.html", project, tab="record", dishes=wishlist,
                       selected=request.args.get("dish", type=int), formats=SUPPORTED_FORMATS_LABEL,
                       max_files=MAX_IMPORT_FILES, back_url=url_for("screens.home", project_id=pid))

    files = [f for f in request.files.getlist("audio_files") if f and f.filename]
    if not files:
        flash("Please choose at least one voice note.", "error")
        return redirect(url_for("screens.import_notes", project_id=pid))
    if len(files) > MAX_IMPORT_FILES:
        flash(f"Up to {MAX_IMPORT_FILES} voice notes for one dish, please.", "error")
        return redirect(url_for("screens.import_notes", project_id=pid))
    bad = [f.filename for f in files if not is_allowed_audio(f.filename, f.mimetype)]
    if bad:
        flash(f"“{bad[0]}” isn't a voice note we can read. Please use {SUPPORTED_FORMATS_LABEL}.", "error")
        return redirect(url_for("screens.import_notes", project_id=pid))
    over_quota = project_service.get_project_recipe_count(pid) >= (project.get("max_recipes") or 10)

    dish_id, title = _dish_choice(pid, wishlist)
    keys = [_store_upload(f) for f in files]
    recipe_id = recipe_service.create_received_recipe(pid, keys[0], source="import", audio_keys=keys, title=title,
                                                      dish_id=dish_id, cook_name=project.get("storyteller_name"))
    events_service.track("recipe_created", project_id=pid, recipe_id=recipe_id, actor="buyer", source="import")
    pipeline_service.enqueue_processing(recipe_id)
    flash("Got it. We're writing the recipe down; it takes about a minute.", "success")
    if over_quota:  # never turn a voice note away; extra pages wait for Volume 2
        flash("Your book is already full, so this one is saved as an extra for a second volume.", "info")
    return redirect(url_for("screens.review", project_id=pid, recipe_id=recipe_id))


@bp.route("/share", methods=["POST"])
@login_required
def share_target():
    """Android "Share" from WhatsApp into the installed app (manifest share_target): goes to the latest book."""
    projects = project_service.get_user_projects(current_user.id)
    files = [f for f in request.files.getlist("audio_files") if f and f.filename]
    if not projects:
        flash("Set up your book first, then share the voice notes again.", "error")
        return redirect(url_for("screens.start"))
    project = projects[0]
    files = [f for f in files if is_allowed_audio(f.filename, f.mimetype)][:MAX_IMPORT_FILES]
    if not files:
        flash("That share didn't include a voice note. Choose the files here instead.", "error")
        return redirect(url_for("screens.import_notes", project_id=project["id"]))
    keys = [_store_upload(f) for f in files]
    recipe_id = recipe_service.create_received_recipe(project["id"], keys[0], source="import", audio_keys=keys,
                                                      cook_name=project.get("storyteller_name"))
    events_service.track("recipe_created", project_id=project["id"], recipe_id=recipe_id, actor="buyer",
                         source="share")
    pipeline_service.enqueue_processing(recipe_id)
    flash("Got the voice notes. We're writing the recipe down.", "success")
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


def _dish_choice(project_id, wishlist):
    """The wishlist dish picked on the form, or a new dish typed in (None title lets the AI name it)."""
    choice = request.form.get("dish_id", type=int)
    dish = next((d for d in wishlist if d["id"] == choice), None)
    if dish:
        return dish["id"], dish["title"]
    typed = dish_service.clean_titles([request.form.get("new_dish", "")])
    return None, (typed[0] if typed else None)


def _store_upload(file):
    filename = build_storage_filename(file.filename, file.mimetype)
    handle, temp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
    os.close(handle)
    try:
        file.save(temp_path)
        storage_service.save_file("audio", filename, temp_path, content_type=file.mimetype)
    finally:
        os.remove(temp_path)
    return filename


PROMPTS = {
    "original": ["Start with the dish's name, and who you make it for.",
                 "What goes in? Say the amounts the way you'd show them: a katori, a mutthi, andaaze se.",
                 "Now the steps, one by one. What do you look, smell or listen for?",
                 "How do you know it's done?", "Any tip you'd tell only family?"],
    "story": ["When did you first make this?", "Who taught it to you?", "Which day or festival is it for?"],
}


@bp.route("/p/<int:project_id>/record")
@owned_project
def record(project):
    """S2: record a recipe (or the story behind one) in the app."""
    pid = project["id"]
    kind = "story" if request.args.get("kind") == "story" else "original"
    recipe = None
    if kind == "story":
        recipe = _recipe_or_404(project, request.args.get("recipe", type=int))
    wishlist = [d for d in dish_service.list_dishes(pid) if d["status"] == "wishlist"]
    dish = next((d for d in wishlist if d["id"] == request.args.get("dish", type=int)), None)
    if kind == "original" and dish is None and wishlist and "dish" not in request.args:
        dish = wishlist[0]
    return _render("app/record.html", project, tab="record", kind=kind, recipe=recipe, dish=dish, dishes=wishlist,
                   prompts=PROMPTS[kind], back_url=url_for("screens.home", project_id=pid))


@bp.route("/p/<int:project_id>/uploads", methods=["POST"])
@owned_project
def upload_open(project):
    body = request.get_json(silent=True) or {}
    kind = body.get("kind", "original")
    recipe_id = dish_id = None
    if kind == "story":
        recipe_id = _recipe_or_404(project, _int(body.get("recipe_id")))["id"]
    elif body.get("dish_id"):
        dish = dish_service.get_dish(project["id"], _int(body.get("dish_id")))
        dish_id = dish["id"] if dish and dish["recipe_id"] is None else None
    try:
        session = upload_service.open_session(project["id"], body.get("client_upload_id"), kind=kind,
                                              content_type=body.get("content_type"), dish_id=dish_id,
                                              recipe_id=recipe_id)
    except upload_service.UploadError as e:
        return jsonify(error=str(e)), 400
    if session["chunks_received"] == 0 and session["status"] == "open":
        events_service.track("recording_started", project_id=project["id"], actor=_actor(project), kind=kind)
    return jsonify(_session_json(project, session))


@bp.route("/p/<int:project_id>/uploads/<client_id>/chunk/<int:number>", methods=["PUT", "POST"])
@owned_project
def upload_chunk(project, client_id, number):
    session = _own_session(project, client_id)
    try:
        session = upload_service.save_chunk(session, number, request.get_data(cache=False))
    except upload_service.UploadError as e:
        events_service.track("upload_failed", project_id=project["id"], actor=_actor(project), stage="chunk")
        return jsonify(error=str(e)), 400
    return jsonify(_session_json(project, session))


@bp.route("/p/<int:project_id>/uploads/<client_id>/complete", methods=["POST"])
@owned_project
def upload_complete(project, client_id):
    pid = project["id"]
    session = _own_session(project, client_id)
    body = request.get_json(silent=True) or {}
    if session["status"] == "complete":
        return jsonify(_session_json(project, session))
    expected, seconds = _int(body.get("chunks")) or 0, max(0, _int(body.get("seconds")) or 0)
    missing = upload_service.missing_chunks(session, expected) if expected else []
    if not expected or missing:
        return jsonify(error="Some parts haven't arrived yet.", missing=missing[:50]), 409
    if not upload_service.claim(session):
        return jsonify(_session_json(project, upload_service.get_session(client_id)))
    try:
        key = upload_service.assemble(session, expected)
        if session["kind"] == "story":
            recipe_service.add_clip(session["recipe_id"], key, kind="story", source="app",
                                    content_type=session["content_type"])
            recipe_id = session["recipe_id"]
        else:
            dish = dish_service.get_dish(pid, session["dish_id"]) if session["dish_id"] else None
            recipe_id = recipe_service.create_received_recipe(
                pid, key, source="app", title=(dish or {}).get("title"),
                dish_id=dish["id"] if dish and dish["recipe_id"] is None else None,
                cook_name=project.get("storyteller_name"), content_type=session["content_type"])
            events_service.track("recipe_created", project_id=pid, recipe_id=recipe_id, actor=_actor(project),
                                 source="app")
    except Exception:
        upload_service.release(session)
        events_service.track("upload_failed", project_id=pid, actor=_actor(project), stage="complete")
        raise
    upload_service.mark_complete(session, recipe_id)
    events_service.track("recording_finished", project_id=pid, recipe_id=recipe_id, actor=_actor(project),
                         seconds=seconds, kind=session["kind"])
    if session["kind"] == "original":
        pipeline_service.enqueue_processing(recipe_id)
    return jsonify(_session_json(project, upload_service.get_session(client_id)))


def _own_session(project, client_id):
    session = upload_service.get_session(client_id)
    if session is None or session["project_id"] != project["id"]:
        abort(404)
    return session


def _session_json(project, session):
    done = session["status"] == "complete" and session["recipe_id"]
    return {"status": session["status"], "chunks_received": session["chunks_received"],
            "redirect": url_for("screens.review", project_id=project["id"], recipe_id=session["recipe_id"])
            if done else None}


def _actor(project):
    return "cook" if project["cook_mode"] == "self" else "buyer"


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ─── Family R11 and Book ────────────────────────────────────────

@bp.route("/p/<int:project_id>/family", methods=["GET", "POST"])
@owned_project
def family(project):
    pid = project["id"]
    if request.method == "POST":
        project_service.update_setup(pid, share_pages_as_ready=bool(request.form.get("share_pages_as_ready")))
        flash("Saved.", "success")
        return redirect(url_for("screens.family", project_id=pid))
    book_url = listen_service.book_url(project["book_token"])
    requested = [d for d in dish_service.list_dishes(pid) if d["source"] == "family"]
    return _render("app/family.html", project, tab="family", book_url=book_url,
                   share_link=copy.wa_link(copy.family_share_text(project, book_url)),
                   members=project_service.get_members(pid), requested=requested)


@bp.route("/p/<int:project_id>/family/share", methods=["POST"])
@owned_project
def share_family(project):
    events_service.track("family_link_shared", project_id=project["id"], actor="buyer")
    book_url = listen_service.book_url(project["book_token"])
    return redirect(copy.wa_link(copy.family_share_text(project, book_url)))


@bp.route("/p/<int:project_id>/book")
@owned_project
def book(project):
    recipes = recipe_service.get_project_recipes(project["id"])
    return _render("app/book.html", project, tab="book", recipes=recipes,
                   approved=[r for r in recipes if r["status"] == "approved"],
                   book_url=listen_service.book_url(project["book_token"]),
                   days_left=days_until(project.get("reveal_date")),
                   steps=SETUP_STEPS[project["cook_mode"]])

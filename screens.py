"""The mobile app screens (MOBILE_UX_SPEC §2; BUILD_PLAN modules 5, 6 and 7).

R = requester (the buyer), S = same person (the cook records in the app). The older
/projects pages stay for now; these routes are what the PWA opens.
"""
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask import session as flask_session
from flask_login import current_user, login_required

import config
from services import (
    amounts_service,
    book_design,
    copy,
    dish_photo_service,
    dish_service,
    events_service,
    family_service,
    listen_service,
    payment_service,
    pdf_service,
    photo_service,
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
# What the buyer calls the cook. Any family cook, not only Mummy; "Something else" takes the rest.
ADDRESS_OPTIONS = ("Mummy", "Maa", "Papa", "Dadi", "Nani", "Dada", "Nana", "Bua", "Mausi", "Chachi")
OCCASIONS = ("Diwali", "Birthday", "Mother's Day", "Father's Day", "Anniversary", "Wedding", "Just because")
DISH_SUGGESTIONS = ("Rajma", "Dal makhani", "Aloo paratha", "Kadhi pakora", "Chole", "Gajar ka halwa",
                    "Bhindi masala", "Paneer butter masala", "Besan ladoo", "Khichdi")
MAX_IMPORT_FILES = 10
QUIET_DAYS = 8  # UX R9: after this long with nothing from the cook, Home offers a gentle nudge
WRITING_STATUSES = ("received", "transcribed", "structured")
NUDGE_CHOICES = ("whatsapp", "call", "record", "later")


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
    if step == "pay":
        context["order"] = payment_service.latest_order(project["id"])
        context["paid"] = payment_service.is_unlocked(project)
        context["payments_on"] = payment_service.enabled()
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
    if config.PILOT_FREE:
        payment_service.mark_pilot(project["id"])
        return None
    if payment_service.is_unlocked(project):
        return None
    if not payment_service.enabled():
        return "Payments open soon. You're on the pilot list, and we'll message you."
    return "Please finish the payment first. If you've just paid, it can take a moment to confirm."


def _save_invite(project):
    return None


SAVE_STEP = {"tier": _save_tier, "cook": _save_cook, "occasion": _save_occasion, "dishes": _save_dishes,
             "pay": _save_pay, "invite": _save_invite}


# ─── Payments R7 (module 13) ─────────────────────────────────────

@bp.route("/p/<int:project_id>/pay/order", methods=["POST"])
@owned_project
def pay_order(project):
    """Start (or resume) Razorpay Checkout for this book; the page opens Checkout with what we return."""
    if not payment_service.enabled() or payment_service.is_unlocked(project):
        return jsonify(error="Nothing to pay.", redirect=_after_pay(project)), 409
    try:
        order = payment_service.create_order(project, current_user.id)
    except payment_service.PaymentError as e:
        return jsonify(error=str(e)), 502
    return jsonify(key=config.RAZORPAY_KEY_ID, order_id=order["provider_ref"], amount=order["amount_paise"],
                   currency=order["currency"], name=config.APP_NAME, description=project["title"],
                   prefill={"name": current_user.name, "email": current_user.email})


@bp.route("/p/<int:project_id>/pay/verify", methods=["POST"])
@owned_project
def pay_verify(project):
    body = request.get_json(silent=True) or {}
    order_ref, payment_id = body.get("razorpay_order_id"), body.get("razorpay_payment_id")
    order = payment_service.get_order_by_ref(order_ref or "")
    if (order is None or order["project_id"] != project["id"]
            or not payment_service.checkout_signature_ok(order_ref, payment_id, body.get("razorpay_signature"))):
        return jsonify(error="We couldn't confirm that payment. If money left your account, "
                             "it will show here within a few minutes."), 400
    payment_service.mark_paid(order_ref, payment_id)
    return jsonify(redirect=_after_pay(project_service.get_project(project["id"])))


def _after_pay(project):
    """Paying completes the pay step, so the buyer carries on with setup."""
    if project.get("setup_step") == "done":
        return url_for("screens.home", project_id=project["id"])
    nxt = _next_step(project, "pay")
    if nxt is None:
        project_service.update_setup(project["id"], setup_step="done")
        return url_for("screens.home", project_id=project["id"])
    project_service.update_setup(project["id"], setup_step="pay")
    return url_for("screens.setup", project_id=project["id"], step=nxt)


@bp.route("/payments/razorpay/webhook", methods=["POST"])
def razorpay_webhook():
    """Signed by Razorpay; unlocks the book even if the buyer's browser closed after paying."""
    body = request.get_data(cache=False)
    if not payment_service.webhook_signature_ok(body, request.headers.get("X-Razorpay-Signature")):
        abort(400)
    try:
        payload = json.loads(body)
    except ValueError:
        abort(400)
    if not payment_service.handle_webhook(payload):
        return "", 503  # order not saved yet: Razorpay retries
    return "", 200


@bp.route("/p/<int:project_id>/orders/<int:order_id>/invoice")
@owned_project
def invoice(project, order_id):
    order = payment_service.get_order(project["id"], order_id)
    if order is None or order["status"] not in ("paid", "refunded"):
        abort(404)
    buyer = {"name": current_user.name, "email": current_user.email}
    return render_template("app/invoice.html", project=project, invoice=payment_service.invoice(order, project, buyer),
                           back_url=url_for("screens.book", project_id=project["id"]))


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
        "writing": any(r["status"] in WRITING_STATUSES for r in recipes),
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
    pending = family_service.pending_requests(pid)
    if pending:
        return {"text": f"{pending[0]['requested_by_label']} asked for {pending[0]['title']}. Add it to the list?",
                "action": url_for("screens.family", project_id=pid), "label": "See requests"}
    quiet = _days_quiet(project, recipes)
    if quiet is not None:
        nudge = url_for("screens.nudge", project_id=pid)
        choices = [("whatsapp", "Send a gentle nudge")]
        if project.get("storyteller_phone"):
            choices.append(("call", "Call"))
        choices += [("record", "Record together"), ("later", "Not now")]
        return {"text": f"Nothing from {cook_label(project)} for {quiet} days. A gentle nudge or a call often "
                        "helps, or cook together and record it here.",
                "action": nudge, "post": True, "label": choices[0][1],
                "choices": [{"do": do, "label": label} for do, label in choices]}
    if project["cook_mode"] == "whatsapp" and not project.get("invite_sent_at"):
        return {"text": f"Send {cook_label(project)} the invite from your WhatsApp.",
                "action": url_for("screens.setup", project_id=pid, step="invite"), "label": "Send the invite"}
    if project["cook_mode"] == "whatsapp" and not recipes:
        return {"text": f"When {cook_label(project)} sends you voice notes, forward or save them and add them here.",
                "action": url_for("screens.import_notes", project_id=pid), "label": "Add voice notes"}
    return None


def _days_quiet(project, recipes):
    """Days since anything happened with the cook, once that's QUIET_DAYS or more; otherwise None."""
    if project["cook_mode"] != "whatsapp" or not project.get("invite_sent_at"):
        return None
    days_left = days_until(project.get("reveal_date"))
    if days_left is not None and days_left < 0:
        return None
    if sum(r["status"] == "approved" for r in recipes) >= (project.get("max_recipes") or 10):
        return None
    moments = [project["invite_sent_at"], events_service.last_at(project["id"], "escalation_action")]
    moments += [r["created_at"] for r in recipes]
    last = max(_aware(m) for m in moments if m)
    days = (datetime.now(timezone.utc) - last).days
    return days if days >= QUIET_DAYS else None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@bp.route("/p/<int:project_id>/nudge", methods=["POST"])
@owned_project
def nudge(project):
    """The quiet-stretch card. Any choice, "Not now" included, starts the QUIET_DAYS clock again."""
    pid = project["id"]
    do = request.form.get("do")
    if do not in NUDGE_CHOICES or (do == "call" and not project.get("storyteller_phone")):
        abort(400)
    events_service.track("escalation_action", project_id=pid, actor="buyer", action=do)
    if do == "whatsapp":
        dish = dish_service.next_dish(pid)
        return redirect(copy.wa_link(copy.nudge_text(project, dish["title"] if dish else None),
                                     project.get("storyteller_phone")))
    if do == "call":
        return redirect(f"tel:{project['storyteller_phone']}")
    if do == "record":
        return redirect(url_for("screens.record", project_id=pid))
    return redirect(url_for("screens.home", project_id=pid))


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
        if request.form.get("action") == "approve" and amounts_service.needs_step(recipe):
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
    questions = _questions_for(project, recipe)
    amounts = not questions and amounts_service.needs_step(recipe)
    return _render("app/amounts.html" if amounts else "app/review.html", project,
                   tab="recipes" if project["cook_mode"] != "self" else "home",
                   recipe=recipe, clip_urls=clips, questions=questions, blank_rows=1,
                   unclear=amounts_service.unclear_amounts(recipe) if amounts else [],
                   ask_link=_amounts_ask_link(project, recipe) if amounts else None,
                   stuck=_is_stuck(recipe),
                   failure=pipeline_service.failure_reason(recipe_id) if recipe["status"] == "failed" else None,
                   back_url=url_for("screens.recipes" if project["cook_mode"] != "self" else "screens.home",
                                    project_id=project["id"]))


STUCK_AFTER = timedelta(minutes=10)


def _is_stuck(recipe):
    """Still "writing it down" long after it should have finished (a lost job, a redeploy mid-way)."""
    if recipe["status"] not in WRITING_STATUSES or not recipe.get("updated_at"):
        return False
    return datetime.now(timezone.utc) - _aware(recipe["updated_at"]) > STUCK_AFTER


def _amounts_ask_link(project, recipe):
    if project["cook_mode"] != "whatsapp":
        return None
    items = [ing["item"] for _, ing in amounts_service.unclear_amounts(recipe)]
    return copy.wa_link(copy.amounts_text(project, recipe["recipe_title"], items), project.get("storyteller_phone"))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/amounts", methods=["POST"])
@owned_project
def save_amounts(project, recipe_id):
    """The amounts step: one answer per vague ingredient, all at once; blanks keep the cook's words."""
    recipe = _recipe_or_404(project, recipe_id)
    if recipe["status"] != "needs_review":
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
    answers = {}
    for index, _ in amounts_service.unclear_amounts(recipe):
        answers[index] = (request.form.get(f"qty_{index}", ""), request.form.get(f"unit_{index}", ""))
    changed = amounts_service.apply(recipe, answers)
    if changed:
        events_service.track("recipe_edited", project_id=project["id"], recipe_id=recipe_id, actor=_actor(project),
                             fields_changed=changed)
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/amounts/edit", methods=["POST"])
@owned_project
def reopen_amounts(project, recipe_id):
    recipe_service.reopen_amounts(_recipe_or_404(project, recipe_id)["id"])
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/restart", methods=["POST"])
@owned_project
def restart(project, recipe_id):
    """Start a recipe over from its voice notes (stuck, or written up wrong)."""
    recipe = _recipe_or_404(project, recipe_id)
    if not recipe["audio_clips"]:
        flash("This recipe has no voice note left to start from. Record or upload it again.", "error")
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
    recipe_service.restart(recipe_id)
    events_service.track("recipe_retry_requested", project_id=project["id"], recipe_id=recipe_id,
                         actor=_actor(project), stage="transcribe")
    pipeline_service.enqueue_processing(recipe_id)
    flash("Starting over from the voice note.", "success")
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/delete", methods=["POST"])
@owned_project
def delete_recipe(project, recipe_id):
    recipe = _recipe_or_404(project, recipe_id)
    recipe_service.delete_recipe(recipe["id"])
    flash(f"Deleted “{recipe['recipe_title']}”.", "success")
    return redirect(url_for("screens.recipes" if project["cook_mode"] != "self" else "screens.home",
                            project_id=project["id"]))


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/page.pdf")
@owned_project
def recipe_page_pdf(project, recipe_id):
    """The printable page for one recipe: the approved one, or a fresh draft while it's being checked."""
    recipe = _recipe_or_404(project, recipe_id)
    if recipe["status"] not in ("needs_review", "approved"):
        abort(404)
    if recipe["status"] != "approved" or not recipe.get("pdf_filename"):
        _make_pdf(recipe_id)
        recipe = recipe_service.get_recipe(recipe_id)
    if not recipe.get("pdf_filename"):
        flash("We couldn't make the PDF just now. Please try again in a minute.", "error")
        return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe_id))
    return storage_service.send("pdfs", recipe["pdf_filename"])


def _questions_for(project, recipe):
    """S4: open follow-up questions, each with a WhatsApp link to ask the cook when they aren't in the app."""
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
            ingredients.append({"item": _one_line(item), "quantity": _one_line(qty), "unit": _one_line(unit),
                                "preparation_note": _one_line(note)})
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
        "recipe_title": _one_line(form.get("recipe_title", "")) or recipe["recipe_title"],
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


def _one_line(text):
    return " ".join((text or "").split())


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
    if recipe["status"] == "failed" or _is_stuck(recipe):
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
    nxt = request.form.get("next")
    return redirect(nxt if _safe_next(nxt) else url_for("screens.book", project_id=project["id"]))


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
        replacing = _recipe_or_404(project, request.args.get("replace", type=int)) if "replace" in request.args \
            else None
        return _render("app/import.html", project, tab="record", dishes=wishlist, replacing=replacing,
                       selected=request.args.get("dish", type=int), formats=SUPPORTED_FORMATS_LABEL,
                       max_files=MAX_IMPORT_FILES,
                       back_url=url_for("screens.review", project_id=pid, recipe_id=replacing["id"]) if replacing
                       else url_for("screens.home", project_id=pid))

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
    keys = [_store_upload(f) for f in files]
    if request.form.get("replace"):
        return _replace_notes(project, _recipe_or_404(project, request.form.get("replace", type=int)), keys, "import")
    return _add_dish(project, keys, *_dish_choice(pid, wishlist), source="import")


def _add_dish(project, keys, dish_id, title, source):
    """A new recipe from stored voice notes (one dish), written down in the background."""
    pid = project["id"]
    over_quota = project_service.get_project_recipe_count(pid) >= (project.get("max_recipes") or 10)
    recipe_id = recipe_service.create_received_recipe(pid, keys[0], source="import", audio_keys=keys, title=title,
                                                      dish_id=dish_id, cook_name=project.get("storyteller_name"))
    events_service.track("recipe_created", project_id=pid, recipe_id=recipe_id, actor="buyer", source=source)
    pipeline_service.enqueue_processing(recipe_id)
    flash("Got it. We're writing the recipe down; it takes about a minute.", "success")
    if over_quota:  # never turn a voice note away; extra pages wait for Volume 2
        flash("Your book is already full, so this one is saved as an extra for a second volume.", "info")
    return redirect(url_for("screens.review", project_id=pid, recipe_id=recipe_id))


def _replace_notes(project, recipe, keys, source):
    recipe_service.replace_audio(recipe["id"], keys, source=source)
    events_service.track("recipe_retry_requested", project_id=project["id"], recipe_id=recipe["id"], actor="buyer",
                         stage="transcribe")
    pipeline_service.enqueue_processing(recipe["id"])
    flash("Got it. We're writing it down again from the new voice note.", "success")
    return redirect(url_for("screens.review", project_id=project["id"], recipe_id=recipe["id"]))


# ─── Share from WhatsApp (S3, Android) ─────────────────────────
# The installed app is a share target (manifest share_target): WhatsApp → Share → Andaaz posts
# the voice notes to /share. We keep them, then ask which book and dish they belong to.

SHARED_KEY = "shared_notes"


@bp.route("/share", methods=["POST"])
@login_required
def share_target():
    files = [f for f in request.files.getlist("audio_files") if f and f.filename]
    files = [f for f in files if is_allowed_audio(f.filename, f.mimetype)][:MAX_IMPORT_FILES]
    projects = project_service.get_user_projects(current_user.id)
    if not projects:
        flash("Set up your book first, then share the voice notes again.", "error")
        return redirect(url_for("screens.start"))
    if not files:
        flash("That share didn't include a voice note. Choose the files here instead.", "error")
        return redirect(url_for("screens.import_notes", project_id=projects[0]["id"]))
    _drop_shared()  # an earlier share that was never placed
    flask_session[SHARED_KEY] = {"user": current_user.id, "keys": [_store_upload(f) for f in files]}
    return redirect(url_for("screens.share_choose"))


@bp.route("/share", methods=["GET"])
@login_required
def share_choose():
    """Where do the shared notes go: a wishlist dish, a new dish, or instead of a page's voice note."""
    keys = _shared_keys()
    projects = project_service.get_user_projects(current_user.id)
    if not keys or not projects:
        return redirect(url_for("screens.home_redirect"))
    project = next((p for p in projects if p["id"] == request.args.get("book", type=int)), projects[0])
    recipes = recipe_service.get_project_recipes(project["id"])
    return _render("app/share.html", project, count=len(keys), books=projects,
                   dishes=[d for d in dish_service.list_dishes(project["id"]) if d["status"] == "wishlist"],
                   redo=[r for r in recipes if r["status"] in ("needs_review", "failed")],
                   back_url=url_for("screens.home", project_id=project["id"]))


@bp.route("/p/<int:project_id>/share", methods=["POST"])
@owned_project
def share_place(project):
    keys = _shared_keys()
    if not keys:
        flash("Those voice notes have already been added.", "info")
        return redirect(url_for("screens.home", project_id=project["id"]))
    choice = request.form.get("place", "")
    if choice.startswith("redo-"):
        recipe = _recipe_or_404(project, int(choice[5:]) if choice[5:].isdigit() else 0)
        flask_session.pop(SHARED_KEY, None)
        return _replace_notes(project, recipe, keys, "share")
    wishlist = [d for d in dish_service.list_dishes(project["id"]) if d["status"] == "wishlist"]
    dish = next((d for d in wishlist if choice == f"dish-{d['id']}"), None)
    typed = dish_service.clean_titles([request.form.get("new_dish", "")])
    flask_session.pop(SHARED_KEY, None)
    return _add_dish(project, keys, dish["id"] if dish else None,
                     dish["title"] if dish else (typed[0] if typed else None), source="share")


@bp.route("/share/cancel", methods=["POST"])
@login_required
def share_cancel():
    _drop_shared()
    flash("Left out. Nothing was added.", "info")
    return redirect(url_for("screens.home_redirect"))


def _shared_keys():
    pending = flask_session.get(SHARED_KEY) or {}
    return pending.get("keys") if pending.get("user") == current_user.id else None


def _drop_shared():
    pending = flask_session.pop(SHARED_KEY, None) or {}
    recipe_service.discard_audio(pending.get("keys") or [])


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
    kind = request.args.get("kind") if request.args.get("kind") in ("story", "replace") else "original"
    recipe = None
    if kind in ("story", "replace"):
        recipe = _recipe_or_404(project, request.args.get("recipe", type=int))
    wishlist = [d for d in dish_service.list_dishes(pid) if d["status"] == "wishlist"]
    dish = next((d for d in wishlist if d["id"] == request.args.get("dish", type=int)), None)
    if kind == "original" and dish is None and wishlist and "dish" not in request.args:
        dish = wishlist[0]
    return _render("app/record.html", project, tab="record", kind=kind, recipe=recipe, dish=dish, dishes=wishlist,
                   prompts=PROMPTS["story" if kind == "story" else "original"],
                   back_url=url_for("screens.review", project_id=pid, recipe_id=recipe["id"]) if recipe
                   else url_for("screens.home", project_id=pid))


@bp.route("/p/<int:project_id>/uploads", methods=["POST"])
@owned_project
def upload_open(project):
    body = request.get_json(silent=True) or {}
    kind = body.get("kind", "original")
    recipe_id = dish_id = None
    if kind in ("story", "replace"):
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
        elif session["kind"] == "replace":
            recipe_service.replace_audio(session["recipe_id"], [key], source="app",
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
    if session["kind"] in ("original", "replace"):
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
    asked = [d for d in dish_service.list_dishes(pid) if d["source"] == "family" and d["status"] != "requested"]
    return _render("app/family.html", project, tab="family", book_url=book_url,
                   join_url=f"{book_url}/join", members=project_service.get_members(pid),
                   pending=family_service.pending_requests(pid), requested=asked)


@bp.route("/p/<int:project_id>/family/requests/<int:dish_id>", methods=["POST"])
@owned_project
def decide_request(project, dish_id):
    approve = request.form.get("decision") == "approve"
    if family_service.decide(project["id"], dish_id, approve):
        flash("Added to the list." if approve else "Hidden. The family won't see it again.", "success")
    return redirect(url_for("screens.family", project_id=project["id"]))


@bp.route("/p/<int:project_id>/family/members/<int:member_id>/remove", methods=["POST"])
@owned_project
def remove_member(project, member_id):
    family_service.remove_member(project["id"], member_id)
    return redirect(url_for("screens.family", project_id=project["id"]))


@bp.route("/p/<int:project_id>/family/new-link", methods=["POST"])
@owned_project
def new_family_link(project):
    listen_service.regenerate_book(project["id"])
    flash("New family link made. The old link and the book's QR code no longer work; recipe QR codes still do.",
          "success")
    return redirect(url_for("screens.family", project_id=project["id"]))


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
                   steps=SETUP_STEPS[project["cook_mode"]], order=payment_service.paid_order(project["id"]))


# ─── Design your book R14 (module 18) ──────────────────────────

DESIGN_TEXT_FIELDS = {"title": 80, "subtitle": 120, "dedication": 400, "about_author": 1500,
                      "introduction": 200, "acknowledgement": 800}
PHOTO_SLOTS = {"cook": "cook_photo_key", "family": "family_photo_key"}


@bp.route("/p/<int:project_id>/design", methods=["GET", "POST"])
@owned_project
def design(project):
    pid = project["id"]
    if request.method == "POST":
        values = book_design.validate(request.form, project)
        for field, limit in DESIGN_TEXT_FIELDS.items():
            if field in request.form:
                values[field] = request.form[field].strip()[:limit]
        if not values.get("title", project["title"]):
            values.pop("title")
        project_service.update_design(pid, **values)
        events_service.track("book_design_saved", project_id=pid, actor="buyer",
                             style=values.get("theme", project.get("theme")))
        flash("Saved. Make the book PDF again to see the changes.", "success")
        return redirect(url_for("screens.design", project_id=pid))
    approved = [r for r in recipe_service.get_project_recipes(pid) if r["status"] == "approved"]
    return _render("app/design.html", project, tab="book", approved=approved,
                   styles=book_design.STYLES, sizes=book_design.SIZES, layouts=book_design.COVER_LAYOUTS,
                   style=book_design.style_key(project), size=book_design.size_key(project),
                   accent=book_design.accent(project), layout=book_design.cover_layout(project),
                   latest_pdf=project_service.latest_book_pdf(pid), back_url=url_for("screens.book", project_id=pid))


def _save_upload(prefix):
    """The uploaded photo's storage key, or None after flashing why it couldn't be used."""
    upload = request.files.get("photo")
    if not upload or not upload.filename:
        flash("Pick a photo first.", "error")
        return None
    try:
        return photo_service.save_photo(upload.stream, prefix)
    except photo_service.PhotoError as exc:
        flash(str(exc), "error")
        return None


@bp.route("/p/<int:project_id>/photos/<slot>", methods=["POST"])
@owned_project
def book_photo(project, slot):
    """The cook's photo (cover, About the cook) or the family photo; `remove` takes it off."""
    if slot not in PHOTO_SLOTS:
        abort(404)
    field = PHOTO_SLOTS[slot]
    key = None if request.form.get("remove") else _save_upload(f"p{project['id']}-{slot}")
    if key or request.form.get("remove"):
        crops = {k: v for k, v in (project.get("photo_crops") or {}).items() if k != slot}  # a new photo starts centred
        project_service.update_design(project["id"], **{field: key, "photo_crops": crops})
        photo_service.delete_photo(project.get(field))
    nxt = request.form.get("next")
    nxt = nxt if _safe_next(nxt) else url_for("screens.design", project_id=project["id"])
    if key:  # straight on to fitting it into its spot
        return redirect(url_for("screens.photo_fit", project_id=project["id"], slot=slot, next=nxt))
    return redirect(nxt)


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/photo", methods=["POST"])
@owned_project
def recipe_photo(project, recipe_id):
    recipe = _recipe_or_404(project, recipe_id)
    key = None if request.form.get("remove") else _save_upload(f"p{project['id']}-r{recipe['id']}")
    if key or request.form.get("remove"):
        photo_service.delete_photo(recipe_service.set_photo(recipe["id"], key))
        if recipe["status"] == "approved" and recipe.get("pdf_filename"):
            _make_pdf(recipe["id"])  # the page's PDF shows the photo
    nxt = request.form.get("next")
    nxt = nxt if _safe_next(nxt) else url_for("screens.review", project_id=project["id"], recipe_id=recipe_id)
    if key:
        return redirect(url_for("screens.photo_fit", project_id=project["id"], slot=f"r{recipe_id}", next=nxt))
    return redirect(nxt)


@bp.route("/p/<int:project_id>/r/<int:recipe_id>/photo/find", methods=["GET", "POST"])
@owned_project
def find_dish_photo(project, recipe_id):
    """No photo of the dish? Pick one other books used, or a free-licence one from the internet."""
    recipe = _recipe_or_404(project, recipe_id)
    nxt = request.values.get("next")
    nxt = nxt if _safe_next(nxt) else url_for("screens.review", project_id=project["id"], recipe_id=recipe_id)
    query = (request.values.get("q") or recipe.get("recipe_title") or "").strip()[:80]
    if request.method == "POST":
        pick, prefix = request.form.get("pick") or "", f"p{project['id']}-r{recipe['id']}"
        try:
            if pick.startswith("lib-") and pick[4:].isdigit():
                image = dish_photo_service.get_library_image(int(pick[4:])) or abort(404)
            elif pick.startswith("web-") and pick.count("-") >= 2:
                _, source, source_id = pick.split("-", 2)
                image = dish_photo_service.add_web_photo(recipe.get("recipe_title") or query, source, source_id)
            else:
                abort(400)
            key, credit = dish_photo_service.use_library_image(image, prefix)
        except (dish_photo_service.DishPhotoError, photo_service.PhotoError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("screens.find_dish_photo", project_id=project["id"], recipe_id=recipe_id,
                                    q=query, next=nxt))
        photo_service.delete_photo(recipe_service.set_photo(recipe["id"], key, credit=credit, image_id=image["id"]))
        if recipe["status"] == "approved" and recipe.get("pdf_filename"):
            _make_pdf(recipe["id"])
        events_service.track("dish_photo_picked", project_id=project["id"], actor="buyer",
                             source="library" if pick.startswith("lib-") else image["source"])
        return redirect(url_for("screens.photo_fit", project_id=project["id"], slot=f"r{recipe_id}", next=nxt))

    library = dish_photo_service.library_matches(query)
    web, error = [], None
    if request.args.get("q") or not library:  # the library alone answers the first look when it can
        try:
            web = dish_photo_service.search_web(query)
        except dish_photo_service.DishPhotoError as exc:
            error = str(exc)
    used = {(i["source"], i["source_id"]) for i in library}
    web = [w for w in web if (w["source"], w["source_id"]) not in used]
    return _render("app/photo_find.html", project, tab="book", recipe=recipe, query=query, library=library,
                   web=web, error=error, searched=bool(request.args.get("q")) or not library, next_url=nxt,
                   back_url=nxt)


@bp.route("/photos/library/<int:image_id>.jpg")
@login_required
def library_photo(image_id):
    """A small copy of a shared library photo for the photo picker; the library is open to every signed-in buyer."""
    image = dish_photo_service.get_library_image(image_id) or abort(404)
    try:
        data = photo_service.thumbnail(image["storage_key"])
    except Exception:
        abort(404)
    response = current_app.response_class(data, mimetype="image/jpeg")
    response.cache_control.private = True
    response.cache_control.max_age = 86400
    return response


def _photo_spots(project, slot):
    """(photo key, crop, the spots it appears in, title, recipe or None) for a cook, family or r<id> slot."""
    if slot in PHOTO_SLOTS:
        crop = (project.get("photo_crops") or {}).get(slot)
        if slot == "cook":
            places = (["cover"] if book_design.cover_layout(project) == "photo" else []) + ["about"]
            title = f"{cook_label(project)}'s photo"
        else:
            places, title = ["family"], "Family photo"
        return project.get(PHOTO_SLOTS[slot]), crop, [book_design.photo_frame(project, p) for p in places], title, None
    if slot.startswith("r") and slot[1:].isdigit():
        recipe = _recipe_or_404(project, int(slot[1:]))
        frame = book_design.photo_frame(project, pdf_service.dish_photo_place(project, recipe))
        title = recipe.get("recipe_title") or "Dish photo"
        return recipe.get("photo_key"), recipe.get("photo_crop"), [frame], title, recipe
    abort(404)


@bp.route("/p/<int:project_id>/photos/<slot>/fit", methods=["GET", "POST"])
@owned_project
def photo_fit(project, slot):
    """Drag and zoom a photo to sit right in its spot in the book (photo_service crops)."""
    key, crop, frames, title, recipe = _photo_spots(project, slot)
    nxt = request.values.get("next")
    nxt = nxt if _safe_next(nxt) else url_for("screens.design", project_id=project["id"]) + "#photos"
    if not key:
        return redirect(nxt)
    if request.method == "POST":
        crop = photo_service.clean_crop(request.form)
        if recipe is None:
            project_service.update_design(project["id"], photo_crops={**(project.get("photo_crops") or {}), slot: crop})
        else:
            recipe_service.set_photo_crop(recipe["id"], crop)
            if recipe["status"] == "approved" and recipe.get("pdf_filename"):
                _make_pdf(recipe["id"])
        events_service.track("photo_fitted", project_id=project["id"], actor="buyer", slot=slot[:1])
        flash("Saved. Make the book PDF again to see it in place.", "success")
        return redirect(nxt)
    return _render("app/photo_fit.html", project, tab="book", slot=slot, title=title, frames=frames,
                   crop=photo_service.clean_crop(crop), max_zoom=photo_service.MAX_ZOOM, next_url=nxt,
                   photo_url=url_for("screens.book_photo_file", project_id=project["id"], slot=slot, v=key[-8:]),
                   back_url=nxt)


@bp.route("/p/<int:project_id>/photos/<slot>.jpg")
@owned_project
def book_photo_file(project, slot):
    """A photo for the owner's own screens; slot is cook, family or r<recipe id>."""
    if slot in PHOTO_SLOTS:
        key = project.get(PHOTO_SLOTS[slot])
    elif slot.startswith("r") and slot[1:].isdigit():
        key = _recipe_or_404(project, int(slot[1:])).get("photo_key")
    else:
        abort(404)
    if not key or not storage_service.exists("photos", key):
        abort(404)
    return storage_service.send("photos", key)


# ─── Whole book and reveal day R12 ─────────────────────────────

@bp.route("/p/<int:project_id>/book/compile", methods=["POST"])
@owned_project
def compile_book(project):
    nxt = request.form.get("next")
    back = nxt if _safe_next(nxt) else url_for("screens.book", project_id=project["id"])
    approved = [recipe_service.get_recipe(r["id"]) for r in recipe_service.get_project_recipes(project["id"])
                if r["status"] == "approved"]
    if not approved:
        flash("Approve at least one page first.", "error")
        return redirect(back)
    try:
        key = pdf_service.generate_book_pdf(project, approved)
    except Exception:
        current_app.logger.exception("Book PDF failed for project %s", project["id"])
        flash("We couldn't make the book PDF just now. Please try again in a minute.", "error")
        return redirect(back)
    project_service.save_book_pdf(project["id"], key)
    events_service.track("book_compiled", project_id=project["id"], actor="buyer", recipes=len(approved))
    flash(f"The book is ready: {len(approved)} page{'s' if len(approved) != 1 else ''}.", "success")
    return redirect(back)


@bp.route("/p/<int:project_id>/book/print.pdf")
@owned_project
def book_print_file(project):
    """The print-shop PDF: same book with 3 mm bleed and crop marks. Made fresh each time."""
    approved = [recipe_service.get_recipe(r["id"]) for r in recipe_service.get_project_recipes(project["id"])
                if r["status"] == "approved"]
    if not approved:
        abort(404)
    key = pdf_service.generate_book_pdf(project, approved, print_ready=True)
    events_service.track("book_print_pdf_made", project_id=project["id"], actor="buyer",
                         size=book_design.size_key(project))
    return storage_service.send("pdfs", key, download_name=f"{project['title']} (print).pdf")


@bp.route("/p/<int:project_id>/book.pdf")
@owned_project
def book_file(project):
    latest = project_service.latest_book_pdf(project["id"])
    if latest is None:
        abort(404)
    return storage_service.send("pdfs", latest["storage_key"], download_name=f"{project['title']}.pdf")


@bp.route("/p/<int:project_id>/reveal", methods=["GET", "POST"])
@owned_project
def reveal(project):
    pid = project["id"]
    approved = [r for r in recipe_service.get_project_recipes(pid) if r["status"] == "approved"]
    if request.method == "POST":
        if not approved:
            flash("There's nothing to reveal yet. Approve a page first, or pick a later date.", "error")
            return redirect(url_for("screens.reveal", project_id=pid))
        project_service.reveal(pid)
        events_service.track("book_revealed", project_id=pid, actor="buyer", recipes=len(approved))
        flash("Revealed. The family can now open every approved page.", "success")
        return redirect(url_for("screens.reveal", project_id=pid))
    book_url = listen_service.book_url(project["book_token"])
    return _render("app/reveal.html", project, tab="book", approved=approved,
                   book_url=book_url, latest_pdf=project_service.latest_book_pdf(pid),
                   share_link=copy.wa_link(copy.reveal_text(project, book_url)),
                   days_left=days_until(project.get("reveal_date")),
                   back_url=url_for("screens.book", project_id=pid))

import os
import json
import socket
import tempfile
from datetime import timedelta
from flask import (
    Flask,
    render_template,
    session,
    request,
    redirect,
    url_for,
    flash,
    Response,
    abort,
    send_from_directory,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_wtf.csrf import CSRFProtect
import config
from models.database import init_db
from services import (
    dish_service,
    events_service,
    family_service,
    listen_service,
    pdf_service,
    pipeline_service,
    project_service,
    qr_service,
    recipe_service,
    storage_service,
    user_service,
)
from services.audio_utils import SUPPORTED_FORMATS_LABEL, build_storage_filename, is_allowed_audio
from services.ui import cook_display_name, days_until, status_chip
import screens

if not config.FLASK_DEBUG and config.FLASK_SECRET_KEY in config.PLACEHOLDER_SECRET_KEYS:
    raise RuntimeError("Set FLASK_SECRET_KEY to a long random string before running with FLASK_DEBUG off.")

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
# Stay signed in on the phone: sharing a voice note from WhatsApp into the app (/share) must not
# land on the sign-in page, which would drop the shared files.
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=180)
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_SECURE"] = not config.FLASK_DEBUG
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "error"


app.register_blueprint(screens.bp)
# The OS share sheet posts here without our CSRF token; it only ever adds the user's own files to their own book.
csrf.exempt(screens.share_target)
# Razorpay can't send our CSRF token; the webhook checks Razorpay's signature instead.
csrf.exempt(screens.razorpay_webhook)
app.jinja_env.globals.update(status_chip=status_chip, days_until=days_until, cook_display_name=cook_display_name)


@app.context_processor
def inject_config():
    return {"config": config}


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.email = user_dict["email"]
        self.name = user_dict["name"]
        self.auth_provider = user_dict.get("auth_provider", "email")


@login_manager.user_loader
def load_user(user_id):
    user_dict = user_service.get_user_by_id(int(user_id))
    if user_dict:
        return User(user_dict)
    return None


# ─── Auth Routes ────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("auth/register.html")

    email = request.form.get("email", "").strip()
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not email or not name or not password:
        flash("All fields are required.", "error")
        return redirect(url_for("register"))

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("register"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("register"))

    existing = user_service.get_user_by_email(email)
    if existing:
        flash("An account with this email already exists.", "error")
        return redirect(url_for("register"))

    user_dict = user_service.create_user(email, name, password)
    if user_dict:
        login_user(User(user_dict), remember=True)
        flash(f"Welcome, {name}!", "success")
        return redirect(url_for("dashboard"))

    flash("Registration failed. Please try again.", "error")
    return redirect(url_for("register"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user_dict = user_service.get_user_by_email(email)
    if not user_dict or not user_service.verify_password(user_dict, password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("login"))

    login_user(User(user_dict), remember=True)
    flash(f"Welcome back, {user_dict['name']}!", "success")

    next_page = request.args.get("next") or ""
    safe = next_page.startswith("/") and not next_page.startswith("//") and "\\" not in next_page
    return redirect(next_page if safe else url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ─── Google OAuth (SSO) ─────────────────────────────────────────

if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    @app.route("/login/google")
    def login_google():
        redirect_uri = url_for("auth_google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/google/callback")
    def auth_google_callback():
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            flash("Google login failed.", "error")
            return redirect(url_for("login"))

        user_dict = user_service.get_or_create_oauth_user(
            email=userinfo["email"],
            name=userinfo.get("name", userinfo["email"]),
            provider="google",
            provider_id=userinfo["sub"],
        )
        login_user(User(user_dict), remember=True)
        flash(f"Welcome, {user_dict['name']}!", "success")
        return redirect(url_for("dashboard"))


# ─── Public Routes ──────────────────────────────────────────────

@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/sw.js")
def service_worker():
    # Served from the root so the worker can control every page, not just /static/.
    response = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/manifest.webmanifest")
def web_manifest():
    with open(os.path.join(app.static_folder, "manifest.webmanifest"), encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["name"] = manifest["short_name"] = config.APP_NAME
    return Response(json.dumps(manifest), mimetype="application/manifest+json")


@app.route("/offline")
def offline():
    return render_template("offline.html")


# ─── Public listen pages (PRD §8.5) ─────────────────────────────
# Printed QR codes point at these paths forever (QR-4): never rename them without redirects.

@app.route("/l/<token>")
def listen(token):
    recipe = listen_service.get_listen_recipe(token)
    if recipe is None or not recipe["clips"]:
        return render_template("listen_private.html"), 404
    clip_urls = [url_for("listen_audio", token=token, clip_number=n) for n in range(1, len(recipe["clips"]) + 1)]
    source = _listen_source()
    if not events_service.is_bot(request.headers.get("User-Agent")):
        events_service.track("listen_page_viewed", project_id=recipe["project_id"], recipe_id=recipe["id"],
                             actor="anon", channel="qr" if source == "qr" else "web", source=source)
    played_url = url_for("listen_played", token=token, s=source)
    clips = [{"url": url, "label": listen_service.clip_label(recipe["clips"], i)} for i, url in enumerate(clip_urls)]
    return render_template("listen.html", recipe=recipe, token=token, clip_urls=clip_urls, clips=clips,
                           played_url=played_url, voice_name=listen_service.voice_name(recipe))


@app.route("/l/<token>/recipe")
def listen_recipe(token):
    """F3: the written page behind a listen link, once the family has approved it."""
    recipe = listen_service.get_listen_recipe(token)
    if recipe is None:
        return render_template("listen_private.html"), 404
    if recipe["status"] != "approved":
        abort(404)
    page = recipe_service.get_recipe(recipe["id"])
    return render_template("listen_recipe.html", recipe=recipe, page=page, token=token,
                           voice_name=listen_service.voice_name(recipe))


@app.route("/l/<token>/audio/<int:clip_number>")
def listen_audio(token, clip_number):
    storage_key = listen_service.get_clip_storage_key(token, clip_number)
    if storage_key is None:
        abort(404)
    # Streams locally; on S3/R2 redirects to a short-lived signed URL (QR-5).
    response = storage_service.send("audio", storage_key)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/l/<token>/played", methods=["POST"])
@csrf.exempt
def listen_played(token):
    if events_service.is_bot(request.headers.get("User-Agent")):
        return "", 204
    if not listen_service.record_play(token, source=_listen_source(), is_owner=_is_listen_owner(token)):
        abort(404)
    return "", 204


def _listen_source():
    source = request.args.get("s", "link")
    return source if source in ("qr", "link", "book", "app") else "link"


def _is_listen_owner(token):
    if not current_user.is_authenticated:
        return False
    recipe = listen_service.get_listen_recipe(token)
    project = project_service.get_project(recipe["project_id"]) if recipe else None
    return bool(project and project["user_id"] == current_user.id)


@app.route("/b/<token>")
def book(token):
    owner = _is_book_owner(token)
    book = listen_service.get_book(token, preview=owner)
    if book is None:
        return render_template("listen_private.html"), 404
    if not owner and not events_service.is_bot(request.headers.get("User-Agent")):
        events_service.track("book_page_viewed", project_id=book["id"], actor="anon")
    has_pdf = not book["surprise"] and project_service.latest_book_pdf(book["id"]) is not None
    return render_template("book_listen.html", book=book, preview=owner and book["surprise"], has_pdf=has_pdf)


@app.route("/b/<token>/book.pdf")
def book_pdf(token):
    book = listen_service.get_book(token, preview=_is_book_owner(token))
    latest = project_service.latest_book_pdf(book["id"]) if book else None
    if latest is None or (book["surprise"] and not _is_book_owner(token)):
        abort(404)
    events_service.track("book_pdf_downloaded", project_id=book["id"], actor="anon")
    return storage_service.send("pdfs", latest["storage_key"], download_name=f"{book['title']}.pdf")


def _is_book_owner(token):
    if not current_user.is_authenticated:
        return False
    return any(p["book_token"] == token for p in project_service.get_user_projects(current_user.id))


@app.route("/b/<token>/join", methods=["GET", "POST"])
def book_join(token):
    """F4: a family member joins with just a name and asks for a dish. No login."""
    book = listen_service.get_book(token)
    if book is None:
        return render_template("listen_private.html"), 404
    joined = session.get("family", {})
    member = family_service.get_member(book["id"], joined.get(str(book["id"]))) if joined.get(str(book["id"])) else None
    cook = book["storyteller_address_as"] or (book["storyteller_name"] or "").split(" ")[0] or "the cook"
    if request.method == "GET":
        wanted = [d["title"] for d in dish_service.list_dishes(book["id"]) if d["status"] == "wishlist"][:8]
        return render_template("book_join.html", book=book, member=member, cook=cook, wanted=wanted)

    try:
        member_id, is_new = family_service.join(book["id"], request.form.get("name"),
                                                member["id"] if member else None)
    except ValueError:
        return render_template("book_join.html", book=book, member=member, cook=cook, wanted=[],
                               error="Please tell us your name."), 400
    joined[str(book["id"])] = member_id
    session["family"] = joined
    if is_new:
        events_service.track("family_member_joined", project_id=book["id"], actor="family")
    member = family_service.get_member(book["id"], member_id)
    dish = request.form.get("dish_other", "").strip() or request.form.get("dish", "").strip()
    if dish:
        family_service.request_dish(book["id"], member, dish)
        events_service.track("dish_requested", project_id=book["id"], actor="family")
    return render_template("book_join_done.html", book=book, member=member, cook=cook, dish=dish, token=token)


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("screens.home_redirect"))
    return render_template("app/welcome.html")


# ─── Dashboard ──────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    """Where sign-in and the installed app land: the latest book, or onboarding."""
    return redirect(url_for("screens.home_redirect"))


@app.route("/projects")
@login_required
def project_list():
    projects = project_service.get_user_projects(current_user.id)
    return render_template("dashboard.html", projects=projects)


# ─── Project Routes ─────────────────────────────────────────────

@app.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "GET":
        return render_template("projects/new.html", themes=config.COOKBOOK_THEMES)

    data = _project_form_data()
    if not data["title"]:
        flash("Project title is required.", "error")
        return redirect(url_for("project_new"))

    project_id = project_service.create_project(user_id=current_user.id, **data)
    flash(f'Project "{data["title"]}" created!', "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()
    recipes = recipe_service.get_project_recipes(project_id)
    return render_template(
        "projects/detail.html", project=project, recipes=recipes, themes=config.COOKBOOK_THEMES
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    if request.method == "GET":
        return render_template("projects/edit.html", project=project, themes=config.COOKBOOK_THEMES)

    data = _project_form_data()

    if not data["title"]:
        flash("Title is required.", "error")
        return redirect(url_for("project_edit", project_id=project_id))

    project_service.update_project(project_id, data)
    flash("Project updated!", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def project_delete(project_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    project_service.delete_project(project_id)
    flash("Project deleted.", "success")
    return redirect(url_for("dashboard"))


# ─── Recipe Routes (project-scoped) ────────────────────────────

@app.route("/projects/<int:project_id>/upload", methods=["GET", "POST"])
@login_required
def upload(project_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    if request.method == "GET":
        return render_template("upload.html", project=project)

    if "audio_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("upload", project_id=project_id))

    file = request.files["audio_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("upload", project_id=project_id))

    if not is_allowed_audio(file.filename, file.mimetype):
        flash(f"Invalid file type. Please upload {SUPPORTED_FORMATS_LABEL}.", "error")
        return redirect(url_for("upload", project_id=project_id))

    recipe_count = project_service.get_project_recipe_count(project_id)
    if recipe_count >= project["max_recipes"]:
        flash(f"This project has reached its maximum of {project['max_recipes']} recipes.", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    filename = build_storage_filename(file.filename, file.mimetype)
    handle, temp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
    os.close(handle)
    try:
        file.save(temp_path)
        storage_service.save_file("audio", filename, temp_path, content_type=file.mimetype)
    finally:
        os.remove(temp_path)

    row_id = recipe_service.create_received_recipe(project_id, filename)
    events_service.track("recipe_created", project_id=project_id, recipe_id=row_id, actor="buyer", source="upload")
    pipeline_service.enqueue_processing(row_id)

    status = recipe_service.get_recipe(row_id)["status"]
    if status == "failed":
        flash("We couldn't turn this recording into a recipe. Please try again or upload another note.", "error")
        return redirect(url_for("upload", project_id=project_id))
    if status == "needs_review":
        flash("Recipe uploaded and processed successfully!", "success")
    else:
        flash("Got it! We're writing the recipe down. Refresh this page in a minute.", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=row_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>")
@login_required
def recipe_detail(project_id, recipe_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    recipe = _get_project_recipe(project_id, recipe_id)
    if recipe is None:
        return _recipe_not_found(project_id)
    listen_url = None
    if recipe["listen_revoked_at"] is None and recipe["audio_clips"]:
        listen_url = listen_service.listen_url(recipe["listen_token"])
    return render_template(
        "recipe_detail.html",
        recipe=recipe,
        project=project,
        listen_url=listen_url,
        qr_data_uri=(qr_service.make_qr_data_uri(listen_service.listen_url(recipe["listen_token"], source="qr"))
                     if listen_url else None),
        play_count=listen_service.play_count(recipe_id),
    )


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/qr.<fmt>")
@login_required
def recipe_qr(project_id, recipe_id, fmt):
    if _get_owned_project(project_id) is None:
        return _project_not_found()
    recipe = _get_project_recipe(project_id, recipe_id)
    if recipe is None or recipe["listen_revoked_at"] is not None:
        return _recipe_not_found(project_id)
    events_service.track("qr_downloaded", project_id=project_id, recipe_id=recipe_id, actor="buyer",
                         format=fmt, target="recipe")
    return _qr_response(listen_service.listen_url(recipe["listen_token"], source="qr"), fmt, f"listen-{recipe_id}")


@app.route("/projects/<int:project_id>/qr.<fmt>")
@login_required
def project_qr(project_id, fmt):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()
    events_service.track("qr_downloaded", project_id=project_id, actor="buyer", format=fmt, target="book")
    return _qr_response(listen_service.book_url(project["book_token"]), fmt, f"cookbook-{project_id}")


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/listen-link/<action>", methods=["POST"])
@login_required
def recipe_listen_link(project_id, recipe_id, action):
    if _get_owned_project(project_id) is None:
        return _project_not_found()
    if _get_project_recipe(project_id, recipe_id) is None or action not in ("revoke", "regenerate"):
        return _recipe_not_found(project_id)
    if action == "revoke":
        listen_service.revoke(recipe_id)
        events_service.track("listen_link_revoked", project_id=project_id, recipe_id=recipe_id, actor="buyer")
        flash("Listen link turned off. The QR code now shows \"This recording is private\".", "success")
    else:
        listen_service.regenerate(recipe_id)
        events_service.track("listen_link_regenerated", project_id=project_id, recipe_id=recipe_id, actor="buyer")
        flash("New listen link created. Old QR codes no longer work; regenerate the PDF to print the new one.",
              "success")
    if screens._safe_next(request.form.get("next")):
        return redirect(request.form["next"])
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
def recipe_edit(project_id, recipe_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    recipe = _get_project_recipe(project_id, recipe_id)
    if recipe is None:
        return _recipe_not_found(project_id)

    if request.method == "GET":
        return render_template("recipe_edit.html", recipe=recipe, project=project)

    data = {
        "recipe_title": request.form.get("recipe_title", ""),
        "category": request.form.get("category", ""),
        "family_note": request.form.get("family_note", ""),
        "serves": request.form.get("serves", ""),
        "prep_time_minutes": _to_int(request.form.get("prep_time_minutes")),
        "cook_time_minutes": _to_int(request.form.get("cook_time_minutes")),
        "difficulty": request.form.get("difficulty", ""),
        "ingredients_json": request.form.get("ingredients_json", "[]"),
        "method_steps_json": request.form.get("method_steps_json", "[]"),
        "moms_tips_json": request.form.get("moms_tips_json", "[]"),
        "serving_suggestion": request.form.get("serving_suggestion", ""),
        "storage_notes": request.form.get("storage_notes", ""),
        "unclear_items_for_review_json": request.form.get(
            "unclear_items_for_review_json", "[]"
        ),
    }

    for field in [
        "ingredients_json",
        "method_steps_json",
        "moms_tips_json",
        "unclear_items_for_review_json",
    ]:
        try:
            json.loads(data[field])
        except json.JSONDecodeError:
            flash(f"Invalid JSON in {field.replace('_json', '')}.", "error")
            return redirect(url_for("recipe_edit", project_id=project_id, recipe_id=recipe_id))

    recipe_service.update_recipe(recipe_id, data)
    events_service.track("recipe_edited", project_id=project_id, recipe_id=recipe_id, actor="buyer",
                         fields_changed=_count_changed_fields(recipe, data))
    flash("Recipe updated successfully!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/approve", methods=["POST"])
@login_required
def recipe_approve(project_id, recipe_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    if _get_project_recipe(project_id, recipe_id) is None:
        return _recipe_not_found(project_id)

    recipe_service.approve_recipe(recipe_id)
    events_service.track("recipe_approved", project_id=project_id, recipe_id=recipe_id, actor="buyer")
    flash("Recipe approved!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/generate-pdf", methods=["POST"])
@login_required
def recipe_generate_pdf(project_id, recipe_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    recipe = _get_project_recipe(project_id, recipe_id)
    if recipe is None:
        return _recipe_not_found(project_id)

    try:
        pdf_filename = pdf_service.generate_recipe_pdf(recipe)
    except Exception as e:
        flash(f"PDF generation failed: {e}", "error")
        return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))

    recipe_service.mark_pdf_generated(recipe_id, pdf_filename)
    flash("PDF generated successfully!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/pdf")
@login_required
def recipe_pdf(project_id, recipe_id):
    project = _get_owned_project(project_id)
    if project is None:
        return _project_not_found()

    recipe = _get_project_recipe(project_id, recipe_id)
    if recipe is None or not recipe["pdf_filename"]:
        return _recipe_not_found(project_id)
    return storage_service.send("pdfs", recipe["pdf_filename"])


def _count_changed_fields(recipe, data):
    changed = 0
    for field, value in data.items():
        before = recipe.get(field)
        if field.endswith("_json"):
            changed += json.loads(before or "[]") != json.loads(value or "[]")
        else:
            changed += (before if before is not None else "") != (value if value is not None else "")
    return changed


def _qr_response(url, fmt, download_stem):
    if fmt == "svg":
        response = Response(qr_service.make_qr_svg(url), mimetype="image/svg+xml")
    elif fmt == "png":
        response = Response(qr_service.make_qr_png(url), mimetype="image/png")
    else:
        abort(404)
    if request.args.get("download"):
        response.headers["Content-Disposition"] = f'attachment; filename="{download_stem}.{fmt}"'
    return response


def _get_owned_project(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        return None
    return project


def _get_project_recipe(project_id, recipe_id):
    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None or recipe["project_id"] != project_id:
        return None
    return recipe


def _project_not_found():
    flash("Project not found.", "error")
    return redirect(url_for("dashboard"))


def _recipe_not_found(project_id):
    flash("Recipe not found.", "error")
    return redirect(url_for("project_detail", project_id=project_id))


def _project_form_data():
    form = request.form
    return {
        "title": form.get("title", "").strip(),
        "subtitle": form.get("subtitle", ""),
        "description": form.get("description", ""),
        "theme": form.get("theme", "classic"),
        "max_recipes": _to_int(form.get("max_recipes")) or 50,
        "max_pages": _to_int(form.get("max_pages")) or 100,
        "acknowledgement": form.get("acknowledgement", ""),
        "about_author": form.get("about_author", ""),
        "dedication": form.get("dedication", ""),
        "introduction": form.get("introduction", ""),
        "cover_note": form.get("cover_note", ""),
        "status": form.get("status", "draft"),
    }


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def _print_startup_urls():
    port = config.FLASK_PORT
    print(f"\n{config.APP_NAME} is running:")
    print(f"  On this computer: http://127.0.0.1:{port}")

    lan_ip = _lan_ip()
    if lan_ip:
        print(f"  On your phone (same Wi-Fi): http://{lan_ip}:{port}")
        print("  Open that address in Safari or Chrome on your phone.")
    else:
        print("  Could not detect a local network IP. Use your computer's Wi-Fi IP with port 5000.")

    print("  Keep this computer awake while you use the app from your phone.\n")


if __name__ == "__main__":
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(config.INSTANCE_FOLDER, exist_ok=True)
    init_db()
    _print_startup_urls()
    app.run(debug=config.FLASK_DEBUG, host=config.FLASK_HOST, port=config.FLASK_PORT)

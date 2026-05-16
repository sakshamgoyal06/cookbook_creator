import os
import json
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
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
from werkzeug.utils import secure_filename
import config
from models.database import init_db
from services import openai_service, recipe_service, pdf_service, user_service, project_service

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "error"


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


def _allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in config.ALLOWED_AUDIO_EXTENSIONS


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
        login_user(User(user_dict))
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

    login_user(User(user_dict))
    flash(f"Welcome back, {user_dict['name']}!", "success")

    next_page = request.args.get("next")
    return redirect(next_page if next_page else url_for("dashboard"))


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
        login_user(User(user_dict))
        flash(f"Welcome, {user_dict['name']}!", "success")
        return redirect(url_for("dashboard"))


# ─── Public Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# ─── Dashboard ──────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    projects = project_service.get_user_projects(current_user.id)
    return render_template("dashboard.html", projects=projects)


# ─── Project Routes ─────────────────────────────────────────────

@app.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "GET":
        return render_template("projects/new.html", themes=config.COOKBOOK_THEMES)

    title = request.form.get("title", "").strip()
    if not title:
        flash("Project title is required.", "error")
        return redirect(url_for("project_new"))

    project_id = project_service.create_project(
        user_id=current_user.id,
        title=title,
        subtitle=request.form.get("subtitle", ""),
        description=request.form.get("description", ""),
        theme=request.form.get("theme", "classic"),
        max_recipes=_to_int(request.form.get("max_recipes")) or 50,
        max_pages=_to_int(request.form.get("max_pages")) or 100,
        acknowledgement=request.form.get("acknowledgement", ""),
        about_author=request.form.get("about_author", ""),
        dedication=request.form.get("dedication", ""),
        introduction=request.form.get("introduction", ""),
        cover_note=request.form.get("cover_note", ""),
    )
    flash(f'Project "{title}" created!', "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))
    recipes = recipe_service.get_project_recipes(project_id)
    return render_template(
        "projects/detail.html", project=project, recipes=recipes, themes=config.COOKBOOK_THEMES
    )


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("projects/edit.html", project=project, themes=config.COOKBOOK_THEMES)

    data = {
        "title": request.form.get("title", "").strip(),
        "subtitle": request.form.get("subtitle", ""),
        "description": request.form.get("description", ""),
        "theme": request.form.get("theme", "classic"),
        "max_recipes": _to_int(request.form.get("max_recipes")) or 50,
        "max_pages": _to_int(request.form.get("max_pages")) or 100,
        "acknowledgement": request.form.get("acknowledgement", ""),
        "about_author": request.form.get("about_author", ""),
        "dedication": request.form.get("dedication", ""),
        "introduction": request.form.get("introduction", ""),
        "cover_note": request.form.get("cover_note", ""),
        "status": request.form.get("status", "draft"),
    }

    if not data["title"]:
        flash("Title is required.", "error")
        return redirect(url_for("project_edit", project_id=project_id))

    project_service.update_project(project_id, data)
    flash("Project updated!", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def project_delete(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    project_service.delete_project(project_id)
    flash("Project deleted.", "success")
    return redirect(url_for("dashboard"))


# ─── Recipe Routes (project-scoped) ────────────────────────────

@app.route("/projects/<int:project_id>/upload", methods=["GET", "POST"])
@login_required
def upload(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("upload.html", project=project)

    if "audio_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("upload", project_id=project_id))

    file = request.files["audio_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("upload", project_id=project_id))

    if not _allowed_file(file.filename):
        flash("Invalid file type. Please upload .mp3, .m4a, .wav, or .ogg.", "error")
        return redirect(url_for("upload", project_id=project_id))

    recipe_count = project_service.get_project_recipe_count(project_id)
    if recipe_count >= project["max_recipes"]:
        flash(f"This project has reached its maximum of {project['max_recipes']} recipes.", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    filename = secure_filename(file.filename)
    filepath = os.path.join(config.UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        transcript = openai_service.transcribe_audio(filepath)
    except Exception as e:
        flash(f"Transcription failed: {e}", "error")
        return redirect(url_for("upload", project_id=project_id))

    if not transcript or not transcript.strip():
        flash("Transcription returned empty text.", "error")
        return redirect(url_for("upload", project_id=project_id))

    try:
        recipe_data = openai_service.structure_recipe(transcript)
    except Exception as e:
        flash(f"Recipe structuring failed: {e}", "error")
        return redirect(url_for("upload", project_id=project_id))

    row_id = recipe_service.save_uploaded_recipe(project_id, filename, transcript, recipe_data)
    flash("Recipe uploaded and processed successfully!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=row_id))


@app.route("/projects/<int:project_id>/recipes")
@login_required
def recipes(project_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))
    all_recipes = recipe_service.get_project_recipes(project_id)
    return render_template("recipes.html", recipes=all_recipes, project=project)


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>")
@login_required
def recipe_detail(project_id, recipe_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None or recipe["project_id"] != project_id:
        flash("Recipe not found.", "error")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("recipe_detail.html", recipe=recipe, project=project)


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
def recipe_edit(project_id, recipe_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None or recipe["project_id"] != project_id:
        flash("Recipe not found.", "error")
        return redirect(url_for("project_detail", project_id=project_id))

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
    flash("Recipe updated successfully!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/approve", methods=["POST"])
@login_required
def recipe_approve(project_id, recipe_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    recipe_service.approve_recipe(recipe_id)
    flash("Recipe approved!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/projects/<int:project_id>/recipes/<int:recipe_id>/generate-pdf", methods=["POST"])
@login_required
def recipe_generate_pdf(project_id, recipe_id):
    project = project_service.get_project(project_id)
    if not project or project["user_id"] != current_user.id:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))

    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None or recipe["project_id"] != project_id:
        flash("Recipe not found.", "error")
        return redirect(url_for("project_detail", project_id=project_id))

    try:
        pdf_filename = pdf_service.generate_recipe_pdf(recipe)
    except Exception as e:
        flash(f"PDF generation failed: {e}", "error")
        return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))

    recipe_service.mark_pdf_generated(recipe_id, pdf_filename)
    flash("PDF generated successfully!", "success")
    return redirect(url_for("recipe_detail", project_id=project_id, recipe_id=recipe_id))


@app.route("/outputs/<filename>")
@login_required
def serve_output(filename):
    return send_from_directory(config.OUTPUT_FOLDER, filename)


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(config.INSTANCE_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)

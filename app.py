import os
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
)
from werkzeug.utils import secure_filename
import config
from models.database import init_db
from services import openai_service, recipe_service, pdf_service

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB


def _allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in config.ALLOWED_AUDIO_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    if "audio_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("upload"))

    file = request.files["audio_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("upload"))

    if not _allowed_file(file.filename):
        flash("Invalid file type. Please upload .mp3, .m4a, .wav, or .ogg.", "error")
        return redirect(url_for("upload"))

    filename = secure_filename(file.filename)
    filepath = os.path.join(config.UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        transcript = openai_service.transcribe_audio(filepath)
    except Exception as e:
        flash(f"Transcription failed: {e}", "error")
        return redirect(url_for("upload"))

    if not transcript or not transcript.strip():
        flash("Transcription returned empty text.", "error")
        return redirect(url_for("upload"))

    try:
        recipe_data = openai_service.structure_recipe(transcript)
    except Exception as e:
        flash(f"Recipe structuring failed: {e}", "error")
        return redirect(url_for("upload"))

    row_id = recipe_service.save_uploaded_recipe(filename, transcript, recipe_data)
    flash("Recipe uploaded and processed successfully!", "success")
    return redirect(url_for("recipe_detail", recipe_id=row_id))


@app.route("/recipes")
def recipes():
    all_recipes = recipe_service.get_all_recipes()
    return render_template("recipes.html", recipes=all_recipes)


@app.route("/recipes/<int:recipe_id>")
def recipe_detail(recipe_id):
    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None:
        flash("Recipe not found.", "error")
        return redirect(url_for("recipes"))
    return render_template("recipe_detail.html", recipe=recipe)


@app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
def recipe_edit(recipe_id):
    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None:
        flash("Recipe not found.", "error")
        return redirect(url_for("recipes"))

    if request.method == "GET":
        return render_template("recipe_edit.html", recipe=recipe)

    import json

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
            return redirect(url_for("recipe_edit", recipe_id=recipe_id))

    recipe_service.update_recipe(recipe_id, data)
    flash("Recipe updated successfully!", "success")
    return redirect(url_for("recipe_detail", recipe_id=recipe_id))


@app.route("/recipes/<int:recipe_id>/approve", methods=["POST"])
def recipe_approve(recipe_id):
    recipe_service.approve_recipe(recipe_id)
    flash("Recipe approved!", "success")
    return redirect(url_for("recipe_detail", recipe_id=recipe_id))


@app.route("/recipes/<int:recipe_id>/generate-pdf", methods=["POST"])
def recipe_generate_pdf(recipe_id):
    recipe = recipe_service.get_recipe(recipe_id)
    if recipe is None:
        flash("Recipe not found.", "error")
        return redirect(url_for("recipes"))

    try:
        pdf_filename = pdf_service.generate_recipe_pdf(recipe)
    except Exception as e:
        flash(f"PDF generation failed: {e}", "error")
        return redirect(url_for("recipe_detail", recipe_id=recipe_id))

    recipe_service.mark_pdf_generated(recipe_id, pdf_filename)
    flash("PDF generated successfully!", "success")
    return redirect(url_for("recipe_detail", recipe_id=recipe_id))


@app.route("/outputs/<filename>")
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

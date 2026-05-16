import json
import uuid
from datetime import datetime, timezone
from models.database import get_connection


def save_uploaded_recipe(project_id, audio_filename, transcript, recipe_data):
    recipe_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO recipes
           (project_id, recipe_id, audio_filename, raw_transcript, recipe_title,
            alternate_names_json, category, family_note, serves,
            prep_time_minutes, cook_time_minutes, difficulty,
            ingredients_json, method_steps_json, moms_tips_json,
            serving_suggestion, storage_notes,
            unclear_items_for_review_json, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            recipe_id,
            audio_filename,
            transcript,
            recipe_data.get("recipe_title", "Untitled"),
            json.dumps(recipe_data.get("alternate_names", [])),
            recipe_data.get("category", ""),
            recipe_data.get("family_note", ""),
            recipe_data.get("serves", ""),
            recipe_data.get("prep_time_minutes"),
            recipe_data.get("cook_time_minutes"),
            recipe_data.get("difficulty", ""),
            json.dumps(recipe_data.get("ingredients", [])),
            json.dumps(recipe_data.get("method_steps", [])),
            json.dumps(recipe_data.get("moms_tips", [])),
            recipe_data.get("serving_suggestion", ""),
            recipe_data.get("storage_notes", ""),
            json.dumps(recipe_data.get("unclear_items_for_review", [])),
            "needs_review",
        ),
    )
    conn.commit()
    row_id = conn.execute(
        "SELECT id FROM recipes WHERE recipe_id = ?", (recipe_id,)
    ).fetchone()["id"]
    conn.close()
    return row_id


def get_recipe(recipe_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def get_project_recipes(project_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM recipes WHERE project_id = ? ORDER BY sort_order, created_at DESC",
        (project_id,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_all_recipes():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM recipes ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_recipe(recipe_id, data):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE recipes SET
           recipe_title = ?, category = ?, family_note = ?,
           serves = ?, prep_time_minutes = ?, cook_time_minutes = ?,
           difficulty = ?, ingredients_json = ?, method_steps_json = ?,
           moms_tips_json = ?, serving_suggestion = ?, storage_notes = ?,
           unclear_items_for_review_json = ?, updated_at = ?
           WHERE id = ?""",
        (
            data.get("recipe_title", ""),
            data.get("category", ""),
            data.get("family_note", ""),
            data.get("serves", ""),
            data.get("prep_time_minutes"),
            data.get("cook_time_minutes"),
            data.get("difficulty", ""),
            data.get("ingredients_json", "[]"),
            data.get("method_steps_json", "[]"),
            data.get("moms_tips_json", "[]"),
            data.get("serving_suggestion", ""),
            data.get("storage_notes", ""),
            data.get("unclear_items_for_review_json", "[]"),
            now,
            recipe_id,
        ),
    )
    conn.commit()
    conn.close()


def approve_recipe(recipe_id):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE recipes SET status = 'approved', updated_at = ? WHERE id = ?",
        (now, recipe_id),
    )
    conn.commit()
    conn.close()


def mark_pdf_generated(recipe_id, pdf_filename):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE recipes SET status = 'pdf_generated', pdf_filename = ?, updated_at = ? WHERE id = ?",
        (pdf_filename, now, recipe_id),
    )
    conn.commit()
    conn.close()


def _row_to_dict(row):
    d = dict(row)
    for key in [
        "alternate_names_json",
        "ingredients_json",
        "method_steps_json",
        "moms_tips_json",
        "unclear_items_for_review_json",
    ]:
        if key in d and d[key]:
            try:
                d[key.replace("_json", "")] = json.loads(d[key])
            except json.JSONDecodeError:
                d[key.replace("_json", "")] = []
        else:
            d[key.replace("_json", "")] = []
    return d

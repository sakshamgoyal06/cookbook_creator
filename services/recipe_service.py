import json
import uuid

from sqlalchemy import func, insert, select, update

from models.database import get_engine, new_token
from models.schema import generated_files, recipe_audio, recipes

JSON_FIELDS = [
    "alternate_names_json",
    "ingredients_json",
    "method_steps_json",
    "moms_tips_json",
    "unclear_items_for_review_json",
]

_latest_pdf = (
    select(generated_files.c.storage_key)
    .where(generated_files.c.recipe_id == recipes.c.id, generated_files.c.kind == "recipe_pdf")
    .order_by(generated_files.c.id.desc())
    .limit(1)
    .scalar_subquery()
    .label("pdf_filename")
)


def create_received_recipe(project_id, audio_filename, source="web"):
    """A recipe row for a voice note that has been stored but not yet processed."""
    with get_engine().begin() as conn:
        row_id = conn.execute(
            insert(recipes)
            .values(
                project_id=project_id,
                recipe_id=str(uuid.uuid4()),
                listen_token=new_token(),
                recipe_title="New recipe",
                status="received",
            )
            .returning(recipes.c.id)
        ).scalar_one()
        conn.execute(
            insert(recipe_audio).values(
                recipe_id=row_id, storage_key=audio_filename, kind="original", play_order=1, source=source
            )
        )
    return row_id


def save_transcript(recipe_id, transcript):
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes)
            .where(recipes.c.id == recipe_id)
            .values(raw_transcript=transcript, status="transcribed", updated_at=func.now())
        )


def save_structured_recipe(recipe_id, recipe_data):
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes)
            .where(recipes.c.id == recipe_id)
            .values(**_structured_values(recipe_data), status="needs_review", updated_at=func.now())
        )


def set_status(recipe_id, status):
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes).where(recipes.c.id == recipe_id).values(status=status, updated_at=func.now())
        )


def _structured_values(recipe_data):
    return {
        "recipe_title": recipe_data.get("recipe_title", "Untitled"),
        "alternate_names_json": recipe_data.get("alternate_names", []),
        "category": recipe_data.get("category", ""),
        "family_note": recipe_data.get("family_note", ""),
        "serves": recipe_data.get("serves", ""),
        "prep_time_minutes": recipe_data.get("prep_time_minutes"),
        "cook_time_minutes": recipe_data.get("cook_time_minutes"),
        "difficulty": recipe_data.get("difficulty", ""),
        "ingredients_json": recipe_data.get("ingredients", []),
        "method_steps_json": recipe_data.get("method_steps", []),
        "moms_tips_json": recipe_data.get("moms_tips", []),
        "serving_suggestion": recipe_data.get("serving_suggestion", ""),
        "storage_notes": recipe_data.get("storage_notes", ""),
        "unclear_items_for_review_json": recipe_data.get("unclear_items_for_review", []),
    }


def save_uploaded_recipe(project_id, audio_filename, transcript, recipe_data):
    with get_engine().begin() as conn:
        row_id = conn.execute(
            insert(recipes)
            .values(
                project_id=project_id,
                recipe_id=str(uuid.uuid4()),
                listen_token=new_token(),
                raw_transcript=transcript,
                **_structured_values(recipe_data),
                status="needs_review",
            )
            .returning(recipes.c.id)
        ).scalar_one()
        if audio_filename:
            conn.execute(
                insert(recipe_audio).values(
                    recipe_id=row_id, storage_key=audio_filename, kind="original", play_order=1, source="web"
                )
            )
    return row_id


def get_recipe(recipe_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(recipes, _latest_pdf).where(recipes.c.id == recipe_id)).mappings().first()
        if row is None:
            return None
        recipe = _row_to_dict(row)
        recipe["audio_clips"] = [
            dict(r)
            for r in conn.execute(
                select(recipe_audio)
                .where(recipe_audio.c.recipe_id == recipe_id)
                .order_by(recipe_audio.c.play_order, recipe_audio.c.id)
            ).mappings()
        ]
    return recipe


def get_project_recipes(project_id):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(recipes, _latest_pdf)
            .where(recipes.c.project_id == project_id)
            .order_by(recipes.c.sort_order, recipes.c.created_at.desc(), recipes.c.id.desc())
        ).mappings().all()
    return [_row_to_dict(r) for r in rows]


def update_recipe(recipe_id, data):
    values = {
        field: data.get(field, "")
        for field in [
            "recipe_title",
            "category",
            "family_note",
            "serves",
            "difficulty",
            "serving_suggestion",
            "storage_notes",
        ]
    }
    values["prep_time_minutes"] = data.get("prep_time_minutes")
    values["cook_time_minutes"] = data.get("cook_time_minutes")
    for field in JSON_FIELDS:
        if field in data:
            values[field] = _parse_json_list(data[field])
    values["updated_at"] = func.now()
    with get_engine().begin() as conn:
        conn.execute(update(recipes).where(recipes.c.id == recipe_id).values(**values))


def approve_recipe(recipe_id):
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes)
            .where(recipes.c.id == recipe_id)
            .values(status="approved", approved_at=func.now(), updated_at=func.now())
        )


def mark_pdf_generated(recipe_id, pdf_filename):
    with get_engine().begin() as conn:
        project_id = conn.execute(
            select(recipes.c.project_id).where(recipes.c.id == recipe_id)
        ).scalar_one()
        conn.execute(
            insert(generated_files).values(
                project_id=project_id, recipe_id=recipe_id, kind="recipe_pdf", storage_key=pdf_filename
            )
        )
        conn.execute(update(recipes).where(recipes.c.id == recipe_id).values(updated_at=func.now()))


def _parse_json_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else []
        except json.JSONDecodeError:
            value = []
    return value if value is not None else []


def _row_to_dict(row):
    """Each list field appears twice: parsed (`ingredients`) and as editable JSON text (`ingredients_json`)."""
    d = dict(row)
    for key in JSON_FIELDS:
        value = _parse_json_list(d.get(key))
        d[key.replace("_json", "")] = value
        d[key] = json.dumps(value, ensure_ascii=False, indent=2)
    return d

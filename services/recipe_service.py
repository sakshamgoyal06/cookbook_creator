import json
import uuid

import logging

from sqlalchemy import delete, func, insert, select, update

from models.database import get_engine, new_token
from models.schema import dishes, generated_files, recipe_audio, recipe_questions, recipes, upload_sessions

JSON_FIELDS = [
    "alternate_names_json",
    "ingredients_json",
    "method_steps_json",
    "moms_tips_json",
    "unclear_items_for_review_json",
]

log = logging.getLogger(__name__)

_latest_pdf = (
    select(generated_files.c.storage_key)
    .where(generated_files.c.recipe_id == recipes.c.id, generated_files.c.kind == "recipe_pdf")
    .order_by(generated_files.c.id.desc())
    .limit(1)
    .scalar_subquery()
    .label("pdf_filename")
)


def create_received_recipe(project_id, audio_filename, source="web", audio_keys=None, title=None,
                           dish_id=None, cook_name=None, content_type=None):
    """A recipe row for voice note(s) that have been stored but not yet processed.

    `audio_keys` lists several clips for one dish, in play order (e.g. imported WhatsApp notes).
    """
    keys = audio_keys or [audio_filename]
    with get_engine().begin() as conn:
        row_id = conn.execute(
            insert(recipes)
            .values(
                project_id=project_id,
                recipe_id=str(uuid.uuid4()),
                listen_token=new_token(),
                recipe_title=title or "New recipe",
                cook_name=cook_name,
                status="received",
            )
            .returning(recipes.c.id)
        ).scalar_one()
        for order, key in enumerate(keys, start=1):
            conn.execute(
                insert(recipe_audio).values(
                    recipe_id=row_id, storage_key=key, kind="original", play_order=order, source=source,
                    content_type=content_type,
                )
            )
        if dish_id is None and title:
            # A typed name that matches a dish on the list is that dish, not a second copy of it.
            dish_id = conn.execute(
                select(dishes.c.id).where(dishes.c.project_id == project_id, dishes.c.recipe_id.is_(None),
                                          func.lower(dishes.c.title) == title.strip().lower())
                .order_by(dishes.c.position).limit(1)
            ).scalar()
        if dish_id is not None:
            conn.execute(
                update(dishes)
                .where(dishes.c.id == dish_id, dishes.c.project_id == project_id, dishes.c.recipe_id.is_(None))
                .values(recipe_id=row_id, status="in_progress")
            )
        else:
            position = conn.execute(
                select(func.coalesce(func.max(dishes.c.position), 0) + 1).where(dishes.c.project_id == project_id)
            ).scalar_one()
            conn.execute(
                insert(dishes).values(project_id=project_id, title=title or "New recipe", position=position,
                                      source="buyer", status="in_progress", recipe_id=row_id)
            )
    return row_id


def add_clip(recipe_id, storage_key, kind="story", source="app", content_type=None):
    """Append a clip (a story, or a follow-up answer) after the recipe's existing clips."""
    with get_engine().begin() as conn:
        order = conn.execute(
            select(func.coalesce(func.max(recipe_audio.c.play_order), 0) + 1)
            .where(recipe_audio.c.recipe_id == recipe_id)
        ).scalar_one()
        conn.execute(
            insert(recipe_audio).values(recipe_id=recipe_id, storage_key=storage_key, kind=kind,
                                        play_order=order, source=source, content_type=content_type)
        )


def replace_audio(recipe_id, audio_keys, source="import", content_type=None):
    """A fresh recording (or upload) for a recipe that went wrong: the old voice notes go, and it starts over."""
    with get_engine().begin() as conn:
        old = conn.execute(select(recipe_audio.c.storage_key).where(recipe_audio.c.recipe_id == recipe_id,
                                                                    recipe_audio.c.kind == "original")).scalars().all()
        conn.execute(delete(recipe_audio).where(recipe_audio.c.recipe_id == recipe_id,
                                                recipe_audio.c.kind == "original"))
        for order, key in enumerate(audio_keys, start=1):
            conn.execute(insert(recipe_audio).values(recipe_id=recipe_id, storage_key=key, kind="original",
                                                     play_order=order, source=source, content_type=content_type))
        _reset(conn, recipe_id)
    _delete_files(old)


def reopen_amounts(recipe_id):
    with get_engine().begin() as conn:
        conn.execute(update(recipes).where(recipes.c.id == recipe_id).values(amounts_checked_at=None))


def restart(recipe_id):
    """Start a recipe over from its voice notes: for a page stuck or gone wrong."""
    with get_engine().begin() as conn:
        _reset(conn, recipe_id)


def _reset(conn, recipe_id):
    conn.execute(delete(recipe_questions).where(recipe_questions.c.recipe_id == recipe_id))
    conn.execute(update(recipes).where(recipes.c.id == recipe_id)
                 .values(status="received", raw_transcript=None, amounts_checked_at=None, approved_at=None,
                         updated_at=func.now()))


def delete_recipe(recipe_id):
    """Remove a recipe, its voice notes and files. Its dish goes back on the list."""
    with get_engine().begin() as conn:
        keys = conn.execute(select(recipe_audio.c.storage_key)
                            .where(recipe_audio.c.recipe_id == recipe_id)).scalars().all()
        pdfs = conn.execute(select(generated_files.c.storage_key)
                            .where(generated_files.c.recipe_id == recipe_id)).scalars().all()
        conn.execute(update(dishes).where(dishes.c.recipe_id == recipe_id)
                     .values(recipe_id=None, status="wishlist"))
        conn.execute(update(upload_sessions).where(upload_sessions.c.recipe_id == recipe_id).values(recipe_id=None))
        for table in (recipe_questions, recipe_audio, generated_files):
            conn.execute(delete(table).where(table.c.recipe_id == recipe_id))
        conn.execute(delete(recipes).where(recipes.c.id == recipe_id))
    _delete_files(keys)
    _delete_files(pdfs, namespace="pdfs")


def _delete_files(keys, namespace="audio"):
    from services import storage_service
    for key in keys:
        try:
            storage_service.delete(namespace, key)
        except Exception:  # a missing file (e.g. wiped by a redeploy) mustn't stop the delete
            log.warning("Could not delete %s/%s", namespace, key, exc_info=True)


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
        conn.execute(update(dishes).where(dishes.c.recipe_id == recipe_id).values(status="done"))


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

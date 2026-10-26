from sqlalchemy import delete, func, insert, select, update

from models.database import get_engine, new_token
from models.schema import family_members, generated_files, projects, recipes, users

EDITABLE_FIELDS = {
    "title": "",
    "subtitle": "",
    "description": "",
    "theme": "classic",
    "max_recipes": 50,
    "max_pages": 100,
    "acknowledgement": "",
    "about_author": "",
    "dedication": "",
    "introduction": "",
    "cover_note": "",
}


def create_project(user_id, title, cook_mode="self", **kwargs):
    values = {field: kwargs.get(field, default) for field, default in EDITABLE_FIELDS.items()}
    values.update(user_id=user_id, title=title, cook_mode=cook_mode, book_token=new_token(), cook_token=new_token())
    with get_engine().begin() as conn:
        project_id = conn.execute(insert(projects).values(**values).returning(projects.c.id)).scalar_one()
        buyer_name = conn.execute(select(users.c.name).where(users.c.id == user_id)).scalar_one()
        conn.execute(
            insert(family_members).values(
                project_id=project_id, name=buyer_name, role="buyer", user_id=user_id, joined_at=func.now()
            )
        )
    return project_id


def get_project(project_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(projects).where(projects.c.id == project_id)).mappings().first()
    return dict(row) if row else None


def get_user_projects(user_id):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(projects)
            .where(projects.c.user_id == user_id)
            .order_by(projects.c.updated_at.desc(), projects.c.id.desc())
        ).mappings().all()
    return [dict(r) for r in rows]


def update_project(project_id, data):
    values = {field: data.get(field, default) for field, default in EDITABLE_FIELDS.items()}
    values.update(status=data.get("status", "draft"), updated_at=func.now())
    with get_engine().begin() as conn:
        conn.execute(update(projects).where(projects.c.id == project_id).values(**values))


def delete_project(project_id):
    # Recipes, audio rows and generated files go with it (ON DELETE CASCADE).
    with get_engine().begin() as conn:
        conn.execute(delete(projects).where(projects.c.id == project_id))


def get_project_recipe_count(project_id):
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count())
            .select_from(recipes)
            .where(recipes.c.project_id == project_id, recipes.c.status != "failed")
        ).scalar_one()


SETUP_FIELDS = {
    "title", "dedication", "cook_mode", "storyteller_name", "storyteller_address_as", "storyteller_phone",
    "storyteller_language", "occasion", "reveal_date", "share_pages_as_ready", "tier", "max_recipes",
    "setup_step", "invite_sent_at",
}


# The R14 "Design your book" screen (module 18).
DESIGN_FIELDS = {
    "theme", "book_size", "book_accent", "cover_layout", "cook_photo_key", "family_photo_key",
    "title", "subtitle", "dedication", "about_author", "introduction", "acknowledgement",
}


def update_design(project_id, **values):
    unknown = set(values) - DESIGN_FIELDS
    if unknown:
        raise ValueError(f"Not a design field: {', '.join(sorted(unknown))}")
    if values:
        with get_engine().begin() as conn:
            conn.execute(update(projects).where(projects.c.id == project_id).values(**values, updated_at=func.now()))


def update_setup(project_id, **values):
    """Save onboarding answers (BUILD_PLAN module 5). Only the listed fields can be set this way."""
    unknown = set(values) - SETUP_FIELDS
    if unknown:
        raise ValueError(f"Not a setup field: {', '.join(sorted(unknown))}")
    with get_engine().begin() as conn:
        conn.execute(update(projects).where(projects.c.id == project_id).values(**values, updated_at=func.now()))


def get_members(project_id):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(family_members)
            .where(family_members.c.project_id == project_id, family_members.c.removed_at.is_(None))
            .order_by(family_members.c.id)
        ).mappings().all()
    return [dict(r) for r in rows]


def save_book_pdf(project_id, storage_key):
    with get_engine().begin() as conn:
        conn.execute(insert(generated_files).values(project_id=project_id, kind="book_pdf", storage_key=storage_key))


def latest_book_pdf(project_id):
    with get_engine().connect() as conn:
        return conn.execute(
            select(generated_files.c.storage_key, generated_files.c.created_at)
            .where(generated_files.c.project_id == project_id, generated_files.c.kind == "book_pdf")
            .order_by(generated_files.c.id.desc()).limit(1)
        ).mappings().first()


def reveal(project_id):
    """Reveal day (BOOK-3): the family sees every approved page from now on."""
    with get_engine().begin() as conn:
        conn.execute(update(projects).where(projects.c.id == project_id, projects.c.revealed_at.is_(None))
                     .values(revealed_at=func.now(), updated_at=func.now()))

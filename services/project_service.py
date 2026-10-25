from sqlalchemy import delete, func, insert, select, update

from models.database import get_engine, new_token
from models.schema import family_members, projects, recipes, users

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

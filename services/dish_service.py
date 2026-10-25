"""The ordered dish wishlist (BUILD_PLAN module 5, UX R6). A dish gets a recipe once something is recorded for it."""
from sqlalchemy import delete, func, insert, select, update

from models.database import get_engine
from models.schema import dishes

MAX_DISHES = 30
MAX_TITLE = 80


def clean_titles(raw_titles):
    """Trim, drop blanks and case-insensitive duplicates, keep order."""
    seen, titles = set(), []
    for raw in raw_titles:
        title = " ".join((raw or "").split())[:MAX_TITLE]
        if title and title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
    return titles[:MAX_DISHES]


def list_dishes(project_id):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(dishes).where(dishes.c.project_id == project_id).order_by(dishes.c.position, dishes.c.id)
        ).mappings().all()
    return [dict(r) for r in rows]


def get_dish(project_id, dish_id):
    with get_engine().connect() as conn:
        row = conn.execute(
            select(dishes).where(dishes.c.id == dish_id, dishes.c.project_id == project_id)
        ).mappings().first()
    return dict(row) if row else None


def save_wishlist(project_id, titles, source="buyer"):
    """Replace the not-yet-recorded dishes with `titles`, in order. Dishes with a recording are kept."""
    titles = clean_titles(titles)
    with get_engine().begin() as conn:
        conn.execute(delete(dishes).where(dishes.c.project_id == project_id, dishes.c.recipe_id.is_(None)))
        start = conn.execute(
            select(func.coalesce(func.max(dishes.c.position), 0)).where(dishes.c.project_id == project_id)
        ).scalar_one()
        recorded = {t.lower() for t in conn.execute(
            select(dishes.c.title).where(dishes.c.project_id == project_id)).scalars()}
        position = start
        for title in titles:
            if title.lower() in recorded:
                continue
            position += 1
            conn.execute(insert(dishes).values(project_id=project_id, title=title, position=position,
                                               source=source, status="wishlist"))
    return titles


def add_dish(project_id, title, source="buyer", requested_by_label=None):
    titles = clean_titles([title])
    if not titles:
        return None
    with get_engine().begin() as conn:
        position = conn.execute(
            select(func.coalesce(func.max(dishes.c.position), 0) + 1).where(dishes.c.project_id == project_id)
        ).scalar_one()
        return conn.execute(
            insert(dishes).values(project_id=project_id, title=titles[0], position=position, source=source,
                                  requested_by_label=requested_by_label, status="wishlist")
            .returning(dishes.c.id)
        ).scalar_one()


def next_dish(project_id):
    """The first dish still waiting for a recording."""
    return next((d for d in list_dishes(project_id) if d["status"] == "wishlist"), None)


def skip_dish(project_id, dish_id):
    with get_engine().begin() as conn:
        conn.execute(update(dishes).where(dishes.c.id == dish_id, dishes.c.project_id == project_id,
                                          dishes.c.recipe_id.is_(None)).values(status="skipped"))

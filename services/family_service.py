"""Family members and their dish requests (BUILD_PLAN module 12, UX R11 and F4).

Family members join from the book link with just a name; nobody logs in. Requests wait for
the buyer's OK before they reach the cook, so jokes and duplicates never do.
"""
from sqlalchemy import func, insert, select, update

from models.database import get_engine
from models.schema import dishes, family_members
from services import dish_service

MAX_NAME = 40


def clean_name(raw):
    return " ".join((raw or "").split())[:MAX_NAME]


def join(project_id, name, member_id=None):
    """Add a family member, or rename the one this device joined as before. Returns (member id, is_new)."""
    name = clean_name(name)
    if not name:
        raise ValueError("Name is required.")
    with get_engine().begin() as conn:
        if member_id:
            existing = conn.execute(
                select(family_members.c.id).where(family_members.c.id == member_id,
                                                  family_members.c.project_id == project_id,
                                                  family_members.c.removed_at.is_(None))
            ).scalar()
            if existing:
                conn.execute(update(family_members).where(family_members.c.id == existing).values(name=name))
                return existing, False
        new_id = conn.execute(
            insert(family_members).values(project_id=project_id, name=name, role="member", joined_at=func.now())
            .returning(family_members.c.id)
        ).scalar_one()
    return new_id, True


def get_member(project_id, member_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(family_members).where(family_members.c.id == member_id,
                                                        family_members.c.project_id == project_id)).mappings().first()
    return dict(row) if row else None


def request_dish(project_id, member, title):
    """A family member asks for a dish. An existing dish gets their name added ("+1"); else it waits for the OK."""
    titles = dish_service.clean_titles([title])
    if not titles:
        raise ValueError("Dish is required.")
    title = titles[0]
    existing = next((d for d in dish_service.list_dishes(project_id)
                     if d["title"].lower() == title.lower() and d["status"] != "skipped"), None)
    with get_engine().begin() as conn:
        if existing:
            names = [n for n in (existing["requested_by_label"] or "").split(", ") if n]
            if member["name"] not in names:
                names.append(member["name"])
            conn.execute(update(dishes).where(dishes.c.id == existing["id"])
                         .values(requested_by_label=", ".join(names)[:200]))
            return existing["id"], False
        position = conn.execute(
            select(func.coalesce(func.max(dishes.c.position), 0) + 1).where(dishes.c.project_id == project_id)
        ).scalar_one()
        dish_id = conn.execute(
            insert(dishes).values(project_id=project_id, title=title, position=position, source="family",
                                  requested_by_member_id=member["id"], requested_by_label=member["name"],
                                  status="requested")
            .returning(dishes.c.id)
        ).scalar_one()
    return dish_id, True


def pending_requests(project_id):
    return [d for d in dish_service.list_dishes(project_id) if d["status"] == "requested"]


def decide(project_id, dish_id, approve):
    with get_engine().begin() as conn:
        return conn.execute(
            update(dishes).where(dishes.c.id == dish_id, dishes.c.project_id == project_id,
                                 dishes.c.status == "requested")
            .values(status="wishlist" if approve else "skipped")
        ).rowcount == 1


def remove_member(project_id, member_id):
    with get_engine().begin() as conn:
        conn.execute(update(family_members)
                     .where(family_members.c.id == member_id, family_members.c.project_id == project_id,
                            family_members.c.role == "member")
                     .values(removed_at=func.now()))

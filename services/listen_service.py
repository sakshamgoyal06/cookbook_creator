"""Public listen links: /l/<token> plays a recipe's voice notes, /b/<token> the whole book (PRD §8.5).

URLs carry only random tokens, never database ids (QR-3). The path format is
permanent (QR-4): never change `/l/<token>` or `/b/<token>` without redirects.
"""
from datetime import datetime, timedelta, timezone

from flask import request
from sqlalchemy import func, insert, select, update

import config
from models.database import get_engine, new_token
from models.schema import LISTEN_SOURCES, listen_events, projects, recipe_audio, recipes
from services import events_service

# Recipes that have a finished draft; the book page skips ones still processing or failed.
LISTENABLE_STATUSES = ("structured", "awaiting_mom", "needs_review", "approved")


def base_url():
    return config.PUBLIC_BASE_URL or request.url_root.rstrip("/")


def listen_url(token, source=None):
    """Public listen URL. QR codes pass source="qr" so scans can be told apart from shared links."""
    url = f"{base_url()}/l/{token}"
    return f"{url}?s={source}" if source else url


def book_url(token):
    return f"{base_url()}/b/{token}"


def get_listen_recipe(token):
    """The recipe behind a live listen token, with its clips, or None if unknown or revoked."""
    with get_engine().connect() as conn:
        row = conn.execute(
            select(
                recipes.c.id,
                recipes.c.project_id,
                recipes.c.recipe_title,
                recipes.c.created_at,
                recipes.c.listen_revoked_at,
                recipes.c.status,
                recipes.c.cook_name,
                projects.c.title.label("project_title"),
                projects.c.storyteller_name,
                projects.c.cook_mode,
            )
            .join(projects, projects.c.id == recipes.c.project_id)
            .where(recipes.c.listen_token == token)
        ).mappings().first()
        if row is None or row["listen_revoked_at"] is not None:
            return None
        recipe = dict(row)
        recipe["clips"] = _clips(conn, recipe["id"])
    return recipe


def get_clip_storage_key(token, clip_number):
    """Storage key of the n-th clip (1-based, in play order) of a live listen token."""
    recipe = get_listen_recipe(token)
    if recipe is None or not 1 <= clip_number <= len(recipe["clips"]):
        return None
    return recipe["clips"][clip_number - 1]["storage_key"]


def record_play(token, source="link", is_owner=False):
    """Count a play without any personal data (QR-9). Returns the recipe id, or None for dead tokens."""
    if source not in LISTEN_SOURCES:
        source = "link"
    with get_engine().begin() as conn:
        row = conn.execute(
            select(recipes.c.id, recipes.c.project_id)
            .where(recipes.c.listen_token == token, recipes.c.listen_revoked_at.is_(None))
        ).first()
        if row is None:
            return None
        conn.execute(insert(listen_events).values(recipe_id=row.id, source=source, is_owner=is_owner))
        events_service.track("qr_play", project_id=row.project_id, recipe_id=row.id,
                             actor="buyer" if is_owner else "anon", channel="qr" if source == "qr" else "web",
                             conn=conn, source=source)
    return row.id


def play_count(recipe_id, days=None):
    """Plays by anyone other than the owner; `days` limits it to the last N days."""
    query = select(func.count()).select_from(listen_events).where(
        listen_events.c.recipe_id == recipe_id, listen_events.c.is_owner.is_(False)
    )
    if days:
        query = query.where(listen_events.c.played_at >= _days_ago(days))
    with get_engine().connect() as conn:
        return conn.execute(query).scalar_one()


def project_play_count(project_id, days=None):
    query = (
        select(func.count())
        .select_from(listen_events.join(recipes, recipes.c.id == listen_events.c.recipe_id))
        .where(recipes.c.project_id == project_id, listen_events.c.is_owner.is_(False))
    )
    if days:
        query = query.where(listen_events.c.played_at >= _days_ago(days))
    with get_engine().connect() as conn:
        return conn.execute(query).scalar_one()


def _days_ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def revoke(recipe_id):
    """Stop the current link working; the page then says the recording is private (QR-7)."""
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes)
            .where(recipes.c.id == recipe_id)
            .values(listen_revoked_at=func.now(), updated_at=func.now())
        )


def regenerate(recipe_id):
    """Issue a new live token. The old QR stops working and shows the private page."""
    with get_engine().begin() as conn:
        conn.execute(
            update(recipes)
            .where(recipes.c.id == recipe_id)
            .values(listen_token=new_token(), listen_revoked_at=None, updated_at=func.now())
        )


def regenerate_book(project_id):
    """New family link: the old book link and book QR stop working (recipe QR codes are unaffected)."""
    with get_engine().begin() as conn:
        conn.execute(update(projects).where(projects.c.id == project_id)
                     .values(book_token=new_token(), updated_at=func.now()))


def get_book(token):
    """A project's public cookbook page data: its title and listenable recipes with clips."""
    with get_engine().connect() as conn:
        project = conn.execute(
            select(projects.c.id, projects.c.title, projects.c.subtitle, projects.c.dedication,
                   projects.c.storyteller_name, projects.c.storyteller_address_as, projects.c.storyteller_language,
                   projects.c.share_pages_as_ready, projects.c.revealed_at, projects.c.reveal_date)
            .where(projects.c.book_token == token)
        ).mappings().first()
        if project is None:
            return None
        book = dict(project)
        rows = conn.execute(
            select(recipes.c.id, recipes.c.recipe_title, recipes.c.listen_token)
            .where(
                recipes.c.project_id == project["id"],
                recipes.c.status == "approved",  # the family sees pages once the buyer approves them
                recipes.c.listen_revoked_at.is_(None),
            )
            .order_by(recipes.c.sort_order, recipes.c.created_at, recipes.c.id)
        ).mappings().all()
        book["recipes"] = [dict(r, clip_count=len(_clips(conn, r["id"]))) for r in rows]
        # "Keep it a surprise": the book lists nothing until the reveal; printed QR codes still play.
        book["surprise"] = not book["share_pages_as_ready"] and book["revealed_at"] is None
        if book["surprise"]:
            book["recipes"] = []
    return book


def voice_name(recipe):
    """Whose voice the listen page names: "Sunita ji", or the owner's own name in self mode."""
    name = recipe.get("cook_name") or recipe.get("storyteller_name")
    if not name:
        return None
    return name if recipe.get("cook_mode") == "self" else f"{name.split()[0]} ji"


def clip_label(clips, index):
    kind = clips[index]["kind"]
    if kind == "story":
        return "The story behind it"
    if kind == "followup":
        return "A follow-up answer"
    originals = [c for c in clips if c["kind"] == "original"]
    if len(originals) == 1:
        return "The recipe"
    return f"The recipe, part {originals.index(clips[index]) + 1}"


def _clips(conn, recipe_id):
    return [
        dict(r)
        for r in conn.execute(
            select(recipe_audio.c.storage_key, recipe_audio.c.kind, recipe_audio.c.created_at)
            .where(recipe_audio.c.recipe_id == recipe_id)
            .order_by(recipe_audio.c.play_order, recipe_audio.c.id)
        ).mappings()
    ]

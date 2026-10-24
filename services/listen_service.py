"""Public listen links: /l/<token> plays a recipe's voice notes, /b/<token> the whole book (PRD §8.5).

URLs carry only random tokens, never database ids (QR-3). The path format is
permanent (QR-4): never change `/l/<token>` or `/b/<token>` without redirects.
"""
from flask import request
from sqlalchemy import func, insert, select, update

import config
from models.database import get_engine, new_token
from models.schema import listen_events, projects, recipe_audio, recipes

# Recipes that have a finished draft; the book page skips ones still processing or failed.
LISTENABLE_STATUSES = ("structured", "awaiting_mom", "needs_review", "approved")


def base_url():
    return config.PUBLIC_BASE_URL or request.url_root.rstrip("/")


def listen_url(token):
    return f"{base_url()}/l/{token}"


def book_url(token):
    return f"{base_url()}/b/{token}"


def get_listen_recipe(token):
    """The recipe behind a live listen token, with its clips, or None if unknown or revoked."""
    with get_engine().connect() as conn:
        row = conn.execute(
            select(
                recipes.c.id,
                recipes.c.recipe_title,
                recipes.c.created_at,
                recipes.c.listen_revoked_at,
                projects.c.title.label("project_title"),
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


def record_play(token):
    """Count a play without any personal data (QR-9). Returns False for dead tokens."""
    with get_engine().begin() as conn:
        recipe_id = conn.execute(
            select(recipes.c.id).where(recipes.c.listen_token == token, recipes.c.listen_revoked_at.is_(None))
        ).scalar()
        if recipe_id is None:
            return False
        conn.execute(insert(listen_events).values(recipe_id=recipe_id))
    return True


def play_count(recipe_id):
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count()).select_from(listen_events).where(listen_events.c.recipe_id == recipe_id)
        ).scalar_one()


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


def get_book(token):
    """A project's public cookbook page data: its title and listenable recipes with clips."""
    with get_engine().connect() as conn:
        project = conn.execute(
            select(projects.c.id, projects.c.title, projects.c.subtitle, projects.c.dedication)
            .where(projects.c.book_token == token)
        ).mappings().first()
        if project is None:
            return None
        book = dict(project)
        rows = conn.execute(
            select(recipes.c.id, recipes.c.recipe_title, recipes.c.listen_token)
            .where(
                recipes.c.project_id == project["id"],
                recipes.c.status.in_(LISTENABLE_STATUSES),
                recipes.c.listen_revoked_at.is_(None),
            )
            .order_by(recipes.c.sort_order, recipes.c.created_at, recipes.c.id)
        ).mappings().all()
        book["recipes"] = [dict(r, clip_count=len(_clips(conn, r["id"]))) for r in rows]
    return book


def _clips(conn, recipe_id):
    return [
        dict(r)
        for r in conn.execute(
            select(recipe_audio.c.storage_key, recipe_audio.c.kind, recipe_audio.c.created_at)
            .where(recipe_audio.c.recipe_id == recipe_id)
            .order_by(recipe_audio.c.play_order, recipe_audio.c.id)
        ).mappings()
    ]

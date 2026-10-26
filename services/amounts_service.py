"""The amounts step before approval: every vague or missing quantity, asked once, on one screen.

The cook's "thoda sa" and "andaaze se" are kept when the buyer says so; otherwise the
buyer types the amount (after asking the cook on WhatsApp, in one message for all of them).
"""
import json
import re

from sqlalchemy import func, update

from models.database import get_engine
from models.schema import recipes

VAGUE = re.compile(r"\b(thod[aie]|andaa?z[ae]?|swaa?d|jitn[aie]|zaroorat|as needed|as required|to taste|"
                   r"some|little|a bit|bit|kuch)\b", re.IGNORECASE)
KEEP_WORDS = "andaaze se"
MAX_FIELD = 40


def unclear_amounts(recipe):
    """(index, ingredient) for each ingredient whose amount is missing or vague."""
    return [(i, ing) for i, ing in enumerate(recipe.get("ingredients") or [])
            if not (ing.get("quantity") or "").strip() or VAGUE.search(ing.get("quantity") or "")]


def needs_step(recipe):
    return recipe["status"] == "needs_review" and not recipe.get("amounts_checked_at") and bool(unclear_amounts(recipe))


def apply(recipe, answers):
    """answers: {index: (quantity, unit)}; an index left out keeps the cook's words. Returns how many changed."""
    ingredients = list(recipe.get("ingredients") or [])
    changed = 0
    for index, ing in unclear_amounts(recipe):
        quantity, unit = answers.get(index, ("", ""))
        quantity, unit = _clean(quantity), _clean(unit)
        if quantity:
            ingredients[index] = {**ing, "quantity": quantity, "unit": unit or ing.get("unit") or ""}
            changed += 1
        elif not (ing.get("quantity") or "").strip():
            ingredients[index] = {**ing, "quantity": KEEP_WORDS}
    # The "please check" notes about these amounts are dealt with now.
    covered = [ing["item"].split()[0].lower() for _, ing in unclear_amounts(recipe) if ing.get("item")]
    flags = [f for f in recipe.get("unclear_items_for_review") or []
             if not any(word in f.lower() for word in covered)]
    with get_engine().begin() as conn:
        conn.execute(update(recipes).where(recipes.c.id == recipe["id"])
                     .values(ingredients_json=json.dumps(ingredients, ensure_ascii=False),
                             unclear_items_for_review_json=json.dumps(flags, ensure_ascii=False),
                             amounts_checked_at=func.now(), updated_at=func.now()))
    return changed


def _clean(value):
    return " ".join((value or "").split())[:MAX_FIELD]

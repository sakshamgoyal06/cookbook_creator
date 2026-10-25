"""Small helpers shared by templates: status chips, names and dates (UX spec §3)."""
from datetime import date

DEFAULT_ADDRESS = "Mummy"


def status_chip(status, address_as=None):
    who = address_as or DEFAULT_ADDRESS
    return {
        "received": {"label": "Writing it down", "style": "writing"},
        "transcribed": {"label": "Writing it down", "style": "writing"},
        "structured": {"label": "Writing it down", "style": "writing"},
        "awaiting_mom": {"label": f"Waiting on {who}", "style": "waiting"},
        "needs_review": {"label": "Ready to review", "style": "review"},
        "approved": {"label": "Approved", "style": "approved"},
        "failed": {"label": "We couldn't hear this one", "style": "failed"},
    }.get(status, {"label": status.replace("_", " ").capitalize(), "style": "writing"})


def days_until(day, today=None):
    if not day:
        return None
    if isinstance(day, str):
        day = date.fromisoformat(day)
    return (day - (today or date.today())).days


def cook_display_name(project):
    """How our own messages address the cook: "Sunita ji", else what the buyer calls her, else Mummy."""
    if project.get("storyteller_name"):
        return f"{project['storyteller_name'].split()[0]} ji"
    return project.get("storyteller_address_as") or DEFAULT_ADDRESS


def cook_label(project):
    """How the buyer's screens name the cook: what the buyer calls her ("Mummy"), else "Sunita ji"."""
    return project.get("storyteller_address_as") or cook_display_name(project)


def normalize_phone(raw, default_country="91"):
    """E.164 for a phone number typed any common way; None if it can't be one.

    Indian numbers may come as 98xxxxxxxx, 098xxxxxxxx, 91 98xxx xxxxx or +91-98xxx-xxxxx.
    """
    if not raw:
        return None
    plus = raw.strip().startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if plus or raw.strip().startswith("00"):
        digits = digits[2:] if raw.strip().startswith("00") else digits
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    digits = digits.lstrip("0")
    if len(digits) == 10 and default_country == "91":
        return f"+91{digits}" if digits[0] in "6789" else None
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return f"+{digits}"
    return None

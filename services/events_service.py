"""Analytics events (BUILD_PLAN module 3, PRD OPS-3 and §10).

Events never carry personal data: no names, phone numbers, transcripts or
storage keys. Each event name has an allowlist of props; anything else is
dropped (and fails loudly in tests). Tracking never breaks the request.
"""
import logging
import re

from sqlalchemy import insert

import config
from models.database import get_engine
from models.schema import ACTORS, events

log = logging.getLogger(__name__)

# Event name -> allowed props.
CATALOGUE = {
    # Onboarding (module 5)
    "onboarding_started": set(),
    "cook_mode_chosen": {"mode"},
    "tier_chosen": {"tier"},
    "cook_details_saved": {"language"},
    "reveal_date_set": {"days_away"},
    "dish_list_saved": {"count"},
    "checkout_started": {"tier"},
    "payment_succeeded": {"amount_paise", "tier"},
    "payment_failed": {"reason"},
    "invite_shared": {"language"},
    # Capture (modules 7, 9)
    "consent_given": set(),
    "voice_note_received": {"seconds", "kind"},
    "recording_started": {"kind"},
    "recording_finished": {"seconds", "kind"},
    "recording_abandoned": {"seconds"},
    "upload_failed": {"stage"},
    "recipe_created": {"source"},
    "pipeline_failed": {"stage"},
    # Review (module 6)
    "recipe_ready_for_review": set(),
    "recipe_edited": {"fields_changed"},
    "recipe_approved": {"edits"},
    "recipe_retry_requested": {"stage"},
    # Questions (module 10)
    "question_sent": set(),
    "question_answered": {"via"},
    "question_skipped": set(),
    "question_expired": set(),
    # Engagement (module 11)
    "reminder_sent": {"day", "to"},
    "reminders_paused": {"days"},
    "escalation_shown": {"days_quiet"},
    "escalation_action": {"action"},
    "milestone_reached": {"n"},
    # Family (module 12)
    "family_link_shared": set(),
    "family_member_joined": set(),
    "dish_requested": set(),
    # QR and listen (module 8)
    "listen_page_viewed": {"source"},
    "qr_play": {"source"},
    "listen_link_revoked": set(),
    "listen_link_regenerated": set(),
    "qr_downloaded": {"format", "target"},
    # Book (module 14)
    "book_compiled": {"recipes"},
    "book_revealed": {"recipes"},
    "book_pdf_downloaded": set(),
    "book_page_viewed": set(),
    # Upsell (module 16)
    "volume2_offer_shown": set(),
    "volume2_bought": {"amount_paise"},
}
CHANNELS = ("web", "pwa", "whatsapp", "qr", "system")

# Link-preview fetchers and crawlers: they open shared links but are not people.
_BOT_RE = re.compile(
    r"bot|crawl|spider|preview|facebookexternalhit|whatsapp|telegram|slack|discord|skype|"
    r"embedly|quora link|vkshare|pinterest|curl|wget|python-requests|httpx|headless",
    re.IGNORECASE,
)


class EventError(ValueError):
    pass


def is_bot(user_agent):
    return not user_agent or bool(_BOT_RE.search(user_agent))


def track(name, project_id=None, recipe_id=None, actor="system", channel="web", conn=None, **props):
    """Record one event. Pass `conn` to write inside the caller's transaction."""
    try:
        row = _validate(name, project_id, recipe_id, actor, channel, props)
        if conn is not None:
            conn.execute(insert(events).values(**row))
        else:
            with get_engine().begin() as own:
                own.execute(insert(events).values(**row))
    except EventError:
        if config.EVENTS_STRICT:
            raise
        log.exception("Rejected analytics event %s", name)
    except Exception:
        if config.EVENTS_STRICT:
            raise
        log.exception("Could not record analytics event %s", name)


def _validate(name, project_id, recipe_id, actor, channel, props):
    if name not in CATALOGUE:
        raise EventError(f"Unknown event: {name}")
    if actor not in ACTORS:
        raise EventError(f"Unknown actor: {actor}")
    if channel not in CHANNELS:
        raise EventError(f"Unknown channel: {channel}")
    extra = set(props) - CATALOGUE[name]
    if extra:
        raise EventError(f"Props not allowed on {name}: {sorted(extra)}")
    for key, value in props.items():
        if not isinstance(value, (int, float, bool, type(None))) and not (isinstance(value, str) and len(value) <= 40):
            raise EventError(f"Prop {key} on {name} must be a number, bool or short code")
    return {"name": name, "project_id": project_id, "recipe_id": recipe_id, "actor": actor,
            "channel": channel, "props": props}

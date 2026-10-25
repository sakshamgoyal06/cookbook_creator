import pytest
from sqlalchemy import select

import config
from models.database import get_engine
from models.schema import events
from services import events_service


def _rows():
    with get_engine().connect() as conn:
        return conn.execute(select(events.c.name, events.c.actor, events.c.props)).all()


def test_track_records_allowed_props(app):
    events_service.track("cook_mode_chosen", actor="buyer", mode="self")
    assert [tuple(r) for r in _rows()] == [("cook_mode_chosen", "buyer", {"mode": "self"})]


@pytest.mark.parametrize("kwargs", [
    {"name": "no_such_event"},
    {"name": "cook_mode_chosen", "phone": "+919999999999"},
    {"name": "cook_mode_chosen", "mode": "x" * 200},
    {"name": "cook_mode_chosen", "actor": "mom"},
    {"name": "cook_mode_chosen", "mode": {"nested": 1}},
])
def test_invalid_events_raise_in_strict_mode(app, kwargs):
    with pytest.raises(events_service.EventError):
        events_service.track(**kwargs)
    assert _rows() == []


def test_invalid_events_never_break_requests_in_production(app, monkeypatch):
    monkeypatch.setattr(config, "EVENTS_STRICT", False)
    events_service.track("no_such_event")
    events_service.track("cook_mode_chosen", transcript="secret words")
    assert _rows() == []


@pytest.mark.parametrize("agent,bot", [
    ("Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile", False),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1", False),
    ("WhatsApp/2.23.20 A", True),
    ("facebookexternalhit/1.1", True),
    ("TelegramBot (like TwitterBot)", True),
    ("Googlebot/2.1", True),
    ("", True),
    (None, True),
])
def test_bot_detection(agent, bot):
    assert events_service.is_bot(agent) is bot

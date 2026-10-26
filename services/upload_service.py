"""Chunked, resumable uploads for in-app recordings (BUILD_PLAN module 7, UX spec §5).

The phone records with MediaRecorder and sends a chunk every few seconds. Chunks are
idempotent (re-sending chunk n replaces it), so a flaky network only means retries.
"complete" joins the chunks in order into one audio file and hands it to the pipeline.
"""
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, update

import config
from models.database import get_engine
from models.schema import upload_sessions
from services import storage_service
from services.audio_utils import build_storage_filename

CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_CHUNK_BYTES = 4 * 1024 * 1024
MAX_CHUNKS = 720  # an hour at 5-second chunks
MAX_TOTAL_BYTES = 60 * 1024 * 1024
KINDS = ("original", "story", "replace")
STALE_HOURS = 24


class UploadError(ValueError):
    pass


def _chunk_dir(client_id):
    return os.path.join(config.INSTANCE_FOLDER, "upload_chunks", client_id)


def open_session(project_id, client_id, kind="original", content_type=None, dish_id=None, recipe_id=None):
    """Start (or find again) the upload for one recording. Returns the session row."""
    if not CLIENT_ID_RE.match(client_id or ""):
        raise UploadError("Bad upload id.")
    if kind not in KINDS:
        raise UploadError("Bad kind.")
    session = get_session(client_id)
    if session:
        if session["project_id"] != project_id:
            raise UploadError("Bad upload id.")
        return session
    cleanup_stale()
    with get_engine().begin() as conn:
        conn.execute(insert(upload_sessions).values(
            project_id=project_id, client_upload_id=client_id, kind=kind, dish_id=dish_id, recipe_id=recipe_id,
            content_type=(content_type or "audio/webm")[:100],
        ))
    os.makedirs(_chunk_dir(client_id), exist_ok=True)
    return get_session(client_id)


def get_session(client_id):
    with get_engine().connect() as conn:
        row = conn.execute(
            select(upload_sessions).where(upload_sessions.c.client_upload_id == client_id)
        ).mappings().first()
    return dict(row) if row else None


def save_chunk(session, number, data):
    if session["status"] == "complete":
        return session  # a late retry of a chunk is harmless
    if not 0 <= number < MAX_CHUNKS:
        raise UploadError("Too many chunks.")
    if not data or len(data) > MAX_CHUNK_BYTES:
        raise UploadError("Chunk is empty or too big.")
    folder = _chunk_dir(session["client_upload_id"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{number:05d}")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)  # a half-written chunk never counts
    chunks = _chunk_files(folder)
    total = sum(os.path.getsize(os.path.join(folder, c)) for c in chunks)
    if total > MAX_TOTAL_BYTES:
        raise UploadError("Recording is too long.")
    with get_engine().begin() as conn:
        # An abandoned session reopens when the phone comes back; a completed one never does.
        conn.execute(update(upload_sessions)
                     .where(upload_sessions.c.id == session["id"], upload_sessions.c.status != "complete")
                     .values(chunks_received=len(chunks), bytes_received=total, status="open"))
    return get_session(session["client_upload_id"])


def missing_chunks(session, expected):
    present = {int(c) for c in _chunk_files(_chunk_dir(session["client_upload_id"]))}
    return [n for n in range(expected) if n not in present]


def assemble(session, expected):
    """Join chunks 0..expected-1 into one stored audio file; returns its storage key."""
    if not 1 <= expected <= MAX_CHUNKS:
        raise UploadError("Bad chunk count.")
    missing = missing_chunks(session, expected)
    if missing:
        raise UploadError(f"Missing chunks: {missing[:10]}")
    folder = _chunk_dir(session["client_upload_id"])
    filename = build_storage_filename("recording", session["content_type"])
    handle, temp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
    try:
        with os.fdopen(handle, "wb") as out:
            for n in range(expected):
                with open(os.path.join(folder, f"{n:05d}"), "rb") as chunk:
                    shutil.copyfileobj(chunk, out)
        storage_service.save_file("audio", filename, temp_path, content_type=session["content_type"])
    finally:
        os.remove(temp_path)
    return filename


def claim(session):
    """Atomically move an open session to complete, so two "complete" calls can't make two recipes."""
    with get_engine().begin() as conn:
        return conn.execute(update(upload_sessions)
                            .where(upload_sessions.c.id == session["id"], upload_sessions.c.status == "open")
                            .values(status="complete")).rowcount == 1


def release(session):
    with get_engine().begin() as conn:
        conn.execute(update(upload_sessions).where(upload_sessions.c.id == session["id"]).values(status="open"))


def mark_complete(session, recipe_id):
    with get_engine().begin() as conn:
        conn.execute(update(upload_sessions).where(upload_sessions.c.id == session["id"])
                     .values(status="complete", recipe_id=recipe_id))
    shutil.rmtree(_chunk_dir(session["client_upload_id"]), ignore_errors=True)


def _chunk_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.isdigit())


def cleanup_stale(max_age_hours=STALE_HOURS):
    """Mark recordings nobody finished as abandoned and free their chunks. Returns how many.

    A session counts as stale once nothing has arrived for `max_age_hours`. The phone keeps its own
    copy, so if it comes back later, its chunks reopen the session (see save_chunk).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    with get_engine().connect() as conn:
        rows = conn.execute(select(upload_sessions.c.id, upload_sessions.c.client_upload_id,
                                   upload_sessions.c.created_at)
                            .where(upload_sessions.c.status == "open")).mappings().all()
    stale = [r for r in rows if _aware(r["created_at"]) < cutoff
             and _last_write(r["client_upload_id"]) < cutoff.timestamp()]
    for row in stale:
        with get_engine().begin() as conn:
            conn.execute(update(upload_sessions)
                         .where(upload_sessions.c.id == row["id"], upload_sessions.c.status == "open")
                         .values(status="abandoned"))
        shutil.rmtree(_chunk_dir(row["client_upload_id"]), ignore_errors=True)
    return len(stale)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _last_write(client_id):
    folder = _chunk_dir(client_id)
    try:
        times = [os.path.getmtime(os.path.join(folder, c)) for c in _chunk_files(folder)]
        return max(times + [os.path.getmtime(folder)])
    except OSError:
        return 0 if not os.path.isdir(folder) else time.time()

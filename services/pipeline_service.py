"""Voice note -> transcript -> structured recipe, run as a background job.

With REDIS_URL set, uploads enqueue `process_recipe` on an RQ queue and `worker.py`
runs it, retrying with backoff. Without it, the job runs inline in the request.
Each stage is recorded in `pipeline_runs`; raw errors stay there for ops and are
never shown to users, who only see the recipe's `failed` status.
"""
import logging

from sqlalchemy import func, insert, select, update

import config
from models.database import get_engine
from models.schema import pipeline_runs, projects, recipe_audio, recipes
from services import ai_service, events_service, question_service, recipe_service, storage_service

log = logging.getLogger(__name__)

# Seconds to wait before each retry of a failed job.
RETRY_INTERVALS = [30, 120, 600]


MISSING_AUDIO = "The voice note file is missing."


class PermanentError(Exception):
    """A failure that retrying will not fix, such as an empty transcript."""


def get_queue():
    from redis import Redis
    from rq import Queue

    return Queue(config.PIPELINE_QUEUE, connection=Redis.from_url(config.REDIS_URL))


def enqueue_processing(recipe_id):
    """Start processing a received recipe: on the worker if configured, otherwise right now."""
    if not config.REDIS_URL:
        try:
            process_recipe(recipe_id)
        except Exception:
            pass  # Already logged and recorded in pipeline_runs; the recipe is marked failed.
        return
    from rq import Retry

    get_queue().enqueue(
        process_recipe,
        recipe_id,
        retry=Retry(max=len(RETRY_INTERVALS), interval=RETRY_INTERVALS),
        job_timeout=config.PIPELINE_JOB_TIMEOUT_SECONDS,
    )


def process_recipe(recipe_id):
    """Run the stages a recipe still needs. Safe to re-run: finished stages are skipped."""
    with get_engine().connect() as conn:
        recipe = conn.execute(
            select(recipes.c.status, recipes.c.raw_transcript, recipes.c.project_id).where(recipes.c.id == recipe_id)
        ).mappings().first()
        audio_keys = conn.execute(
            select(recipe_audio.c.storage_key)
            .where(recipe_audio.c.recipe_id == recipe_id, recipe_audio.c.kind == "original")
            .order_by(recipe_audio.c.play_order, recipe_audio.c.id)
        ).scalars().all()
    if recipe is None or recipe["status"] not in ("received", "transcribed", "failed"):
        return

    try:
        transcript = recipe["raw_transcript"]
        if not transcript:
            transcript = _run_stage(recipe_id, "transcribe", "openai", config.OPENAI_TRANSCRIBE_MODEL,
                                    lambda: _transcribe(audio_keys))
            recipe_service.save_transcript(recipe_id, transcript)
        text = transcript + question_service.answers_block(recipe_id)
        language = _project_language(recipe["project_id"])
        recipe_data = _run_stage(recipe_id, "structure", "anthropic", config.ANTHROPIC_RECIPE_MODEL,
                                 lambda: ai_service.structure_recipe(text, language=language))
        recipe_service.save_structured_recipe(recipe_id, recipe_data)
        for _ in range(question_service.save_questions(recipe_id, recipe_data.get("follow_up_questions"))):
            events_service.track("question_sent", project_id=recipe["project_id"], recipe_id=recipe_id,
                                 channel="web")
        events_service.track("recipe_ready_for_review", project_id=recipe["project_id"], recipe_id=recipe_id)
    except PermanentError as e:
        _mark_failed(recipe, recipe_id, getattr(e, "stage", "transcribe"))
    except Exception as e:
        if _is_last_attempt():
            _mark_failed(recipe, recipe_id, getattr(e, "stage", "structure"))
        raise


def _project_language(project_id):
    with get_engine().connect() as conn:
        return conn.execute(select(projects.c.storyteller_language).where(projects.c.id == project_id)).scalar()


def _mark_failed(recipe, recipe_id, stage):
    recipe_service.set_status(recipe_id, "failed")
    events_service.track("pipeline_failed", project_id=recipe["project_id"], recipe_id=recipe_id, stage=stage)


def _transcribe(audio_keys):
    """One transcript for all of a dish's voice notes, in play order."""
    if not audio_keys:
        raise PermanentError("Recipe has no audio.")
    parts = []
    for key in audio_keys:
        try:
            with storage_service.local_copy("audio", key) as path:
                parts.append((ai_service.transcribe_audio(path) or "").strip())
        except FileNotFoundError as e:  # e.g. local storage wiped by a redeploy: retrying can't bring it back
            raise PermanentError(MISSING_AUDIO) from e
    transcript = "\n\n".join(p for p in parts if p)
    if not transcript:
        raise PermanentError("Transcription returned empty text.")
    return transcript


def failure_reason(recipe_id):
    """Why a recipe last failed, in words the buyer can act on: "missing_audio" or "unclear"."""
    with get_engine().connect() as conn:
        error = conn.execute(select(pipeline_runs.c.error)
                             .where(pipeline_runs.c.recipe_id == recipe_id, pipeline_runs.c.status == "failed")
                             .order_by(pipeline_runs.c.id.desc()).limit(1)).scalar()
    return "missing_audio" if error and MISSING_AUDIO in error else "unclear"


def _run_stage(recipe_id, stage, provider, model, work):
    with get_engine().begin() as conn:
        run_id = conn.execute(
            insert(pipeline_runs)
            .values(recipe_id=recipe_id, stage=stage, status="running", attempts=_attempt_number(),
                    provider=provider, model=model, started_at=func.now())
            .returning(pipeline_runs.c.id)
        ).scalar_one()
    try:
        result = work()
    except Exception as e:
        log.exception("Pipeline stage %s failed for recipe %s", stage, recipe_id)
        _finish_run(run_id, "failed", f"{type(e).__name__}: {e}"[:2000])
        e.stage = stage
        raise
    _finish_run(run_id, "succeeded")
    return result


def _finish_run(run_id, status, error=None):
    with get_engine().begin() as conn:
        conn.execute(
            update(pipeline_runs)
            .where(pipeline_runs.c.id == run_id)
            .values(status=status, error=error, finished_at=func.now())
        )


def _current_job():
    try:
        from rq import get_current_job
    except ImportError:
        return None
    return get_current_job()


def _attempt_number():
    job = _current_job()
    if job is None or job.retries_left is None:
        return 1
    return len(RETRY_INTERVALS) - job.retries_left + 1


def _is_last_attempt():
    job = _current_job()
    return job is None or not job.retries_left

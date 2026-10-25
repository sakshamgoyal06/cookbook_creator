import io

import fakeredis
import pytest
from conftest import SAMPLE_RECIPE, create_project
from rq import SimpleWorker
from sqlalchemy import select

import config
from models.database import get_engine
from models.schema import pipeline_runs
from services import ai_service, pipeline_service, project_service, recipe_service


@pytest.fixture
def queue(monkeypatch):
    """A real RQ queue on an in-memory Redis; jobs run when `run_jobs` is called."""
    from rq import Queue

    connection = fakeredis.FakeStrictRedis()
    q = Queue(config.PIPELINE_QUEUE, connection=connection)
    monkeypatch.setattr(config, "REDIS_URL", "redis://fake")
    monkeypatch.setattr(pipeline_service, "get_queue", lambda: q)
    return q


def run_jobs(q):
    SimpleWorker([q], connection=q.connection).work(burst=True)


def _upload(client, project_id):
    return client.post(
        f"/projects/{project_id}/upload",
        data={"audio_file": (io.BytesIO(b"fake audio"), "note.m4a", "audio/m4a")},
        content_type="multipart/form-data",
    )


def _runs():
    with get_engine().connect() as conn:
        rows = conn.execute(select(pipeline_runs).order_by(pipeline_runs.c.id)).mappings().all()
    return [(r["stage"], r["status"], r["attempts"]) for r in rows]


def test_upload_returns_immediately_and_worker_processes(auth_client, queue, monkeypatch):
    calls = []
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: calls.append(path) or "Rajma...")
    monkeypatch.setattr(ai_service, "structure_recipe", lambda transcript: SAMPLE_RECIPE)
    project_id = create_project(auth_client)

    response = _upload(auth_client, project_id)
    row_id = int(response.headers["Location"].rstrip("/").split("/")[-1])
    assert recipe_service.get_recipe(row_id)["status"] == "received"
    assert calls == []
    assert queue.count == 1
    assert b"writing the recipe down" in auth_client.get(response.headers["Location"]).data

    run_jobs(queue)

    recipe = recipe_service.get_recipe(row_id)
    assert recipe["status"] == "needs_review"
    assert recipe["recipe_title"] == "Rajma"
    assert recipe["raw_transcript"] == "Rajma..."
    assert _runs() == [("transcribe", "succeeded", 1), ("structure", "succeeded", 1)]


def test_failed_job_is_retried_with_backoff_then_marked_failed(app, auth_client, queue, monkeypatch):
    monkeypatch.setattr(pipeline_service, "RETRY_INTERVALS", [0, 0])
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma...")

    def flaky(transcript):
        raise RuntimeError("Anthropic overloaded")

    monkeypatch.setattr(ai_service, "structure_recipe", flaky)
    project_id = create_project(auth_client)
    row_id = recipe_service.create_received_recipe(project_id, "abc.m4a")

    pipeline_service.enqueue_processing(row_id)
    for _ in range(3):
        run_jobs(queue)
        if recipe_service.get_recipe(row_id)["status"] == "failed":
            break
        # Retries with a 0s interval go straight back on the queue.
        assert recipe_service.get_recipe(row_id)["status"] == "transcribed"

    assert recipe_service.get_recipe(row_id)["status"] == "failed"
    # Transcribed once; the transcript is reused on every retry of the structuring step.
    assert _runs() == [
        ("transcribe", "succeeded", 1),
        ("structure", "failed", 1),
        ("structure", "failed", 2),
        ("structure", "failed", 3),
    ]


def test_retry_succeeds_after_transient_error(auth_client, queue, monkeypatch):
    monkeypatch.setattr(pipeline_service, "RETRY_INTERVALS", [0])
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma...")
    attempts = []

    def flaky_once(transcript):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("timeout")
        return SAMPLE_RECIPE

    monkeypatch.setattr(ai_service, "structure_recipe", flaky_once)
    project_id = create_project(auth_client)
    row_id = recipe_service.create_received_recipe(project_id, "abc.m4a")

    pipeline_service.enqueue_processing(row_id)
    run_jobs(queue)
    run_jobs(queue)

    assert recipe_service.get_recipe(row_id)["status"] == "needs_review"


def test_empty_transcript_fails_without_retry(auth_client, monkeypatch):
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "   ")
    project_id = create_project(auth_client)
    row_id = recipe_service.create_received_recipe(project_id, "abc.m4a")

    pipeline_service.process_recipe(row_id)

    assert recipe_service.get_recipe(row_id)["status"] == "failed"
    assert _runs() == [("transcribe", "failed", 1)]


def test_processed_recipe_is_not_reprocessed(auth_client, monkeypatch):
    project_id = create_project(auth_client)
    row_id = recipe_service.save_uploaded_recipe(project_id, "abc.m4a", "t", SAMPLE_RECIPE)
    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: pytest.fail("should not run"))

    pipeline_service.process_recipe(row_id)

    assert recipe_service.get_recipe(row_id)["status"] == "needs_review"
    assert _runs() == []


def test_failed_recipes_do_not_use_up_recipe_slots(auth_client):
    project_id = create_project(auth_client)
    row_id = recipe_service.create_received_recipe(project_id, "abc.m4a")
    assert project_service.get_project_recipe_count(project_id) == 1
    recipe_service.set_status(row_id, "failed")
    assert project_service.get_project_recipe_count(project_id) == 0


def test_pipeline_records_events(auth_client, monkeypatch):
    from models.schema import events

    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "   ")
    project_id = create_project(auth_client)
    failed = recipe_service.create_received_recipe(project_id, "a.m4a")
    pipeline_service.process_recipe(failed)

    monkeypatch.setattr(ai_service, "transcribe_audio", lambda path: "Rajma...")
    monkeypatch.setattr(ai_service, "structure_recipe", lambda transcript: SAMPLE_RECIPE)
    ok = recipe_service.create_received_recipe(project_id, "b.m4a")
    pipeline_service.process_recipe(ok)

    with get_engine().connect() as conn:
        rows = conn.execute(select(events.c.name, events.c.recipe_id, events.c.props).order_by(events.c.id)).all()
    assert [tuple(r) for r in rows] == [
        ("pipeline_failed", failed, {"stage": "transcribe"}),
        ("recipe_ready_for_review", ok, {}),
    ]

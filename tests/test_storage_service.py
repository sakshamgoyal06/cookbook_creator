import os

import boto3
import pytest
from moto import mock_aws

import config
from services import storage_service


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "incoming.m4a"
    path.write_bytes(b"mom's voice")
    return str(path)


@pytest.fixture
def s3(app, monkeypatch):
    with mock_aws():
        monkeypatch.setattr(config, "STORAGE_BACKEND", "s3")
        monkeypatch.setattr(config, "S3_BUCKET", "cookbook-test")
        monkeypatch.setattr(config, "S3_ENDPOINT_URL", None)
        monkeypatch.setattr(config, "S3_REGION", "us-east-1")
        monkeypatch.setattr(config, "S3_ACCESS_KEY_ID", "test")
        monkeypatch.setattr(config, "S3_SECRET_ACCESS_KEY", "test")
        monkeypatch.setattr(config, "S3_KEY_PREFIX", "prod/")
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="cookbook-test")
        yield client


def test_local_backend_uses_existing_folders(app, audio_file):
    storage_service.save_file("audio", "abc.m4a", audio_file)
    assert os.path.isfile(os.path.join(config.UPLOAD_FOLDER, "abc.m4a"))
    assert storage_service.exists("audio", "abc.m4a")
    with storage_service.local_copy("audio", "abc.m4a") as path:
        assert open(path, "rb").read() == b"mom's voice"

    with app.test_request_context():
        response = storage_service.send("audio", "abc.m4a")
        response.direct_passthrough = False
        assert response.get_data() == b"mom's voice"

    storage_service.delete("audio", "abc.m4a")
    assert not storage_service.exists("audio", "abc.m4a")
    storage_service.delete("audio", "abc.m4a")  # deleting twice is fine


def test_s3_backend_round_trip(app, s3, audio_file):
    storage_service.save_file("audio", "abc.m4a", audio_file, content_type="audio/mp4")

    head = s3.head_object(Bucket="cookbook-test", Key="prod/audio/abc.m4a")
    assert head["ContentType"] == "audio/mp4"
    assert storage_service.exists("audio", "abc.m4a")
    assert not storage_service.exists("audio", "missing.m4a")

    with storage_service.local_copy("audio", "abc.m4a") as path:
        assert path.endswith(".m4a")
        assert open(path, "rb").read() == b"mom's voice"
    assert not os.path.exists(path)  # the temporary download is cleaned up

    with app.test_request_context():
        response = storage_service.send("audio", "abc.m4a", download_name="rajma.m4a")
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "prod/audio/abc.m4a" in location and "Signature=" in location

    storage_service.delete("audio", "abc.m4a")
    assert not storage_service.exists("audio", "abc.m4a")


@pytest.mark.parametrize("name", ["", "../secret", "a/b.m4a", "..", "a\\b"])
def test_rejects_unsafe_names(app, name):
    with pytest.raises(ValueError):
        storage_service.exists("audio", name)


def test_rejects_unknown_namespace(app):
    with pytest.raises(ValueError):
        storage_service.exists("secrets", "x.txt")


def test_upload_and_pdf_go_through_s3(auth_client, s3, monkeypatch):
    import io

    from conftest import SAMPLE_RECIPE, create_project
    from services import ai_service, recipe_service

    seen = {}

    def fake_transcribe(path):
        seen["audio"] = open(path, "rb").read()
        return "Rajma banane ke liye..."

    monkeypatch.setattr(ai_service, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(ai_service, "structure_recipe", lambda transcript: SAMPLE_RECIPE)
    project_id = create_project(auth_client)

    response = auth_client.post(
        f"/projects/{project_id}/upload",
        data={"audio_file": (io.BytesIO(b"fake audio"), "note.m4a", "audio/m4a")},
        content_type="multipart/form-data",
    )
    row_id = int(response.headers["Location"].rstrip("/").split("/")[-1])
    audio_key = recipe_service.get_recipe(row_id)["audio_clips"][0]["storage_key"]
    stored = s3.get_object(Bucket="cookbook-test", Key=f"prod/audio/{audio_key}")
    assert stored["Body"].read() == b"fake audio"
    assert seen["audio"] == b"fake audio"
    assert os.listdir(config.UPLOAD_FOLDER) == []

    auth_client.post(f"/projects/{project_id}/recipes/{row_id}/generate-pdf")
    pdf_name = recipe_service.get_recipe(row_id)["pdf_filename"]
    pdf = s3.get_object(Bucket="cookbook-test", Key=f"prod/pdfs/{pdf_name}")
    assert pdf["Body"].read().startswith(b"%PDF")
    assert os.listdir(config.OUTPUT_FOLDER) == []

    response = auth_client.get(f"/projects/{project_id}/recipes/{row_id}/pdf")
    assert response.status_code == 302
    assert "Signature=" in response.headers["Location"]

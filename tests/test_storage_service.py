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

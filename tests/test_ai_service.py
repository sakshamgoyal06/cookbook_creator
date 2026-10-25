import json
from types import SimpleNamespace
from unittest import mock

import jsonschema
import pytest

import config
from conftest import SAMPLE_RECIPE
from services import ai_service


def _response(stop_reason="end_turn", text=json.dumps(SAMPLE_RECIPE)):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


@pytest.fixture
def anthropic_client(monkeypatch):
    with mock.patch.object(ai_service, "Anthropic") as anthropic_cls:
        yield anthropic_cls


def test_sample_recipe_matches_schema():
    jsonschema.validate(SAMPLE_RECIPE, ai_service.RECIPE_SCHEMA)


def test_structure_recipe_request_and_parse(anthropic_client, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_RECIPE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setattr(config, "ANTHROPIC_RECIPE_EFFORT", "medium")
    monkeypatch.setattr(config, "ANTHROPIC_RECIPE_TEMPERATURE", None)
    anthropic_client.return_value.messages.create.return_value = _response()

    result = ai_service.structure_recipe("Rajma banane ke liye...")

    assert result == SAMPLE_RECIPE
    kwargs = anthropic_client.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": ai_service.RECIPE_SCHEMA}
    assert kwargs["output_config"]["effort"] == "medium"
    assert "temperature" not in kwargs
    assert "Rajma banane ke liye..." in kwargs["messages"][0]["content"]
    assert "Hinglish" in kwargs["messages"][0]["content"] and "{{" not in kwargs["messages"][0]["content"]
    ai_service.structure_recipe("x", language="hi")
    assert "Devanagari" in anthropic_client.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert anthropic_client.call_args.kwargs["base_url"] == config.ANTHROPIC_BASE_URL


def test_effort_and_temperature_are_optional(anthropic_client, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_RECIPE_EFFORT", None)
    monkeypatch.setattr(config, "ANTHROPIC_RECIPE_TEMPERATURE", 0.3)
    anthropic_client.return_value.messages.create.return_value = _response()

    ai_service.structure_recipe("x")

    kwargs = anthropic_client.return_value.messages.create.call_args.kwargs
    assert "effort" not in kwargs["output_config"]
    assert kwargs["temperature"] == 0.3


@pytest.mark.parametrize("stop_reason, message", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_incomplete_responses_raise(anthropic_client, stop_reason, message):
    anthropic_client.return_value.messages.create.return_value = _response(stop_reason=stop_reason)
    with pytest.raises(ValueError, match=message):
        ai_service.structure_recipe("x")


def test_invalid_json_raises(anthropic_client):
    anthropic_client.return_value.messages.create.return_value = _response(text="not json")
    with pytest.raises(ValueError, match="invalid JSON"):
        ai_service.structure_recipe("x")


def test_transcribe_audio_uses_configured_model(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
    audio = tmp_path / "note.m4a"
    audio.write_bytes(b"fake")
    with mock.patch.object(ai_service, "OpenAI") as openai_cls:
        openai_cls.return_value.audio.transcriptions.create.return_value = SimpleNamespace(text="namaste")
        assert ai_service.transcribe_audio(str(audio)) == "namaste"
        kwargs = openai_cls.return_value.audio.transcriptions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-transcribe"
        assert kwargs["file"][0] == "note.m4a"
        assert openai_cls.call_args.kwargs["base_url"] == config.OPENAI_BASE_URL

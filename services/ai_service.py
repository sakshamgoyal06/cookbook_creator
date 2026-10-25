import json
import os
import subprocess
import tempfile
from openai import OpenAI
from anthropic import Anthropic
import config


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_STRING = {"type": "string"}
_STRING_LIST = {"type": "array", "items": _STRING}

# Mirrors the JSON shape described in prompts/recipe_editor_prompt.txt and
# read by recipe_service.save_uploaded_recipe.
RECIPE_SCHEMA = _object({
    "recipe_title": _STRING,
    "alternate_names": _STRING_LIST,
    "category": _STRING,
    "family_note": _STRING,
    "serves": _STRING,
    "prep_time_minutes": _nullable({"type": "integer"}),
    "cook_time_minutes": _nullable({"type": "integer"}),
    "difficulty": _STRING,
    "ingredients": {
        "type": "array",
        "items": _object({
            "item": _STRING,
            "quantity": _STRING,
            "unit": _STRING,
            "preparation_note": _STRING,
        }),
    },
    "method_steps": {
        "type": "array",
        "items": _object({
            "step_number": {"type": "integer"},
            "instruction": _STRING,
            "flame_level": _STRING,
            "timing": _STRING,
            "sensory_cue": _STRING,
        }),
    },
    "moms_tips": _STRING_LIST,
    "serving_suggestion": _STRING,
    "storage_notes": _STRING,
    "unclear_items_for_review": _STRING_LIST,
    "follow_up_questions": {
        "type": "array",
        "items": _object({"about": _STRING, "question": _STRING, "options": _STRING_LIST}),
    },
})

LANGUAGE_NAMES = {"hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi in Latin script)",
                  "en": "simple Indian English"}


def _get_openai_client():
    return OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


def _get_anthropic_client():
    return Anthropic(api_key=config.ANTHROPIC_API_KEY, base_url=config.ANTHROPIC_BASE_URL)


# What the transcription API accepts, by file name. Anything else is converted first.
TRANSCRIBE_EXTENSIONS = (".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm")


def transcribe_audio(file_path: str) -> str:
    client = _get_openai_client()
    stem, ext = os.path.splitext(os.path.basename(file_path))
    ext = ext.lower()
    if ext == ".opus":  # WhatsApp voice notes on Android: Opus in an Ogg file, sent under its usual name
        ext = ".ogg"
    if ext in TRANSCRIBE_EXTENSIONS:
        with open(file_path, "rb") as audio_file:
            return _transcribe(client, (stem + ext, audio_file))
    # iPhone .aac/.caf and other odd files: convert to mp3 with ffmpeg first.
    with tempfile.TemporaryDirectory() as folder:
        converted = os.path.join(folder, stem + ".mp3")
        try:
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", file_path, "-vn", "-ac", "1",
                            "-b:a", "64k", converted], check=True, capture_output=True, timeout=300)
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg is needed to read this audio format") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg could not read the audio: {e.stderr.decode(errors='replace')[:300]}") from e
        with open(converted, "rb") as audio_file:
            return _transcribe(client, (stem + ".mp3", audio_file))


def _transcribe(client, file):
    return client.audio.transcriptions.create(model=config.OPENAI_TRANSCRIBE_MODEL, file=file).text


def structure_recipe(transcript: str, language: str = "hinglish") -> dict:
    prompt_path = os.path.join(config.PROMPTS_FOLDER, "recipe_editor_prompt.txt")
    with open(prompt_path, "r") as f:
        prompt_template = f.read()

    prompt = (prompt_template.replace("{{TRANSCRIPT}}", transcript)
              .replace("{{LANGUAGE}}", LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["hinglish"])))

    request = {
        "model": config.ANTHROPIC_RECIPE_MODEL,
        "max_tokens": config.ANTHROPIC_RECIPE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": RECIPE_SCHEMA}},
    }
    if config.ANTHROPIC_RECIPE_EFFORT:
        request["output_config"]["effort"] = config.ANTHROPIC_RECIPE_EFFORT
    if config.ANTHROPIC_RECIPE_TEMPERATURE is not None:
        request["temperature"] = config.ANTHROPIC_RECIPE_TEMPERATURE

    client = _get_anthropic_client()
    response = client.messages.create(**request)

    if response.stop_reason == "refusal":
        raise ValueError("The AI declined to structure this transcript.")
    if response.stop_reason == "max_tokens":
        raise ValueError(
            "The AI response was cut off. Increase ANTHROPIC_RECIPE_MAX_TOKENS and try again."
        )

    content = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\nRaw response:\n{content}")

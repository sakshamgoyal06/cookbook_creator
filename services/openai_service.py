import json
import os
from openai import OpenAI
from anthropic import Anthropic
import config


def _get_openai_client():
    return OpenAI(api_key=config.OPENAI_API_KEY)


def _get_anthropic_client():
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _extract_text_content(response) -> str:
    content = ""
    for block in response.content:
        if block.type == "text":
            content += block.text
    return content.strip()


def _extract_json_object(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_recipe_json(text: str) -> dict:
    cleaned = _extract_json_object(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\nRaw response:\n{text}")


def transcribe_audio(file_path: str) -> str:
    client = _get_openai_client()
    with open(file_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=config.OPENAI_TRANSCRIBE_MODEL,
            file=audio_file,
        )
    return result.text


def structure_recipe(transcript: str) -> dict:
    prompt_path = os.path.join(config.PROMPTS_FOLDER, "recipe_editor_prompt.txt")
    with open(prompt_path, "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{{TRANSCRIPT}}", transcript)
    client = _get_anthropic_client()

    token_limits = [12000, 16000]
    last_error = None

    for max_tokens in token_limits:
        response = client.messages.create(
            model=config.ANTHROPIC_RECIPE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        content = _extract_text_content(response)

        try:
            return _parse_recipe_json(content)
        except ValueError as e:
            last_error = e
            if response.stop_reason == "max_tokens":
                continue
            raise

    raise last_error

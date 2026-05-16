import json
import os
from openai import OpenAI
from anthropic import Anthropic
import config


def _get_openai_client():
    return OpenAI(api_key=config.OPENAI_API_KEY)


def _get_anthropic_client():
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


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
    response = client.messages.create(
        model=config.ANTHROPIC_RECIPE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    content = response.content[0].text.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        lines = [line for line in lines if not line.startswith("```")]
        content = "\n".join(lines)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\nRaw response:\n{content}")

# AGENTS.md

## Project Overview

Mom's Cookbook Studio — a Flask web app that converts recipe voice notes into structured cookbook recipes with PDF generation.

## Cursor Cloud specific instructions

### Running the app

```bash
python3 app.py
```

Starts on `http://localhost:5000` in debug mode. Uses `python3` (not `python`).

### Key services

| Service | How to run | Notes |
|---------|-----------|-------|
| Flask dev server | `python3 app.py` | Runs on port 5000, debug mode with hot reload |
| SQLite DB | Auto-created at `instance/cookbook.db` on first run | No separate process needed |
| OpenAI API | Requires `OPENAI_API_KEY` in `.env` | Used for audio transcription (`gpt-4o-transcribe`) |
| Anthropic API | Requires `ANTHROPIC_API_KEY` in `.env` | Used for recipe structuring via Claude (`claude-sonnet-5`) |

### Linting

```bash
flake8 --max-line-length=120 --exclude=__pycache__,instance,uploads,outputs,.git app.py config.py models/ services/
```

### Important caveats

- **WeasyPrint system deps**: Requires `libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf2.0-0`, `libffi-dev`, `libcairo2` installed at OS level. Without these, PDF generation will fail.
- **ffmpeg**: Required to convert uploaded `.opus` voice notes into a format supported by OpenAI transcription.
- **No `python` symlink**: Use `python3` explicitly.
- **API keys**: The upload flow needs both `OPENAI_API_KEY` (transcription) and `ANTHROPIC_API_KEY` (structuring). All other flows (view, edit, approve, PDF generation) work without them.
- **PATH**: pip installs scripts to `~/.local/bin` — ensure it's on PATH (`export PATH="$HOME/.local/bin:$PATH"`).
- **Database**: Auto-initializes on first `python3 app.py` run. No migrations needed.

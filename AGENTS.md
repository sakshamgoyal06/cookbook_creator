# AGENTS.md

## Project Overview

Mom's Cookbook Studio — a Flask web app that converts recipe voice notes into structured cookbook recipes with PDF generation.

Product requirements, priorities (P0/P1/P2) and the build order are in `docs/PRD.md`. Check new work against it.
The milestone checklist is `docs/BUILD_PLAN.md`: pick the next unticked item, and tick it in the same commit as the work.

## Cursor Cloud specific instructions

### Running the app

```bash
python3 app.py
```

Starts on `http://localhost:5000` in debug mode. Uses `python3` (not `python`).

When testing from a phone on the same Wi-Fi, start the app and use the printed URL like `http://192.168.x.x:5000` in the phone browser. The computer running `python3 app.py` must stay on and awake.

### Key services

| Service | How to run | Notes |
|---------|-----------|-------|
| Flask dev server | `python3 app.py` | Runs on port 5000, debug mode with hot reload |
| Database | SQLite at `instance/cookbook.db` by default; Postgres when `DATABASE_URL` is set (`make db-up` starts one in Docker) | Schema changes go through Alembic migrations, see `docs/DATABASE.md` |
| OpenAI API | Requires `OPENAI_API_KEY` in `.env` | Used for audio transcription (`gpt-4o-transcribe`) |
| Anthropic API | Requires `ANTHROPIC_API_KEY` in `.env` | Used for recipe structuring via Claude |

### Deploying (Railway)

Railway builds the `Dockerfile` (see `railway.json`) runs `python wsgi.py migrate` (Alembic migrations), then `gunicorn wsgi:app` on `$PORT`, with `/healthz` as the health check. Set these service variables in Railway: `FLASK_SECRET_KEY` (required: the app refuses to start without a real key when `FLASK_DEBUG` is off), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `DATABASE_URL` (reference the Railway Postgres service's `DATABASE_URL`; without it the app falls back to SQLite, which Railway wipes on every redeploy). Leave `FLASK_DEBUG` unset in production.

### Linting and tests

```bash
pip install -r requirements-dev.txt
flake8 --max-line-length=120 --exclude=__pycache__,instance,uploads,outputs,.git app.py config.py models/ services/ tests/ migrations/ scripts/
pytest -q
```

Tests use a temporary SQLite database and mock the OpenAI and Anthropic clients, so they need no API keys. CI (`.github/workflows/ci.yml`) runs both on every PR.

### Important caveats

- **WeasyPrint system deps**: Requires `libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf2.0-0`, `libffi-dev`, `libcairo2` installed at OS level. Without these, PDF generation will fail.
- **No `python` symlink**: Use `python3` explicitly.
- **API keys**: The upload flow needs both `OPENAI_API_KEY` (transcription) and `ANTHROPIC_API_KEY` (structuring). All other flows (view, edit, approve, PDF generation) work without them.
- **PATH**: pip installs scripts to `~/.local/bin` — ensure it's on PATH (`export PATH="$HOME/.local/bin:$PATH"`).
- **Database**: `python3 app.py` applies pending migrations on start. Never edit tables by hand or in `init_db()`: add a migration in `migrations/versions/` and update `models/schema.py` to match (`tests/test_database.py` checks they agree). Set `TEST_POSTGRES_URL` to also run the migration tests on Postgres.

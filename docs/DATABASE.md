# Database

The app uses **SQLite** on a laptop and in tests, and **Postgres** when hosted. `DATABASE_URL` picks which one; empty means `instance/cookbook.db`. Tables are defined in `models/schema.py` and changed only through **Alembic** migrations in `migrations/versions/`.

## Quick start

| I want to… | Run |
|---|---|
| Keep using SQLite | Nothing. `python3 app.py` applies any pending migrations on start, including to an `instance/cookbook.db` made before migrations existed. |
| Use Postgres on my laptop | `make db-up`, then put `DATABASE_URL=postgresql://cookbook:cookbook@localhost:5432/cookbook` in `.env` and run `make db-migrate` |
| Get demo data | `make db-seed`, then log in as `demo@example.com` / `demo1234` |
| Move my SQLite data into Postgres | `make db-copy-sqlite` (Postgres must be empty; your SQLite file is not changed) |
| Start Postgres from scratch | `make db-reset` (deletes the Docker database) |
| Take a backup | `make db-backup` → `backups/cookbook-<time>.dump`. Restore: `pg_restore --clean --no-owner -d "$DATABASE_URL" backups/<file>.dump` |

`make db-up` needs Docker Desktop (or Docker Engine). `make db-backup` needs the Postgres client tools (`brew install libpq` on a Mac).

## Hosted setup (once)

1. Create a managed Postgres 16 database on your host (Render, Neon or Supabase all work) and turn on daily backups.
2. Copy its connection URL into the web service's (and later the worker's) environment as `DATABASE_URL`. A `postgres://…` URL is fine; the app switches it to the psycopg driver.
3. Run `make db-migrate` as the deploy's release or pre-deploy command, so every deploy applies new migrations before the app starts.
4. Optional, only if your local SQLite has data worth keeping: `python3 scripts/migrate_sqlite_to_postgres.py --to "<the URL>"`. Then copy `uploads/` and `outputs/` too, until object storage lands.

## Tables

| Table | What it holds | Added in |
|---|---|---|
| `users` | Buyers who log in. Email is unique and stored lowercase; Google ids are unique per provider. | baseline, 0002 |
| `projects` | One gift cookbook. `book_token` is the public id for the book QR (`/b/<token>`). | baseline, 0003 |
| `recipes` | One recipe. Lists (ingredients, steps, tips, unclear items) are JSON (JSONB on Postgres). `status` is one of `received, transcribed, structured, awaiting_mom, needs_review, approved, failed`. `listen_token` is the public id for the recipe QR (`/l/<token>`); `listen_revoked_at` turns it off. | baseline, 0002, 0003 |
| `recipe_audio` | The voice clips a recipe's QR plays, in `play_order`. `kind` is `original`, `followup` or `story`. | 0003 |
| `listen_events` | One row per QR play, with no personal data. | 0003 |
| `generated_files` | PDFs and images made for a project or recipe. Ownership checks on downloads look here. | 0002 |
| `pipeline_runs` | One row per worker step (transcribe, structure…): status, attempts, error, model, tokens and cost in paise. | 0002 |
| `dish_images` | The shared library of free-licence dish photos, filed by `dish_key` (the dish name, lowercased). Holds the licence, the creator and the stored copy; `use_count` counts the books that used it. A recipe using one has `photo_image_id` and `photo_credit` set. Photo crops live on `projects.photo_crops` and `recipes.photo_crop`. | 0010, 0011 |

Deleting a project deletes its recipes, audio rows, files rows, plays and pipeline runs (`ON DELETE CASCADE`). Public links never use database ids; tokens come from `secrets.token_urlsafe(16)` (128 bits).

Planned with later milestones: storyteller and consent columns plus `wa_messages` (M2), `recipe_questions` (M3), `dish_requests` and `reminder_sends` (M4), `orders` and `payment_events` (M5), `analytics_events` (M7).

## Changing the schema

1. Edit `models/schema.py`.
2. `alembic revision -m "short description"` and write `upgrade()` and `downgrade()` by hand (or start from `alembic revision --autogenerate`). Keep the file self-contained: copy constants into it rather than importing from `models/`, so old migrations never change.
3. Use `op.batch_alter_table(...)` for changes to existing tables, so SQLite works too.
4. `pytest tests/test_database.py`. It checks that migrations produce exactly `models/schema.py`, that a pre-migration SQLite file upgrades cleanly, and that downgrade and upgrade both work. Set `TEST_POSTGRES_URL` to a throwaway Postgres database to run the same tests there (CI does).

## What changed from the old SQLite tables

- `recipes.status` values were mapped: `uploaded` → `received`, `pdf_generated` → `approved`. Generating a PDF no longer changes a recipe's status.
- `recipes.pdf_filename` moved to `generated_files`, and `recipes.audio_filename` moved to `recipe_audio`. The service layer still returns `pdf_filename`, and adds `audio_clips`.
- Timestamps are time-zone aware and set by the database.

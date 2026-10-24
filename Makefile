.PHONY: db-up db-down db-migrate db-reset db-seed db-copy-sqlite db-backup

# Start local Postgres + Redis and wait until Postgres is ready.
db-up:
	docker compose up -d --wait postgres redis

db-down:
	docker compose down

# Apply all migrations to DATABASE_URL (SQLite if unset). Also upgrades a pre-migration SQLite file.
db-migrate:
	python3 -c "from models.database import init_db; init_db()"

# Wipe the local Docker Postgres and rebuild it from migrations.
db-reset:
	docker compose down -v
	docker compose up -d --wait postgres redis
	python3 -c "from models.database import init_db; init_db()"

db-seed:
	python3 scripts/seed_demo.py

# Copy instance/cookbook.db into the (empty) Postgres at DATABASE_URL.
db-copy-sqlite:
	python3 scripts/migrate_sqlite_to_postgres.py

db-backup:
	scripts/db_backup.sh

#!/usr/bin/env bash
# Dump the Postgres database at DATABASE_URL to backups/cookbook-<UTC time>.dump
# Restore with: pg_restore --clean --no-owner -d "$DATABASE_URL" backups/<file>.dump
set -euo pipefail

if [[ -f .env && -z "${DATABASE_URL:-}" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | cut -d= -f2- || true)"
fi
url="${DATABASE_URL:-}"
if [[ "$url" != postgres* ]]; then
  echo "Set DATABASE_URL to a Postgres URL." >&2
  exit 1
fi
url="${url/postgresql+psycopg:/postgresql:}"

mkdir -p backups
file="backups/cookbook-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --dbname="$url" --file="$file"
echo "Wrote $file ($(du -h "$file" | cut -f1))"

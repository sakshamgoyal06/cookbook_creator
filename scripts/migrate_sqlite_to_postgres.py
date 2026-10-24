"""Copy everything from the local SQLite database into Postgres.

    python3 scripts/migrate_sqlite_to_postgres.py --to postgresql://user:pass@host/db

The SQLite file is not changed: a temporary copy is upgraded to the latest
schema first, then every table is copied in one transaction. Postgres must be
empty (run it once, right after creating the database).
"""
import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

import config  # noqa: E402
from models.database import get_engine, init_db, normalize_url  # noqa: E402
from models.schema import metadata  # noqa: E402

BATCH_SIZE = 500


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", default=config.DATABASE_PATH, help="SQLite file to copy from")
    parser.add_argument("--to", dest="target", default=os.getenv("DATABASE_URL", ""), help="Postgres URL")
    args = parser.parse_args()

    target_url = normalize_url(args.target)
    if not target_url.startswith("postgresql"):
        sys.exit("Give a Postgres URL with --to or DATABASE_URL.")
    if not os.path.exists(args.source):
        sys.exit(f"SQLite file not found: {args.source}")

    with tempfile.TemporaryDirectory() as tmp:
        copy_path = os.path.join(tmp, "source.db")
        shutil.copy(args.source, copy_path)
        source_url = f"sqlite:///{copy_path}"
        print("Upgrading a temporary copy of the SQLite database...")
        init_db(source_url)
        print("Applying migrations to Postgres...")
        init_db(target_url)
        copy_all(get_engine(source_url), get_engine(target_url))


def copy_all(source, target):
    tables = metadata.sorted_tables
    with target.connect() as conn:
        busy = [t.name for t in tables if conn.execute(select(func.count()).select_from(t)).scalar_one()]
    if busy:
        sys.exit(f"Postgres already has rows in: {', '.join(busy)}. Use an empty database.")

    with source.connect() as src, target.begin() as dst:
        dst.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")  # SQLite times are UTC without an offset
        print(f"{'table':<18}{'sqlite':>8}{'postgres':>10}")
        for table in tables:
            rows = [dict(r) for r in src.execute(select(table)).mappings()]
            for start in range(0, len(rows), BATCH_SIZE):
                dst.execute(table.insert(), rows[start:start + BATCH_SIZE])
            if "id" in table.c:
                # Rows kept their ids, so move each id sequence past the highest one.
                dst.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table.name}"
                )
            copied = dst.execute(select(func.count()).select_from(table)).scalar_one()
            print(f"{table.name:<18}{len(rows):>8}{copied:>10}")
            if copied != len(rows):
                raise RuntimeError(f"{table.name}: copied {copied} of {len(rows)} rows")
    print("Done. Audio and PDF files stay in uploads/ and outputs/; copy those separately.")


if __name__ == "__main__":
    main()

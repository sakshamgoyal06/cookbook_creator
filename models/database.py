import os
import secrets

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect

import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_REVISION = "0001"

_engines = {}


def normalize_url(url):
    """Accept the postgres:// URLs hosts hand out and use the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine(url=None):
    url = normalize_url(url or config.DATABASE_URL)
    engine = _engines.get(url)
    if engine is None:
        if url.startswith("sqlite"):
            path = url.split("///", 1)[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        engine = create_engine(url, pool_pre_ping=True)
        if engine.dialect.name == "sqlite":
            event.listen(engine, "connect", _sqlite_on_connect)
        _engines[url] = engine
    return engine


def _sqlite_on_connect(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def new_token():
    """Random URL-safe token, 128 bits (QR-3)."""
    return secrets.token_urlsafe(16)


def alembic_config(url=None):
    cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BASE_DIR, "migrations"))
    cfg.attributes["database_url"] = normalize_url(url or config.DATABASE_URL)
    return cfg


def init_db(url=None):
    """Bring the database up to the latest migration.

    A database made before migrations existed (tables but no alembic_version)
    is stamped as the baseline first, then upgraded.
    """
    cfg = alembic_config(url)
    tables = set(inspect(get_engine(url)).get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

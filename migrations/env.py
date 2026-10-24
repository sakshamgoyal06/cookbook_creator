from logging.config import fileConfig

from alembic import context

from models.database import get_engine, normalize_url
from models.schema import metadata
import config as app_config

alembic_cfg = context.config
if alembic_cfg.config_file_name is not None and not alembic_cfg.attributes.get("database_url"):
    fileConfig(alembic_cfg.config_file_name, disable_existing_loggers=False)

database_url = alembic_cfg.attributes.get("database_url") or normalize_url(app_config.DATABASE_URL)


def run_migrations_offline():
    context.configure(
        url=database_url,
        target_metadata=metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with get_engine(database_url).connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # SQLite migrations rebuild tables; with foreign keys on, dropping the old
            # table would cascade-delete or reject its child rows. Checked again below.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            problems = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if problems:
                raise RuntimeError(f"Foreign key check failed after migration: {problems[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

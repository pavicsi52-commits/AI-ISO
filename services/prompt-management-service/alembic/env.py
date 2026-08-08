"""Alembic migration environment.

Resolves this service's own DSN from :func:`app.config.settings
.get_settings` (never hardcoded in ``alembic.ini``), converted to the
sync ``psycopg`` DSN Alembic's command API needs via
:func:`shared_core.database.migration.sync_dsn`, and targets
``app.models``' full :data:`~shared_core.database.base.Base.metadata`
for autogenerate support.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from shared_core.database.base import Base
from shared_core.database.migration import sync_dsn
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  -- import registers every table with Base.metadata
from app.config.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", sync_dsn(get_settings().database.dsn))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

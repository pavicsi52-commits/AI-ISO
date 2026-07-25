"""Migration Framework.

Per docs/018_Enterprise_Database_Framework.md.txt "MIGRATION FRAMEWORK":
Alembic Integration, Migration Generator, Migration Validator, Rollback,
Version History, Migration Status. "Never modify production schema
manually."

This package owns no business schema, so it doesn't ship a
``migrations/`` directory itself -- each service owns its own Alembic
``script_location`` (env.py + versions/) with its own ``target_metadata``.
What lives here is the plumbing every service's migration tooling shares:
building the ``Config`` consistently, running Alembic's command API against
it with framework exceptions instead of bare Alembic ones, and read-only
status/history/validation queries usable independent of any specific
service's models.

Alembic's command API (``upgrade``/``downgrade``/``revision``) is
synchronous, so it runs over ``psycopg`` (sync) rather than the
``asyncpg``-based :class:`~sqlalchemy.ext.asyncio.AsyncEngine` the rest of
this framework uses for application traffic -- exactly the standard
"asyncpg for the app, psycopg for migration tooling" split.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from shared_core.database.exceptions import MigrationFailedError


def sync_dsn(dsn: str) -> str:
    """Convert an ``asyncpg`` DSN into the ``psycopg`` DSN Alembic's sync command API needs."""
    if "+asyncpg" in dsn:
        return dsn.replace("+asyncpg", "+psycopg")
    return dsn


def build_alembic_config(*, script_location: str | Path, dsn: str) -> Config:
    """Build an Alembic :class:`Config` programmatically.

    Every service's ``alembic/env.py`` (and any CLI wrapper script) calls
    this instead of hand-parsing its own ``alembic.ini``, keeping the
    ``{script_location, sqlalchemy.url}`` wiring in one place.
    """
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", sync_dsn(dsn))
    return config


def upgrade(config: Config, revision: str = "head") -> None:
    """Apply migrations up to *revision* (default: the latest)."""
    try:
        command.upgrade(config, revision)
    except Exception as exc:
        raise MigrationFailedError(f"Migration upgrade to {revision!r} failed.") from exc


def downgrade(config: Config, revision: str) -> None:
    """Roll back migrations down to *revision*."""
    try:
        command.downgrade(config, revision)
    except Exception as exc:
        raise MigrationFailedError(f"Migration downgrade to {revision!r} failed.") from exc


def generate_revision(config: Config, message: str, *, autogenerate: bool = False) -> str | None:
    """Create a new migration script and return its revision ID.

    ``autogenerate=True`` diffs the database against the service's
    ``target_metadata`` (configured in its own ``env.py``) to draft the
    operations; ``autogenerate=False`` creates an empty script for the
    developer to fill in by hand.
    """
    try:
        script = command.revision(config, message=message, autogenerate=autogenerate)
    except Exception as exc:
        raise MigrationFailedError(f"Migration generation for {message!r} failed.") from exc
    if script is None:
        return None
    revision = script[0] if isinstance(script, list) else script
    return revision.revision  # type: ignore[union-attr]


def get_current_revision(connection: Connection) -> str | None:
    """Return the revision currently applied to the database *connection* points at.

    Returns ``None`` if no migrations have ever been applied (no
    ``alembic_version`` table yet).
    """
    return MigrationContext.configure(connection).get_current_revision()


async def get_current_revision_async(engine: AsyncEngine) -> str | None:
    """Async wrapper for :func:`get_current_revision` against an :class:`AsyncEngine`."""
    async with engine.connect() as connection:
        return await connection.run_sync(get_current_revision)


def get_head_revision(config: Config) -> str | None:
    """Return the latest ("head") revision known to *config*'s migration scripts."""
    return ScriptDirectory.from_config(config).get_current_head()


def get_migration_history(config: Config) -> list[str]:
    """Return every revision ID known to *config*'s migration scripts, oldest first."""
    script = ScriptDirectory.from_config(config)
    return [rev.revision for rev in reversed(list(script.walk_revisions()))]


def validate_migrations(config: Config) -> None:
    """Raise :class:`MigrationFailedError` if the migration scripts have diverged heads.

    A fork (two revisions with no single common descendant) must be merged
    with ``alembic merge`` before the next deploy -- "Never modify
    production schema manually" (docs/018) extends to never resolving a
    fork by hand-editing ``down_revision`` either.
    """
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) > 1:
        raise MigrationFailedError(
            f"Migration scripts have diverged into {len(heads)} heads {heads!r}; merge them."
        )


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """A snapshot of a database's migration state relative to its migration scripts."""

    current_revision: str | None
    head_revision: str | None
    is_up_to_date: bool


async def get_migration_status(engine: AsyncEngine, config: Config) -> MigrationStatus:
    """Compare the database's applied revision against the scripts' head revision."""
    current = await get_current_revision_async(engine)
    head = get_head_revision(config)
    return MigrationStatus(
        current_revision=current, head_revision=head, is_up_to_date=current == head
    )


__all__ = [
    "MigrationStatus",
    "build_alembic_config",
    "downgrade",
    "generate_revision",
    "get_current_revision",
    "get_current_revision_async",
    "get_head_revision",
    "get_migration_history",
    "get_migration_status",
    "sync_dsn",
    "upgrade",
    "validate_migrations",
]

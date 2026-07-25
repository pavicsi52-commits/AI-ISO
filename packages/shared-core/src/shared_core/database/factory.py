"""Database Framework factory.

Assembles engine, session factory, and health/shutdown into one object a
service builds exactly once at startup -- the same "factory wires settings
into ready-to-use primitives" role
:mod:`shared_core.config.loader`/:mod:`shared_core.logging.factory` play for
their own frameworks. Distinct from :mod:`shared_core.database.fixtures`'s
:class:`~shared_core.database.fixtures.ModelFactory`, which builds *test
entities*, not the framework itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from shared_core.config.settings import DatabaseSettings
from shared_core.database.connection import graceful_shutdown, wait_for_database
from shared_core.database.engine import create_engine, create_test_engine
from shared_core.database.health import DatabaseHealthReport, get_health_report
from shared_core.database.session import create_session_factory


@dataclass(slots=True)
class DatabaseFramework:
    """Everything a service needs to talk to its database, assembled once at startup."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def check_health(self) -> DatabaseHealthReport:
        """Run the framework's standard health check against this engine."""
        return await get_health_report(self.engine)

    async def shutdown(self) -> None:
        """Gracefully close the connection pool. Call once at service shutdown."""
        await graceful_shutdown(self.engine)


async def create_database_framework(
    settings: DatabaseSettings,
    *,
    echo: bool = False,
    wait_for_ready: bool = True,
) -> DatabaseFramework:
    """Build a :class:`DatabaseFramework` from Configuration Framework settings.

    If *wait_for_ready* (the default), blocks with retry/backoff until the
    database accepts connections before returning -- call this at service
    startup so the very first request doesn't race a still-initializing
    database container.
    """
    engine = create_engine(settings, echo=echo)
    if wait_for_ready:
        await wait_for_database(engine)
    return DatabaseFramework(engine=engine, session_factory=create_session_factory(engine))


def create_test_database_framework(dsn: str, *, echo: bool = False) -> DatabaseFramework:
    """Build a :class:`DatabaseFramework` for tests, against a test DSN (e.g. in-memory SQLite)."""
    engine = create_test_engine(dsn, echo=echo)
    return DatabaseFramework(engine=engine, session_factory=create_session_factory(engine))


__all__ = ["DatabaseFramework", "create_database_framework", "create_test_database_framework"]

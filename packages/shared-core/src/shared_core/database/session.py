"""Async database session management.

Per docs/018_Enterprise_Database_Framework.md.txt "SESSION MANAGER": every
service constructs exactly one :class:`~sqlalchemy.ext.asyncio.async_sessionmaker`
at startup (:func:`create_session_factory`) and obtains sessions from it
through one of three call shapes, all of which guarantee cleanup on exit:

- :func:`get_session` -- one session per HTTP request (FastAPI ``Depends``).
- :func:`get_worker_session` -- one session per background job execution.
- :func:`session_scope` -- an explicit context manager for scripts/tests,
  with automatic commit-on-success / rollback-on-error ("Transaction Session").
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``.

    Each service constructs exactly one factory at startup and reuses it
    for every request.
    """
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session for the duration of a single unit of work.

    Intended for use as a FastAPI dependency:
    ``Depends(lambda: get_session(app.state.session_factory))``.
    """
    async with session_factory() as session:
        yield session


async def get_worker_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session scoped to a single background-worker job execution.

    Distinct from :func:`get_session` in name only -- background jobs and
    HTTP requests both get exactly one session for their whole lifetime, but
    naming the two separately keeps worker code from implying it runs inside
    a request.
    """
    async with session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Explicit transaction-scoped session for scripts, seeds, and tests.

    Commits on success, rolls back on any exception, and always closes the
    session -- "Automatic Cleanup" and "Session Lifetime Management" without
    requiring a framework (FastAPI, a job queue) to drive the lifecycle.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


__all__ = [
    "create_session_factory",
    "get_session",
    "get_worker_session",
    "session_scope",
]

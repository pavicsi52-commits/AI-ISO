"""Unit of Work.

Per docs/018_Enterprise_Database_Framework.md.txt "UNIT OF WORK": Begin,
Commit, Rollback, Nested Transactions, Context Manager, Retry Support,
Automatic Cleanup. "Every business operation must use Unit of Work."

:class:`UnitOfWork` is the object-oriented entry point business/service
code is expected to use directly; it composes the lower-level primitives in
:mod:`shared_core.database.transaction` (which remain available for callers
that already hold a session and just need transactional wrapping).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Self, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared_core.database.constants import (
    DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
    DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
    DEFAULT_TRANSACTION_MAX_ATTEMPTS,
)
from shared_core.database.exceptions import TransactionFailedError
from shared_core.database.transaction import is_retryable_error, nested_transaction

_T = TypeVar("_T")


class UnitOfWork:
    """Explicit begin/commit/rollback wrapper around one :class:`AsyncSession`.

    Usage::

        async with UnitOfWork(session_factory) as uow:
            uow.session.add(entity)
            # commits automatically on clean exit, rolls back on exception

    Nested units of work (``async with outer.nested() as inner``) use
    ``SAVEPOINT``s so an inner failure doesn't discard the outer transaction.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Build a unit of work.

        Either provide *session_factory* (a new session is opened on
        ``__aenter__`` and closed on ``__aexit__``), or provide an
        already-open *session* directly -- in that case the caller retains
        ownership of its lifecycle and this unit of work only commits or
        rolls it back, never closes it.
        """
        if session_factory is None and session is None:
            raise TypeError("UnitOfWork requires either session_factory or session.")
        self._session_factory = session_factory
        self._session = session
        self._owns_session = session is None

    @classmethod
    def from_session(cls, session: AsyncSession) -> UnitOfWork:
        """Build a :class:`UnitOfWork` around an already-open session.

        The caller retains ownership of the session's lifecycle -- exiting
        this unit of work commits/rolls back but does not close it.
        """
        return cls(session=session)

    @property
    def session(self) -> AsyncSession:
        """The session this unit of work is managing.

        Raises:
            RuntimeError: If accessed outside an ``async with`` block.
        """
        if self._session is None:
            raise RuntimeError("UnitOfWork.session accessed before __aenter__.")
        return self._session

    async def __aenter__(self) -> Self:
        if self._session is None:
            assert self._session_factory is not None
            self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            if self._owns_session:
                await session.close()
                self._session = None

    def nested(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Open a ``SAVEPOINT``-backed nested transaction within this unit of work."""
        return nested_transaction(self.session)

    async def run_with_retry(
        self,
        operation: Callable[[AsyncSession], Awaitable[_T]],
        *,
        max_attempts: int = DEFAULT_TRANSACTION_MAX_ATTEMPTS,
        backoff_base_seconds: float = DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
        backoff_max_seconds: float = DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
    ) -> _T:
        """Run *operation* against this unit of work's session, retrying on deadlock.

        Each retry attempt rolls back to the state at entry (via a savepoint)
        before rerunning *operation*, so partial writes from a failed
        attempt never leak into the retried one.
        """
        last_error: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with nested_transaction(self.session):
                    return await operation(self.session)
            except SQLAlchemyError as exc:
                if not is_retryable_error(exc) or attempt == max_attempts:
                    raise
                last_error = exc
                delay = min(backoff_base_seconds * (2 ** (attempt - 1)), backoff_max_seconds)
                delay += random.uniform(0, backoff_base_seconds)
                await asyncio.sleep(delay)

        raise TransactionFailedError(  # pragma: no cover
            "Unit of work retry loop exited unexpectedly."
        ) from last_error


__all__ = ["UnitOfWork"]

"""Transaction Manager.

Every business operation that writes to the database uses this instead of
committing sessions ad hoc, per docs/007_Database_Master_Architecture.md.txt
"TRANSACTIONS": atomic, rollback on failure, no partial updates. Expanded
per docs/018_Enterprise_Database_Framework.md.txt "TRANSACTION MANAGER" with
timeout, deadlock retry, and nested (savepoint) transactions. The
higher-level Unit-of-Work object (:mod:`shared_core.database.unit_of_work`)
is built on top of the primitives here.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.constants import (
    DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
    DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
    DEFAULT_TRANSACTION_MAX_ATTEMPTS,
    RETRYABLE_SQLSTATES,
)
from shared_core.database.exceptions import QueryTimeoutError, TransactionFailedError


def is_retryable_error(exc: BaseException) -> bool:
    """Return whether *exc* represents a transient failure worth retrying.

    Covers PostgreSQL deadlocks (``40P01``) and serialization failures
    (``40001``) under ``SERIALIZABLE``/``REPEATABLE READ`` isolation, and
    transient connection drops (``08006``) -- see
    :data:`shared_core.database.constants.RETRYABLE_SQLSTATES`.
    """
    if not isinstance(exc, DBAPIError):
        return False
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    return sqlstate in RETRYABLE_SQLSTATES


@asynccontextmanager
async def unit_of_work(
    session: AsyncSession,
    *,
    timeout_seconds: float | None = None,
) -> AsyncIterator[AsyncSession]:
    """Run a block of work in a single atomic transaction.

    Commits on success, rolls back and raises on failure, and never leaves a
    partially-applied transaction. If *timeout_seconds* is given and the
    block does not finish in time, raises :class:`QueryTimeoutError`.
    """
    try:
        if timeout_seconds is not None:
            async with asyncio.timeout(timeout_seconds):
                yield session
        else:
            yield session
        await session.commit()
    except TimeoutError as exc:
        await session.rollback()
        raise QueryTimeoutError(
            f"Transaction exceeded its {timeout_seconds}s timeout and was rolled back."
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise TransactionFailedError("Transaction failed and was rolled back.") from exc
    except Exception:
        await session.rollback()
        raise


@asynccontextmanager
async def nested_transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Run a block of work inside a ``SAVEPOINT`` nested within the caller's transaction.

    On failure, only the savepoint is rolled back -- the outer transaction
    (and anything already flushed before entering this block) is untouched
    and may still be committed by the caller.
    """
    async with session.begin_nested():
        yield session


async def run_with_retry[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_TRANSACTION_MAX_ATTEMPTS,
    backoff_base_seconds: float = DEFAULT_TRANSACTION_BACKOFF_BASE_SECONDS,
    backoff_max_seconds: float = DEFAULT_TRANSACTION_BACKOFF_MAX_SECONDS,
) -> T:
    """Call *func*, retrying with exponential backoff on retryable DB errors.

    *func* takes no arguments -- callers pass a closure (or
    ``functools.partial``) so each retry attempt reruns the whole operation,
    including any session/transaction setup it needs.
    """
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except SQLAlchemyError as exc:
            if not is_retryable_error(exc) or attempt == max_attempts:
                raise
            last_error = exc
            delay = min(backoff_base_seconds * (2 ** (attempt - 1)), backoff_max_seconds)
            delay += random.uniform(0, backoff_base_seconds)
            await asyncio.sleep(delay)

    # Unreachable: the loop always returns or raises. Kept for type-checkers.
    raise TransactionFailedError(  # pragma: no cover
        "Transaction retry loop exited unexpectedly."
    ) from last_error


__all__ = [
    "is_retryable_error",
    "nested_transaction",
    "run_with_retry",
    "unit_of_work",
]

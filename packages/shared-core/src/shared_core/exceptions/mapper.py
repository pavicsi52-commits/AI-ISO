"""Automatic exception mapping.

Turns an arbitrary caught exception -- a third-party library's own
exception type, or a plain Python builtin -- into the right
:class:`AIIOSException` subclass, so call sites (most importantly
:mod:`shared_core.exceptions.handlers`'s catch-all handler) never need a
bespoke ``except`` chain to classify what went wrong.
"""

from __future__ import annotations

from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.cache import CacheError
from shared_core.exceptions.database import DatabaseError
from shared_core.exceptions.network import NetworkError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.queue import QueueError
from shared_core.exceptions.service import UnknownError
from shared_core.exceptions.storage import StorageError
from shared_core.exceptions.timeout import AIIOSTimeoutError
from shared_core.exceptions.validation import ValidationError


def _mapping() -> tuple[tuple[tuple[type[Exception], ...], type[AIIOSException]], ...]:
    """Build the mapping lazily so an unavailable optional dependency
    (e.g. a service that doesn't depend on ``minio``) can't break import
    of this module -- only the mapping entries that need it.
    """
    entries: list[tuple[tuple[type[Exception], ...], type[AIIOSException]]] = [
        ((TimeoutError,), AIIOSTimeoutError),
        ((PermissionError,), AuthorizationError),
        ((KeyError, LookupError), NotFoundError),
        ((ValueError, TypeError), ValidationError),
        ((ConnectionError, OSError), NetworkError),
    ]

    try:
        from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

        entries.append(((SQLAlchemyError,), DatabaseError))
    except ImportError:
        pass

    try:
        from redis.exceptions import RedisError  # noqa: PLC0415

        entries.append(((RedisError,), CacheError))
    except ImportError:
        pass

    try:
        from aio_pika.exceptions import AMQPError  # noqa: PLC0415

        entries.append(((AMQPError,), QueueError))
    except ImportError:
        pass

    try:
        from minio.error import MinioException  # noqa: PLC0415

        entries.append(((MinioException,), StorageError))
    except ImportError:
        pass

    try:
        from jwt.exceptions import PyJWTError  # noqa: PLC0415

        entries.append(((PyJWTError,), AuthenticationError))
    except ImportError:
        pass

    try:
        from httpx import HTTPError  # noqa: PLC0415

        entries.append(((HTTPError,), NetworkError))
    except ImportError:
        pass

    return tuple(entries)


_MAPPING = _mapping()

# AI-IOS's own AI subsystem client errors aren't a third-party exception
# type -- there's no single upstream provider SDK to import here (the
# provider is configurable per docs/013's AISettings), so AIError has no
# automatic-mapping entry; services that call an AI provider SDK map its
# exceptions to AIError explicitly at the call site.


def map_exception(exc: Exception) -> AIIOSException:
    """Map an arbitrary exception to the appropriate :class:`AIIOSException`.

    An exception that's already an :class:`AIIOSException` is returned
    unchanged. Anything unrecognized becomes :class:`UnknownError` rather
    than raising -- this function is meant to be called from a catch-all
    handler that must never itself fail to produce a response.
    """
    if isinstance(exc, AIIOSException):
        return exc

    for exc_types, mapped_cls in _MAPPING:
        if isinstance(exc, exc_types):
            return mapped_cls(str(exc) or exc.__class__.__name__)

    return UnknownError(str(exc) or exc.__class__.__name__)

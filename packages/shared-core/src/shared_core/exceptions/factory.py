"""Exception factory: build an :class:`AIIOSException` from an error code.

The inverse of :mod:`shared_core.exceptions.mapper` (which classifies an
*existing* exception): given an ``AIIOS-<DOMAIN>-<NUMBER>`` code -- e.g.
one read back from a downstream AI-IOS service's error response, or from a
config-driven error definition -- reconstruct the correct exception type
locally.
"""

from __future__ import annotations

from typing import Any

from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.constants import ERROR_CODE_CATALOG
from shared_core.exceptions.service import UnknownError


def get_exception_class(error_code: str) -> type[AIIOSException]:
    """Return the :class:`AIIOSException` subclass registered for *error_code*.

    Falls back to :class:`UnknownError` for an unrecognized code rather
    than raising -- an unrecognized code is itself something a caller may
    need to represent as an exception, not a programming error to crash on.
    """
    return ERROR_CODE_CATALOG.get(error_code, UnknownError)


def create_exception(error_code: str, message: str, **kwargs: Any) -> AIIOSException:
    """Construct an exception instance for *error_code*.

    Any keyword accepted by :meth:`AIIOSException.__init__` (``user_message``,
    ``details``, ``metadata``, ``request_id``, ``correlation_id``,
    ``organization_id``, ``project_id``) may be passed through *kwargs*.
    """
    exception_cls = get_exception_class(error_code)
    return exception_cls(message, **kwargs)

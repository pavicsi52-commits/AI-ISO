"""Request-scoped security context.

Populated by a service's authentication middleware (once JWT verification
is wired in) and read by the ``@requires_*`` decorators in
``shared_core.decorators``. Mirrors the pattern used by
``shared_core.logging.context``.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from uuid import UUID

from shared_core.enums.role import Role


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """The authenticated caller's identity and tenant scope for this request."""

    user_id: UUID | None = None
    role: Role | None = None
    organization_id: UUID | None = None
    project_id: UUID | None = None
    auth_method: str | None = None
    mfa_verified: bool = False


_context_var: ContextVar[SecurityContext | None] = ContextVar("security_context", default=None)


def get_security_context() -> SecurityContext:
    """Return the current request's security context."""
    return _context_var.get() or SecurityContext()


def bind_security_context(**fields: object) -> None:
    """Merge the given fields into the current security context."""
    _context_var.set(replace(get_security_context(), **fields))  # type: ignore[arg-type]


def reset_security_context() -> None:
    """Clear the security context. Call at the end of each request."""
    _context_var.set(None)

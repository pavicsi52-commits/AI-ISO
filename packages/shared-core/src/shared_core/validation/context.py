"""Validation context: identity/tenant/request scope threaded through the pipeline.

Rules that need to know *who* is asking (permission checks, tenant
isolation, quota checks) read this rather than taking a dozen separate
parameters. Mirrors the ``LogContext``/``SecurityContext`` contextvar
pattern already established in :mod:`shared_core.logging.context` and
:mod:`shared_core.security.context`, but passed explicitly through the
pipeline rather than via a contextvar -- validation results must be
deterministic given their inputs, not depend on ambient state that could
change mid-pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Identity, tenant, and request scope available to every validation rule."""

    organization_id: UUID | None = None
    project_id: UUID | None = None
    user_id: UUID | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    locale: str = "en"
    extra: dict[str, Any] = field(default_factory=dict)

    def with_extra(self, **fields: Any) -> ValidationContext:
        """Return a copy with additional ``extra`` fields merged in."""
        return replace(self, extra={**self.extra, **fields})

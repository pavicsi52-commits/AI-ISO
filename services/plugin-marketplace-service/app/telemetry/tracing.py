"""Plugin marketplace telemetry (docs/059 "TELEMETRY"): Plugin Installation,
Activation, Execution, Upgrade, Rollback, Marketplace Search, Package
Verification.

Integrates ``shared_core.telemetry`` (Prompt 024).

**Every call below passes attributes via ``**{...}``, never a literal
``attributes={...}`` keyword.** ``start_span``'s own signature is
``start_span(tracer, name, *, span_type=None, **attributes)`` -- there is
no parameter actually named ``attributes``, only that catch-all. Passing
one anyway silently drops every attribute onto the floor instead of
raising -- a confirmed, repo-wide defect in every AI-IOS service after
``authentication-service``. This copy was written correct from the start.

**Spans carry identifiers and outcomes, never manifest/review/package
content.** A plugin's own manifest or a package's own bytes may carry
another tenant's sensitive data; a tracing backend has different
retention and different access rules than this service's own database
and object storage do.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Span, Tracer
from shared_core.telemetry.span import SpanType, start_span


@contextmanager
def trace_installation(
    tracer: Tracer, *, plugin_id: str, organization_id: str, **attributes: object
) -> Iterator[Span]:
    """Span installing a plugin into an organization."""
    with start_span(
        tracer,
        "marketplace.plugin.install",
        span_type=SpanType.REST_API,
        **{
            "marketplace.plugin_id": plugin_id,
            "marketplace.organization_id": organization_id,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_activation(
    tracer: Tracer, *, installation_id: str, **attributes: object
) -> Iterator[Span]:
    """Span activating an installed plugin instance."""
    with start_span(
        tracer,
        "marketplace.plugin.activate",
        span_type=SpanType.REST_API,
        **{"marketplace.installation_id": installation_id, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_execution(
    tracer: Tracer, *, installation_id: str, timed_out: bool, **attributes: object
) -> Iterator[Span]:
    """Span one sandboxed plugin entry-point execution."""
    with start_span(
        tracer,
        "marketplace.plugin.execute",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "marketplace.installation_id": installation_id,
            "marketplace.timed_out": timed_out,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_upgrade(
    tracer: Tracer,
    *,
    installation_id: str,
    from_version_number: str,
    to_version_number: str,
    **attributes: object,
) -> Iterator[Span]:
    """Span upgrading an installed plugin instance to a newer version."""
    with start_span(
        tracer,
        "marketplace.plugin.upgrade",
        span_type=SpanType.REST_API,
        **{
            "marketplace.installation_id": installation_id,
            "marketplace.from_version_number": from_version_number,
            "marketplace.to_version_number": to_version_number,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_rollback(
    tracer: Tracer,
    *,
    installation_id: str,
    from_version_number: str,
    to_version_number: str,
    **attributes: object,
) -> Iterator[Span]:
    """Span rolling an installed plugin instance back to an older version."""
    with start_span(
        tracer,
        "marketplace.plugin.rollback",
        span_type=SpanType.REST_API,
        **{
            "marketplace.installation_id": installation_id,
            "marketplace.from_version_number": from_version_number,
            "marketplace.to_version_number": to_version_number,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_marketplace_search(
    tracer: Tracer, *, query: str | None, results_returned: int, **attributes: object
) -> Iterator[Span]:
    """Span one marketplace search request."""
    with start_span(
        tracer,
        "marketplace.search",
        span_type=SpanType.REST_API,
        **{
            "marketplace.query": query or "",
            "marketplace.results_returned": results_returned,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_package_verification(
    tracer: Tracer, *, package_id: str, verified: bool, **attributes: object
) -> Iterator[Span]:
    """Span verifying a package's own Ed25519 signature."""
    with start_span(
        tracer,
        "marketplace.package.verify",
        span_type=SpanType.REST_API,
        **{"marketplace.package_id": package_id, "marketplace.verified": verified, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_health_check(
    tracer: Tracer, *, installation_id: str, status: str, **attributes: object
) -> Iterator[Span]:
    """Span one installation health probe."""
    with start_span(
        tracer,
        "marketplace.health.check",
        span_type=SpanType.BACKGROUND_JOB,
        **{
            "marketplace.installation_id": installation_id,
            "marketplace.status": status,
            **attributes,
        },
    ) as span:
        yield span


@contextmanager
def trace_worker_tick(
    tracer: Tracer, *, worker: str, processed: int, **attributes: object
) -> Iterator[Span]:
    """Span one background worker's sweep tick."""
    with start_span(
        tracer,
        "marketplace.worker.tick",
        span_type=SpanType.BACKGROUND_JOB,
        **{"marketplace.worker": worker, "marketplace.processed": processed, **attributes},
    ) as span:
        yield span


@contextmanager
def trace_publish(tracer: Tracer, *, event_name: str, **attributes: object) -> Iterator[Span]:
    """Span one domain-event publish."""
    with start_span(
        tracer,
        "marketplace.event.publish",
        span_type=SpanType.BACKGROUND_JOB,
        **{"marketplace.event": event_name, **attributes},
    ) as span:
        yield span


__all__ = [
    "trace_activation",
    "trace_execution",
    "trace_health_check",
    "trace_installation",
    "trace_marketplace_search",
    "trace_package_verification",
    "trace_publish",
    "trace_rollback",
    "trace_upgrade",
    "trace_worker_tick",
]

"""Background worker: scheduled escalation advancement ("PERFORMANCE":
Async Rule Evaluation, Distributed Workers, Horizontal Scaling).

``app/scheduling/registrar.py`` registers one recurring
``shared_core.scheduler.Job``; this module builds the ``Job.fn``
closure it runs when due -- opening a fresh database session per firing
(the scheduler's own callback has no request-scoped session) and
delegating to
:class:`~app.services.dispatch.AlertDispatchService.advance_escalations`,
the same "framework fires the callback, this service owns the session
lifecycle" split ``services/monitoring-service``'s own scheduled-job
closures already established.

The pass is organization-scoped and driven from the alerts actually
open, so an organization with nothing outstanding costs one cheap
query rather than a per-alert scheduled job each.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.factory import DatabaseFramework
from shared_core.database.session import session_scope
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager
from shared_core.scheduler import Job, JobFn
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.alert_notifications import AlertNotificationService
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.repositories.alert_notification import AlertNotificationRepository
from app.repositories.alert_oncall_schedule import AlertOnCallScheduleRepository
from app.repositories.alert_route import AlertRouteRepository
from app.services.alert import AlertService
from app.services.dispatch import AlertDispatchService
from app.services.escalation import AlertEscalationPolicyService
from app.services.oncall import AlertOnCallScheduleService
from app.services.route import AlertRouteService
from app.types import EventPublisher

logger = get_logger("app.workers.escalation_worker")


def build_dispatch_service(
    session: AsyncSession,
    manager: NotificationManager,
    publish_event: EventPublisher,
) -> AlertDispatchService:
    """Assemble a fully-wired :class:`AlertDispatchService` on *session*.

    Exposed separately from :func:`build_escalation_job_fn` so both the
    scheduled worker and the API layer build it the same way.
    """
    return AlertDispatchService(
        AlertService(AlertInstanceRepository(session), AlertHistoryRepository(session)),
        AlertInstanceRepository(session),
        AlertRouteService(AlertRouteRepository(session)),
        AlertEscalationPolicyService(AlertEscalationPolicyRepository(session)),
        AlertOnCallScheduleService(AlertOnCallScheduleRepository(session)),
        AlertNotificationService(
            AlertNotificationRepository(session), manager, publish_event=publish_event
        ),
        publish_event=publish_event,
    )


def build_escalation_job_fn(
    organization_id: UUID,
    database: DatabaseFramework,
    manager: NotificationManager,
    publish_event: EventPublisher,
) -> JobFn:
    """Bind *organization_id* into the ``shared_core.scheduler.JobFn`` shape
    :func:`~app.scheduling.registrar.register_escalation_pass` needs.
    """

    async def _run(_job: Job) -> None:
        async with session_scope(database.session_factory) as session:
            service = build_dispatch_service(session, manager, publish_event)
            try:
                advanced = await service.advance_escalations(organization_id)
            except Exception:
                logger.exception(
                    "Scheduled escalation pass failed.",
                    extra={"extra_fields": {"organization_id": str(organization_id)}},
                )
                raise
            if advanced:
                logger.info(
                    "Escalation pass advanced alerts.",
                    extra={
                        "extra_fields": {
                            "organization_id": str(organization_id),
                            "advanced": advanced,
                        }
                    },
                )

    return _run


__all__ = ["build_dispatch_service", "build_escalation_job_fn"]

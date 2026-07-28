"""Background worker: scheduled collector/synthetic-test dispatch
("PERFORMANCE": Distributed Collectors, Async Processing, Horizontal
Scaling).

``app/scheduling/registrar.py`` registers one
``shared_core.scheduler.Job`` per active
:class:`~app.models.monitoring_collector.MonitoringCollector`/
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`;
this module builds the actual ``Job.fn`` closures those registrations
run when a job comes due -- opening a fresh database session per firing
(the scheduler's own callback has no request-scoped session of its
own) and delegating to
:class:`~app.services.collection.MonitoringCollectionService`/
:class:`~app.services.synthetic_execution
.MonitoringSyntheticExecutionService`, the same "framework fires the
callback, this service owns the session lifecycle" split
``services/workflow-runtime-service``'s own scheduled-job closures
already established.
"""

from __future__ import annotations

from shared_core.database.factory import DatabaseFramework
from shared_core.database.session import session_scope
from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job, JobFn

from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.repositories.monitoring_rule import MonitoringRuleRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.repositories.monitoring_threshold import MonitoringThresholdRepository
from app.services.availability import MonitoringAvailabilityService
from app.services.collection import EventPublisher, MonitoringCollectionService
from app.services.health import MonitoringHealthService
from app.services.metric import MonitoringMetricService
from app.services.metric_series import MonitoringMetricSeriesService
from app.services.synthetic_execution import MonitoringSyntheticExecutionService
from app.services.target import MonitoringTargetService

logger = get_logger("app.workers.collection_worker")


def build_collector_job_fn(
    collector: MonitoringCollector,
    database: DatabaseFramework,
    registry: CollectorRegistry,
    context: CollectorContext,
    publish_event: EventPublisher,
) -> JobFn:
    """Bind *collector* into the ``shared_core.scheduler.JobFn`` shape
    :func:`~app.scheduling.registrar.register_collector` needs.
    """

    async def _run(_job: Job) -> None:
        async with session_scope(database.session_factory) as session:
            targets_repo = MonitoringTargetRepository(session)
            all_targets = await targets_repo.list_for_org(collector.organization_id)
            matching = [
                target
                for target in all_targets
                if not collector.target_types or str(target.target_type) in collector.target_types
            ]
            if not matching:
                return
            service = MonitoringCollectionService(
                MonitoringMetricRepository(session),
                MonitoringThresholdRepository(session),
                MonitoringRuleRepository(session),
                MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(session)),
                MonitoringHealthService(MonitoringHealthRepository(session)),
                MonitoringAvailabilityService(MonitoringAvailabilityRepository(session)),
                registry,
                context,
                publish_event=publish_event,
            )
            try:
                await service.run_collector(collector, matching)
            except Exception:
                logger.exception(
                    "Scheduled collector run failed.",
                    extra={"extra_fields": {"collector_id": str(collector.id)}},
                )
                raise

    return _run


def build_synthetic_test_job_fn(
    test: MonitoringSyntheticTest,
    database: DatabaseFramework,
    context: CollectorContext,
    publish_event: EventPublisher,
) -> JobFn:
    """Bind *test* into the ``shared_core.scheduler.JobFn`` shape
    :func:`~app.scheduling.registrar.register_synthetic_test` needs.
    """

    async def _run(_job: Job) -> None:
        async with session_scope(database.session_factory) as session:
            target = None
            if test.target_id is not None:
                target = await MonitoringTargetRepository(session).get_by_id(test.target_id)
            service = MonitoringSyntheticExecutionService(
                MonitoringHealthService(MonitoringHealthRepository(session)),
                MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(session)),
                MonitoringMetricService(MonitoringMetricRepository(session)),
                MonitoringTargetService(MonitoringTargetRepository(session)),
                context,
                publish_event=publish_event,
            )
            try:
                await service.run(test, target)
            except Exception:
                logger.exception(
                    "Scheduled synthetic test run failed.",
                    extra={"extra_fields": {"synthetic_test_id": str(test.id)}},
                )
                raise

    return _run


__all__ = ["build_collector_job_fn", "build_synthetic_test_job_fn"]

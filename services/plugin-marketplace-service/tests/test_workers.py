"""Tests for the four background sweep workers and their registrar.

Every test's own "due" work is created **only** through the real
service layer (``plugin_service``/``installation_service``/
``marketplace_service``/``review_service``) -- never by hand-inserting a
row that is already in whatever state a worker's own sweep query
filters on. That is the one bug class this file exists to catch: a
sweep query that never actually discovers freshly-created work because
the row was created through a path that never made it eligible for the
sweep's own query, even though every other test (built on hand-crafted
"already due" fixtures) would pass.

A few tests reach for the private ``_probe_one``/``_approve_one``
method, or a repository-level soft-delete/session-factory wrapper, to
exercise a worker's own per-item failure isolation (the "one session
per X" guarantee each worker module's own docstring documents) --
real Postgres throughout, never a faked response, just a genuine
race/conflict/dropped-connection forced at a precise point.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.dependency import DependencyGraph
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.manager import SchedulerManager
from shared_core.scheduler.registry import JobRegistry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import MarketplaceListingStatus, PluginInstallationStatus, PluginLifecycleStatus
from app.repositories.governance import PluginStatisticRepository
from app.repositories.health import PluginHealthRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.marketplace import PluginMarketplaceRepository
from app.repositories.plugin import PluginRepository
from app.repositories.review import PluginRatingRepository
from app.services.installation import PluginInstallationService
from app.services.marketplace import PluginMarketplaceService
from app.services.plugin import PluginService
from app.services.review import PluginReviewService
from app.workers import registrar
from app.workers.health_probe_sweep import HealthProbeSweepWorker
from app.workers.marketplace_approval_sweep import MarketplaceApprovalSweepWorker
from app.workers.review_moderation_sweep import ReviewModerationSweepWorker
from app.workers.statistics_rollup import StatisticsRollupWorker
from tests.conftest import REACHABLE_HTTP_URL, UNREACHABLE_HTTP_URL, RecordingPublisher

# ---- shared helpers ---------------------------------------------------------


def _checksummed_manifest(*, version: str = "1.0.0") -> dict[str, Any]:
    """A minimal, structurally-valid manifest -- same shape as ``test_smoke.py``."""
    manifest: dict[str, Any] = {
        "name": "Worker Test Plugin",
        "publisher": "worker-tests",
        "category": "utilities",
        "type": "custom_plugin",
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["checksum"] = hashlib.sha256(canonical).hexdigest()
    return manifest


async def _register_and_publish(
    plugin_service: PluginService,
    organization_id: uuid.UUID,
    *,
    slug: str,
    version: str = "1.0.0",
) -> Any:
    """Register a plugin, submit a valid manifest, and publish it -- entirely
    through ``PluginService``, the same lifecycle ``test_smoke.py`` drives
    over HTTP.
    """
    plugin = await plugin_service.register(
        organization_id,
        slug=slug,
        name=f"Worker test: {slug}",
        category="utilities",
        plugin_type="custom_plugin",
    )
    await plugin_service.submit_manifest(
        organization_id,
        plugin.id,
        version_number=version,
        manifest=_checksummed_manifest(version=version),
    )
    return await plugin_service.publish(organization_id, plugin.id, version_number=version)


async def _install_configure_activate(
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
    plugin_id: uuid.UUID,
    *,
    health_check_url: str | None = None,
) -> Any:
    """Install a published plugin and bring it to ``ACTIVE`` -- configuring
    *before* activating, since ``configure()`` itself sets the installation
    back to ``CONFIGURED`` (not ``ACTIVE``); only ``activate()`` produces the
    ``ACTIVE`` status the health-probe sweep's own query filters on.
    """
    installation = await installation_service.install(organization_id, plugin_id)
    if health_check_url is not None:
        installation = await installation_service.configure(
            organization_id,
            installation.id,
            configuration={"health_check_url": health_check_url},
        )
    return await installation_service.activate(organization_id, installation.id)


class _DropsConnectionOnce:
    """Wraps a real ``session_factory``, raising once on a chosen call.

    Every other call passes straight through to the real, live database --
    this never fabricates a query result. It exists only to force one
    specific organization's own rollup to fail with a genuine exception
    (simulating a dropped connection) so ``StatisticsRollupWorker``'s own
    documented guarantee -- "a failure on one tenant must not poison the
    transaction the next one needs" -- can be proven against a real
    failure, not just the happy path.
    """

    def __init__(
        self, real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
    ) -> None:
        self._real_factory = real_factory
        self._fail_on_call = fail_on_call
        self._calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        self._calls += 1
        if self._calls == self._fail_on_call:
            raise RuntimeError("Simulated dropped connection.")
        return self._real_factory(*args, **kwargs)


async def _noop_job(_job: object) -> None:
    """A throwaway ``JobFn`` for registrar tests that never actually runs."""


# ============================================================================
# HealthProbeSweepWorker
# ============================================================================


async def test_tick_discovers_and_probes_a_freshly_activated_installation(
    db_session_factory: Any,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="health-happy")
    installation = await _install_configure_activate(
        installation_service, organization_id, plugin.id, health_check_url=REACHABLE_HTTP_URL
    )
    assert installation.status == PluginInstallationStatus.ACTIVE

    worker = HealthProbeSweepWorker(
        session_factory=db_session_factory,
        timeout_seconds=5.0,
        failure_threshold=3,
        publish_event=publisher,
    )
    probed = await worker.tick()
    assert probed == 1

    async with db_session_factory() as session:
        latest = await PluginHealthRepository(session).get_latest(installation.id)
    assert latest is not None
    assert latest.status == HealthStatus.HEALTHY
    assert latest.consecutive_failures == 0
    assert latest.recovery_attempted is False


async def test_tick_skips_an_installation_that_was_never_activated(
    db_session_factory: Any,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="health-inactive")
    installation = await installation_service.install(organization_id, plugin.id)
    assert installation.status == PluginInstallationStatus.INSTALLED

    worker = HealthProbeSweepWorker(
        session_factory=db_session_factory, timeout_seconds=5.0, failure_threshold=3
    )
    probed = await worker.tick()
    assert probed == 0

    async with db_session_factory() as session:
        latest = await PluginHealthRepository(session).get_latest(installation.id)
    assert latest is None


async def test_tick_flips_recovery_attempted_and_publishes_health_changed_event(
    db_session_factory: Any,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="health-unreachable")
    installation = await _install_configure_activate(
        installation_service, organization_id, plugin.id, health_check_url=UNREACHABLE_HTTP_URL
    )

    worker = HealthProbeSweepWorker(
        session_factory=db_session_factory,
        timeout_seconds=2.0,
        failure_threshold=2,
        publish_event=publisher,
    )

    # First tick: consecutive_failures becomes 1, below the threshold --
    # no recovery attempted yet, no health-changed event.
    probed_first = await worker.tick()
    assert probed_first == 1
    assert "PluginHealthChanged" not in publisher.names

    # Second tick: the running streak (carried forward from the previous
    # probe row) crosses the failure_threshold=2 -- recovery_attempted
    # flips true and the event publishes.
    probed_second = await worker.tick()
    assert probed_second == 1
    assert publisher.names.count("PluginHealthChanged") == 1

    async with db_session_factory() as session:
        latest = await PluginHealthRepository(session).get_latest(installation.id)
    assert latest is not None
    assert latest.status == HealthStatus.UNHEALTHY
    assert latest.consecutive_failures == 2
    assert latest.recovery_attempted is True

    event = next(e for e in publisher.events if e.event_name == "PluginHealthChanged")
    assert event.payload["installation_id"] == str(installation.id)
    assert event.payload["recovery_attempted"] is True


async def test_probe_one_isolates_a_failure_without_crashing_the_sweep(
    db_session_factory: Any,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    """An installation that vanishes between being listed as due and being
    probed (a genuine race, simulated here with a direct repository
    soft-delete -- installations expose no such operation at the service
    layer) must not crash the rest of the sweep.
    """
    plugin = await _register_and_publish(plugin_service, organization_id, slug="health-vanishes")
    installation = await _install_configure_activate(
        installation_service, organization_id, plugin.id, health_check_url=REACHABLE_HTTP_URL
    )

    async with db_session_factory() as session:
        await PluginInstallationRepository(session).delete(installation.id)
        await session.commit()

    worker = HealthProbeSweepWorker(
        session_factory=db_session_factory, timeout_seconds=5.0, failure_threshold=3
    )
    probed_ok = await worker._probe_one(installation.id)
    assert probed_ok is False


async def test_health_probe_run_job_delegates_to_tick(
    db_session_factory: Any,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="health-run-job")
    installation = await _install_configure_activate(
        installation_service, organization_id, plugin.id, health_check_url=REACHABLE_HTTP_URL
    )

    worker = HealthProbeSweepWorker(
        session_factory=db_session_factory, timeout_seconds=5.0, failure_threshold=3
    )
    result = await worker.run_job(object())
    assert result is None

    async with db_session_factory() as session:
        latest = await PluginHealthRepository(session).get_latest(installation.id)
    assert latest is not None


# ============================================================================
# MarketplaceApprovalSweepWorker
# ============================================================================


async def test_tick_auto_approves_a_draft_listing_for_a_published_plugin(
    db_session_factory: Any,
    plugin_service: PluginService,
    marketplace_service: PluginMarketplaceService,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="mkt-happy")
    assert plugin.status == PluginLifecycleStatus.PUBLISHED

    listing = await marketplace_service.create_listing(
        organization_id, plugin.id, search_keywords=["worker-test"]
    )
    assert listing.status == MarketplaceListingStatus.DRAFT

    worker = MarketplaceApprovalSweepWorker(session_factory=db_session_factory, publish_event=publisher)
    approved = await worker.tick()
    assert approved == 1

    async with db_session_factory() as session:
        entry = await PluginMarketplaceRepository(session).require_by_id(listing.id)
    assert entry.status == MarketplaceListingStatus.PUBLISHED
    assert entry.approved_by == "system-sweep"
    assert entry.approved_at is not None
    assert "MarketplaceUpdated" in publisher.names


async def test_tick_skips_a_draft_listing_whose_plugin_was_never_published(
    db_session_factory: Any,
    plugin_service: PluginService,
    marketplace_service: PluginMarketplaceService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await plugin_service.register(
        organization_id,
        slug="mkt-unpublished",
        name="Unpublished",
        category="utilities",
        plugin_type="custom_plugin",
    )
    assert plugin.status == PluginLifecycleStatus.REGISTERED

    listing = await marketplace_service.create_listing(organization_id, plugin.id)
    assert listing.status == MarketplaceListingStatus.DRAFT

    worker = MarketplaceApprovalSweepWorker(session_factory=db_session_factory)
    approved = await worker.tick()
    assert approved == 0

    async with db_session_factory() as session:
        entry = await PluginMarketplaceRepository(session).require_by_id(listing.id)
    assert entry.status == MarketplaceListingStatus.DRAFT


async def test_approve_one_isolates_a_failure_without_crashing_the_sweep(
    db_session_factory: Any,
    plugin_service: PluginService,
    marketplace_service: PluginMarketplaceService,
    organization_id: uuid.UUID,
) -> None:
    """A listing whose own plugin vanishes between being listed as due and
    being approved (simulated with a direct repository soft-delete of the
    plugin) must not crash the rest of the sweep.
    """
    plugin = await _register_and_publish(plugin_service, organization_id, slug="mkt-vanishes")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)

    async with db_session_factory() as session:
        await PluginRepository(session).delete(plugin.id)
        await session.commit()

    worker = MarketplaceApprovalSweepWorker(session_factory=db_session_factory)
    approved_ok = await worker._approve_one(listing.id)
    assert approved_ok is False


async def test_marketplace_approval_run_job_delegates_to_tick(
    db_session_factory: Any,
    plugin_service: PluginService,
    marketplace_service: PluginMarketplaceService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _register_and_publish(plugin_service, organization_id, slug="mkt-run-job")
    listing = await marketplace_service.create_listing(organization_id, plugin.id)

    worker = MarketplaceApprovalSweepWorker(session_factory=db_session_factory)
    result = await worker.run_job(object())
    assert result is None

    async with db_session_factory() as session:
        entry = await PluginMarketplaceRepository(session).require_by_id(listing.id)
    assert entry.status == MarketplaceListingStatus.PUBLISHED


# ============================================================================
# StatisticsRollupWorker
# ============================================================================


async def test_tick_recomputes_statistics_for_an_organization_with_a_plugin(
    db_session_factory: Any, plugin_service: PluginService, organization_id: uuid.UUID
) -> None:
    await plugin_service.register(
        organization_id,
        slug="stats-plugin",
        name="Stats Plugin",
        category="utilities",
        plugin_type="custom_plugin",
    )

    worker = StatisticsRollupWorker(session_factory=db_session_factory, window_seconds=3600)
    done = await worker.tick()
    assert done >= 1

    async with db_session_factory() as session:
        latest = await PluginStatisticRepository(session).latest(organization_id)
    assert latest is not None
    assert latest.plugins_published >= 1


async def test_tick_isolates_one_organizations_own_rollup_failure(
    db_session_factory: Any, plugin_service: PluginService
) -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    await plugin_service.register(
        org_a, slug="rollup-a", name="A", category="utilities", plugin_type="custom_plugin"
    )
    await plugin_service.register(
        org_b, slug="rollup-b", name="B", category="utilities", plugin_type="custom_plugin"
    )

    # Call 1 is `_organizations()`'s own query; calls 2 and 3 are the two
    # discovered organizations' own `_recompute` -- fail the second one.
    flaky_factory = _DropsConnectionOnce(db_session_factory, fail_on_call=3)
    worker = StatisticsRollupWorker(session_factory=flaky_factory, window_seconds=3600)  # type: ignore[arg-type]

    done = await worker.tick()
    assert done == 1


async def test_statistics_rollup_run_job_delegates_to_tick(
    db_session_factory: Any, plugin_service: PluginService, organization_id: uuid.UUID
) -> None:
    await plugin_service.register(
        organization_id,
        slug="stats-run-job",
        name="Stats Run Job",
        category="utilities",
        plugin_type="custom_plugin",
    )

    worker = StatisticsRollupWorker(session_factory=db_session_factory, window_seconds=3600)
    result = await worker.run_job(object())
    assert result is None

    async with db_session_factory() as session:
        latest = await PluginStatisticRepository(session).latest(organization_id)
    assert latest is not None


# ============================================================================
# ReviewModerationSweepWorker
# ============================================================================


async def test_tick_recomputes_rating_aggregate_from_submitted_reviews(
    db_session_factory: Any,
    plugin_service: PluginService,
    review_service: PluginReviewService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await plugin_service.register(
        organization_id,
        slug="review-plugin",
        name="Review Plugin",
        category="utilities",
        plugin_type="custom_plugin",
    )
    await review_service.submit(
        organization_id, plugin.id, reviewer_id="reviewer-1", rating=5, body="Great."
    )
    await review_service.submit(
        organization_id, plugin.id, reviewer_id="reviewer-2", rating=3, body="Fine."
    )
    await review_service.submit(
        organization_id, plugin.id, reviewer_id="reviewer-3", rating=4, body="Good."
    )

    worker = ReviewModerationSweepWorker(session_factory=db_session_factory)
    recomputed = await worker.tick()
    assert recomputed == 1

    async with db_session_factory() as session:
        rating = await PluginRatingRepository(session).get_for_plugin(plugin.id)
    assert rating is not None
    assert rating.review_count == 3
    assert rating.average_rating == pytest.approx((5 + 3 + 4) / 3)
    assert rating.rating_5_count == 1
    assert rating.rating_4_count == 1
    assert rating.rating_3_count == 1


async def test_tick_completes_normally_with_a_flagged_review_pending_moderation(
    db_session_factory: Any,
    plugin_service: PluginService,
    review_service: PluginReviewService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await plugin_service.register(
        organization_id,
        slug="review-flagged",
        name="Review Flagged",
        category="utilities",
        plugin_type="custom_plugin",
    )
    review = await review_service.submit(
        organization_id, plugin.id, reviewer_id="reviewer-1", rating=1, body="Spam-ish."
    )
    await review_service.flag(review.id, reason="suspected spam")

    worker = ReviewModerationSweepWorker(session_factory=db_session_factory)
    # Must not raise -- the flagged-review queue depth is only logged, not
    # returned, so completing normally is the whole assertion.
    recomputed = await worker.tick()
    assert recomputed == 1


async def test_recompute_one_isolates_a_failure_without_crashing_the_sweep(
    db_session_factory: Any,
    plugin_service: PluginService,
    review_service: PluginReviewService,
    organization_id: uuid.UUID,
) -> None:
    """Soft-deleting the existing rating aggregate (bypassing the service
    layer, which exposes no such operation) forces ``recompute_rating``'s
    own re-``create`` to collide with the still-present row on
    ``plugin_ratings``'s own ``UniqueConstraint("plugin_id")`` -- a genuine
    Postgres integrity conflict, proving the per-plugin isolation promise
    against a real database error rather than a synthetic one.
    """
    plugin = await plugin_service.register(
        organization_id,
        slug="review-conflict",
        name="Review Conflict",
        category="utilities",
        plugin_type="custom_plugin",
    )
    await review_service.submit(organization_id, plugin.id, reviewer_id="reviewer-1", rating=5)
    rating = await review_service.get_rating(plugin.id)
    assert rating is not None

    async with db_session_factory() as session:
        await PluginRatingRepository(session).delete(rating.id)
        await session.commit()

    worker = ReviewModerationSweepWorker(session_factory=db_session_factory)
    recomputed_ok = await worker._recompute_one(plugin.id)
    assert recomputed_ok is False


async def test_review_moderation_run_job_delegates_to_tick(
    db_session_factory: Any,
    plugin_service: PluginService,
    review_service: PluginReviewService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await plugin_service.register(
        organization_id,
        slug="review-run-job",
        name="Review Run Job",
        category="utilities",
        plugin_type="custom_plugin",
    )
    await review_service.submit(organization_id, plugin.id, reviewer_id="reviewer-1", rating=5)

    worker = ReviewModerationSweepWorker(session_factory=db_session_factory)
    result = await worker.run_job(object())
    assert result is None

    async with db_session_factory() as session:
        rating = await PluginRatingRepository(session).get_for_plugin(plugin.id)
    assert rating is not None


# ============================================================================
# registrar
# ============================================================================


class _StubExecutor:
    """Satisfies ``Worker.__init__``'s attribute access on construction.

    Never actually invoked -- these registrar tests only exercise job
    *registration* (:meth:`SchedulerManager.register_job`, purely
    in-process: a registry dict write plus computing the first due time),
    never dispatch or execution, so a real ``JobExecutor`` wired to
    Redis is not needed.
    """

    execute = None


@pytest.fixture
def scheduler_manager() -> SchedulerManager:
    """A real, fully in-process ``SchedulerManager`` -- no Redis/RabbitMQ.

    ``register_job`` only touches ``registry``/``engine`` (see
    ``SchedulerManager.register_job``), so a real one can be built and
    used for genuine registration assertions without any infrastructure
    at all.
    """
    registry = JobRegistry()
    engine = SchedulerEngine(registry, DependencyGraph())
    return SchedulerManager(registry, engine, object(), _StubExecutor())


_REGISTER_FUNCTIONS = [
    (registrar.register_health_probe_sweep, registrar.HEALTH_PROBE_SWEEP_JOB_ID),
    (registrar.register_marketplace_approval_sweep, registrar.MARKETPLACE_APPROVAL_SWEEP_JOB_ID),
    (registrar.register_statistics_rollup, registrar.STATISTICS_ROLLUP_JOB_ID),
    (registrar.register_review_moderation_sweep, registrar.REVIEW_MODERATION_SWEEP_JOB_ID),
]


@pytest.mark.parametrize(("register_fn", "job_id"), _REGISTER_FUNCTIONS)
def test_register_rejects_a_zero_interval(
    register_fn: Any, job_id: str, scheduler_manager: SchedulerManager
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        register_fn(scheduler_manager, _noop_job, interval_seconds=0)


@pytest.mark.parametrize(("register_fn", "job_id"), _REGISTER_FUNCTIONS)
def test_register_rejects_a_negative_interval(
    register_fn: Any, job_id: str, scheduler_manager: SchedulerManager
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        register_fn(scheduler_manager, _noop_job, interval_seconds=-30)


@pytest.mark.parametrize(("register_fn", "job_id"), _REGISTER_FUNCTIONS)
def test_register_schedules_a_fixed_rate_job(
    register_fn: Any, job_id: str, scheduler_manager: SchedulerManager
) -> None:
    job = register_fn(scheduler_manager, _noop_job, interval_seconds=45)
    assert job.job_id == job_id
    assert job.status == JobStatus.SCHEDULED
    assert job.next_run is not None
    assert job.schedule.interval == timedelta(seconds=45)
    assert job.fn is _noop_job

    # Registered against the manager's own registry, not just returned --
    # a second lookup must see the same job.
    assert scheduler_manager.registry.get(job_id).job_id == job_id


def test_job_ids_are_distinct_and_non_empty() -> None:
    ids = {
        registrar.HEALTH_PROBE_SWEEP_JOB_ID,
        registrar.MARKETPLACE_APPROVAL_SWEEP_JOB_ID,
        registrar.STATISTICS_ROLLUP_JOB_ID,
        registrar.REVIEW_MODERATION_SWEEP_JOB_ID,
    }
    assert len(ids) == 4
    assert all(isinstance(job_id, str) and job_id for job_id in ids)

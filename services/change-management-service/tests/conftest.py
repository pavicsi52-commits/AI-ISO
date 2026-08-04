"""Test fixtures for the change management service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ. Nothing
here mocks infrastructure: the notification service is a real manager
with no channel registered, the event publisher is a real awaitable that
records, and the app fixture starts the actual lifespan.

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it.

Concretely: ``AuditService.record_failure`` commits in its own
``session_scope`` precisely so a refused request's audit entry survives
the rollback of the request that raised. Under a SAVEPOINT that
distinction vanishes and the test passes whether the code is right or
wrong -- the same reasoning Prompt 052's own conftest documents. That
path is therefore exercised at service level against the real session
factory, never over HTTP.

Where a test's isolation differs from production's, the test is only
trustworthy about things that isolation does not touch.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""IPv4, never "localhost".

Docker Desktop's IPv6 loopback does not reach the published ports, so a
name that resolves to ``::1`` first makes every connection hang until it
times out rather than failing fast.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_change_management")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "26")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_change_management_test_keys"
_TEST_KEY_DIR.mkdir(parents=True, exist_ok=True)
_TEST_PRIVATE_KEY_PATH = _TEST_KEY_DIR / "private.pem"
_TEST_PUBLIC_KEY_PATH = _TEST_KEY_DIR / "public.pem"

if not _TEST_PRIVATE_KEY_PATH.is_file():
    _private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _TEST_PRIVATE_KEY_PATH.write_text(
        _private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii"),
        encoding="ascii",
    )
    _TEST_PUBLIC_KEY_PATH.write_text(
        _private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii"),
        encoding="ascii",
    )

os.environ.setdefault(
    "AIIOS_CHANGE_MANAGEMENT_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault("AIIOS_CHANGE_MANAGEMENT_SERVICE_SCHEDULER_ENABLED", "false")

from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.notifications.factory import create_notification_framework  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ApprovalPolicy,
    ApprovalStatus,
    CabVote,
    CalendarEntryKind,
    ChangeCategory,
    ChangePriority,
    ChangeType,
    RiskImpact,
    RiskLikelihood,
)
from app.notifications.change_notifications import ChangeNotificationService  # noqa: E402
from app.repositories.approval import ChangeApprovalRepository  # noqa: E402
from app.repositories.cab import ChangeCabRepository, ChangeCabVoteRepository  # noqa: E402
from app.repositories.calendar import ChangeCalendarRepository  # noqa: E402
from app.repositories.catalogue import (  # noqa: E402
    ChangeCategoryRepository,
    ChangePriorityRepository,
    ChangeStatusRepository,
    ChangeTypeRepository,
)
from app.repositories.change import (  # noqa: E402
    ChangeRelationshipRepository,
    ChangeRequestRepository,
)
from app.repositories.conflict import ChangeConflictRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    ChangeAuditRepository,
    ChangeReportRepository,
    ChangeStatisticRepository,
)
from app.repositories.implementation import (  # noqa: E402
    ChangeImplementationRepository,
    ChangeRollbackRepository,
    ChangeTaskRepository,
    ChangeValidationRepository,
)
from app.repositories.pir import (  # noqa: E402
    ChangePostReviewActionItemRepository,
    ChangePostReviewRepository,
)
from app.repositories.risk import ChangeRiskAssessmentRepository  # noqa: E402
from app.risk.engine import RiskDimensions  # noqa: E402
from app.services.approval import ApprovalService  # noqa: E402
from app.services.cab import CabService  # noqa: E402
from app.services.calendar import CalendarService  # noqa: E402
from app.services.change import ChangeService  # noqa: E402
from app.services.conflict import ConflictService  # noqa: E402
from app.services.implementation import ImplementationService  # noqa: E402
from app.services.pir import PirService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.risk import RiskService  # noqa: E402
from app.services.rollback import RollbackService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_change_management",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 26 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=26,
        _env_file=None,
    )


def rabbitmq_test_settings() -> RabbitMQSettings:
    """The broker the scheduler's job queue runs on."""
    return RabbitMQSettings(
        rabbitmq_host=_LOOPBACK,
        rabbitmq_port=5672,
        rabbitmq_user="aiios",
        rabbitmq_password="change-me",
        rabbitmq_vhost="/aiios",
        _env_file=None,
    )


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_test_settings())
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    pg_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory on one per-test SAVEPOINT-isolated connection."""
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        yield async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await trans.rollback()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One SAVEPOINT-isolated session per test, always rolled back."""
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def organization_id() -> uuid.UUID:
    """A fresh organization id per test.

    Every test works inside its own tenant, which means every test is
    also, incidentally, a tenant-isolation test: a query that forgot its
    ``organization_id`` filter would see the other tests' rows.
    """
    return uuid.uuid4()


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


AuthHeadersFn = Callable[[uuid.UUID], dict[str, str]]


@pytest.fixture
def auth_headers(jwt_keypair: tuple[str, str]) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user id."""
    private_key, _public_key = jwt_keypair

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        token = encode_token({"sub": str(user_id)}, private_key=private_key)
        return {"Authorization": f"Bearer {token}"}

    return _headers


class RecordingPublisher:
    """A real :data:`~app.types.EventPublisher` that records.

    Not a mock: an awaitable callable with the right signature, so the
    publish path executes for real and a test can assert exactly which
    domain events a flow announced.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def __call__(self, event: Any) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        """The ``event_name`` of every event published, in order."""
        return [event.event_name for event in self.events]


@pytest.fixture
def publisher() -> RecordingPublisher:
    """A recording event publisher."""
    return RecordingPublisher()


@pytest.fixture
def notifications() -> ChangeNotificationService:
    """A real notification service with no channels registered.

    Not a mock: the manager, router, dispatcher, and dead-letter store all
    run for real, and with no channel registered every send fails the way
    a misconfigured deployment's would. That is the path worth exercising,
    because every caller here is meant to survive it.
    """
    return ChangeNotificationService(create_notification_framework())


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def changes_repo(db_session: AsyncSession) -> ChangeRequestRepository:
    return ChangeRequestRepository(db_session)


@pytest.fixture
def relationships_repo(db_session: AsyncSession) -> ChangeRelationshipRepository:
    return ChangeRelationshipRepository(db_session)


@pytest.fixture
def risk_repo(db_session: AsyncSession) -> ChangeRiskAssessmentRepository:
    return ChangeRiskAssessmentRepository(db_session)


@pytest.fixture
def approvals_repo(db_session: AsyncSession) -> ChangeApprovalRepository:
    return ChangeApprovalRepository(db_session)


@pytest.fixture
def cab_repo(db_session: AsyncSession) -> ChangeCabRepository:
    return ChangeCabRepository(db_session)


@pytest.fixture
def cab_votes_repo(db_session: AsyncSession) -> ChangeCabVoteRepository:
    return ChangeCabVoteRepository(db_session)


@pytest.fixture
def calendar_repo(db_session: AsyncSession) -> ChangeCalendarRepository:
    return ChangeCalendarRepository(db_session)


@pytest.fixture
def conflicts_repo(db_session: AsyncSession) -> ChangeConflictRepository:
    return ChangeConflictRepository(db_session)


@pytest.fixture
def tasks_repo(db_session: AsyncSession) -> ChangeTaskRepository:
    return ChangeTaskRepository(db_session)


@pytest.fixture
def implementations_repo(db_session: AsyncSession) -> ChangeImplementationRepository:
    return ChangeImplementationRepository(db_session)


@pytest.fixture
def validations_repo(db_session: AsyncSession) -> ChangeValidationRepository:
    return ChangeValidationRepository(db_session)


@pytest.fixture
def rollbacks_repo(db_session: AsyncSession) -> ChangeRollbackRepository:
    return ChangeRollbackRepository(db_session)


@pytest.fixture
def pir_repo(db_session: AsyncSession) -> ChangePostReviewRepository:
    return ChangePostReviewRepository(db_session)


@pytest.fixture
def pir_action_items_repo(db_session: AsyncSession) -> ChangePostReviewActionItemRepository:
    return ChangePostReviewActionItemRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> ChangeStatisticRepository:
    return ChangeStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> ChangeReportRepository:
    return ChangeReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> ChangeAuditRepository:
    return ChangeAuditRepository(db_session)


@pytest.fixture
def categories_repo(db_session: AsyncSession) -> ChangeCategoryRepository:
    return ChangeCategoryRepository(db_session)


@pytest.fixture
def types_repo(db_session: AsyncSession) -> ChangeTypeRepository:
    return ChangeTypeRepository(db_session)


@pytest.fixture
def priorities_repo(db_session: AsyncSession) -> ChangePriorityRepository:
    return ChangePriorityRepository(db_session)


@pytest.fixture
def statuses_repo(db_session: AsyncSession) -> ChangeStatusRepository:
    return ChangeStatusRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def change_service(db_session: AsyncSession, publisher: RecordingPublisher) -> ChangeService:
    return ChangeService(
        ChangeRequestRepository(db_session),
        ChangeRelationshipRepository(db_session),
        ChangeCalendarRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def risk_service(db_session: AsyncSession, publisher: RecordingPublisher) -> RiskService:
    return RiskService(
        ChangeRiskAssessmentRepository(db_session),
        ChangeRequestRepository(db_session),
        publish_event=publisher,
        standard_change_requires_cab=False,
    )


@pytest.fixture
def approval_service(
    db_session: AsyncSession,
    notifications: ChangeNotificationService,
    publisher: RecordingPublisher,
) -> ApprovalService:
    return ApprovalService(
        ChangeApprovalRepository(db_session),
        ChangeRequestRepository(db_session),
        notifications,
        publish_event=publisher,
        minimum_approvals_high_risk=2,
    )


@pytest.fixture
def cab_service(
    db_session: AsyncSession,
    notifications: ChangeNotificationService,
    publisher: RecordingPublisher,
) -> CabService:
    return CabService(
        ChangeCabRepository(db_session),
        ChangeCabVoteRepository(db_session),
        ChangeRequestRepository(db_session),
        notifications,
        publish_event=publisher,
        quorum_fraction=0.5,
    )


@pytest.fixture
def calendar_service(db_session: AsyncSession) -> CalendarService:
    return CalendarService(ChangeCalendarRepository(db_session))


@pytest.fixture
def conflict_service(db_session: AsyncSession) -> ConflictService:
    return ConflictService(
        ChangeConflictRepository(db_session), ChangeRequestRepository(db_session), slack_hours=4
    )


@pytest.fixture
def implementation_service(
    db_session: AsyncSession,
    notifications: ChangeNotificationService,
    publisher: RecordingPublisher,
) -> ImplementationService:
    return ImplementationService(
        ChangeTaskRepository(db_session),
        ChangeImplementationRepository(db_session),
        ChangeValidationRepository(db_session),
        ChangeRequestRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def rollback_service(
    db_session: AsyncSession,
    notifications: ChangeNotificationService,
    publisher: RecordingPublisher,
) -> RollbackService:
    return RollbackService(
        ChangeRollbackRepository(db_session),
        ChangeRequestRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def pir_service(db_session: AsyncSession, publisher: RecordingPublisher) -> PirService:
    return PirService(
        ChangePostReviewRepository(db_session),
        ChangePostReviewActionItemRepository(db_session),
        ChangeRequestRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        ChangeStatisticRepository(db_session),
        ChangeRequestRepository(db_session),
        ChangeConflictRepository(db_session),
    )


@pytest.fixture
def report_service(
    db_session: AsyncSession, statistics_service: StatisticsService
) -> ReportService:
    return ReportService(
        ChangeReportRepository(db_session), ChangeRequestRepository(db_session), statistics_service
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(ChangeAuditRepository(db_session))


# ---- helpers --------------------------------------------------------------


MakeChangeFn = Callable[..., Any]


@pytest.fixture
def make_change(change_service: ChangeService, organization_id: uuid.UUID) -> MakeChangeFn:
    """Create one change request, in ``DRAFT``."""

    async def _make(
        title: str = "Patch the payments gateway",
        *,
        requester_id: str = "requester-1",
        category: ChangeCategory = ChangeCategory.APPLICATION,
        change_type: ChangeType = ChangeType.NORMAL,
        priority: ChangePriority = ChangePriority.MEDIUM,
        **kwargs: Any,
    ) -> Any:
        return await change_service.create(
            organization_id,
            title=title,
            requester_id=requester_id,
            category=category,
            change_type=change_type,
            priority=priority,
            **kwargs,
        )

    return _make


MakeAssessedChangeFn = Callable[..., Any]


@pytest.fixture
def make_assessed_change(
    make_change: MakeChangeFn,
    change_service: ChangeService,
    risk_service: RiskService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """Create a change, submit it, and run a risk assessment against it.

    Leaves it in ``PENDING_APPROVAL`` (or, for a dimension set severe
    enough to require CAB, still ``PENDING_APPROVAL`` -- ``cab_required``
    is a flag on the change, not a different status until an approval
    chain actually resolves).
    """

    async def _make(
        *,
        likelihood: RiskLikelihood = RiskLikelihood.POSSIBLE,
        dimensions: RiskDimensions | None = None,
        **change_kwargs: Any,
    ) -> Any:
        created = await make_change(**change_kwargs)
        change = await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            change.id,
            likelihood=likelihood,
            dimensions=dimensions
            or RiskDimensions(
                technical=RiskImpact.MINOR,
                business=RiskImpact.MINOR,
                operational=RiskImpact.MINOR,
                security=RiskImpact.MINOR,
                compliance=RiskImpact.MINOR,
                dependency=RiskImpact.MINOR,
            ),
        )
        return change

    return _make


@pytest.fixture
def make_approved_change(
    make_assessed_change: MakeAssessedChangeFn,
    approval_service: ApprovalService,
    change_service: ChangeService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """Assess (default: ``MEDIUM`` risk, CAB not required), then approve.

    A single approver, decided ``APPROVED``. Leaves the change
    ``PENDING_APPROVAL`` with ``approved_at`` set -- deciding an approval
    chain never advances a change's status by itself unless CAB is also
    required; ``ChangeService.schedule`` is the move that actually leaves
    ``PENDING_APPROVAL`` behind.
    """

    async def _make(**kwargs: Any) -> Any:
        change = await make_assessed_change(**kwargs)
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        return await change_service.get(organization_id, change.id)

    return _make


@pytest.fixture
def make_cab_review_change(
    make_assessed_change: MakeAssessedChangeFn,
    approval_service: ApprovalService,
    change_service: ChangeService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """Assess at ``CRITICAL`` risk (CAB required), then approve into ``CAB_REVIEW``."""

    async def _make(**kwargs: Any) -> Any:
        change = await make_assessed_change(
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            dimensions=RiskDimensions(
                technical=RiskImpact.SEVERE,
                business=RiskImpact.SEVERE,
                operational=RiskImpact.SEVERE,
                security=RiskImpact.SEVERE,
                compliance=RiskImpact.SEVERE,
                dependency=RiskImpact.SEVERE,
            ),
            **kwargs,
        )
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        return await change_service.get(organization_id, change.id)

    return _make


@pytest.fixture
def make_scheduled_change(
    make_approved_change: MakeAssessedChangeFn,
    change_service: ChangeService,
    calendar_service: CalendarService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """An approved change, booked into a fresh maintenance window."""

    async def _make(**kwargs: Any) -> Any:
        change = await make_approved_change(**kwargs)
        entry = await calendar_service.create_entry(
            organization_id,
            kind=CalendarEntryKind.MAINTENANCE_WINDOW,
            title="Test maintenance window",
            starts_at=soon(1),
            ends_at=soon(2),
        )
        return await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=entry.id,
            scheduled_start_at=soon(1),
            scheduled_end_at=soon(2),
        )

    return _make


@pytest.fixture
def make_ready_change(
    make_scheduled_change: MakeAssessedChangeFn,
    change_service: ChangeService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """A scheduled change marked ready to implement."""

    async def _make(**kwargs: Any) -> Any:
        change = await make_scheduled_change(**kwargs)
        return await change_service.mark_ready(organization_id, change.id)

    return _make


@pytest.fixture
def make_in_progress_change(
    make_ready_change: MakeAssessedChangeFn,
    implementation_service: ImplementationService,
    change_service: ChangeService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """A ready change with implementation started."""

    async def _make(**kwargs: Any) -> Any:
        change = await make_ready_change(**kwargs)
        await implementation_service.start(organization_id, change.id)
        return await change_service.get(organization_id, change.id)

    return _make


@pytest.fixture
def make_completed_change(
    make_in_progress_change: MakeAssessedChangeFn,
    implementation_service: ImplementationService,
    change_service: ChangeService,
    organization_id: uuid.UUID,
) -> MakeAssessedChangeFn:
    """An in-progress change with one task, validated, and completed."""

    async def _make(**kwargs: Any) -> Any:
        change = await make_in_progress_change(**kwargs)
        task = await implementation_service.add_task(
            organization_id, change.id, title="The only step"
        )
        await implementation_service.complete_task(organization_id, task.id)
        await implementation_service.move_to_validation(organization_id, change.id)
        await implementation_service.complete(organization_id, change.id)
        return await change_service.get(organization_id, change.id)

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, notifications, and key loading all run
    for real. Only the request session is overridden, so a test's writes
    roll back -- see this module's docstring for the one thing that
    override makes untestable here.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


def soon(hours: int = 4) -> datetime:
    """A moment *hours* in the future."""
    return datetime.now(UTC) + timedelta(hours=hours)


def ago(hours: int = 4) -> datetime:
    """A moment *hours* in the past."""
    return datetime.now(UTC) - timedelta(hours=hours)


__all__ = [
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_NOT_FOUND",
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "CabVote",
    "ago",
    "soon",
    "utcnow",
]

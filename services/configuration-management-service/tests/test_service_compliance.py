"""Tests for :class:`app.services.compliance.ConfigurationComplianceService`."""

from __future__ import annotations

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceEvalType, ComplianceStatus
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.compliance import ConfigurationComplianceService, EventPublisher
from tests.conftest import make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationComplianceService:
    return ConfigurationComplianceService(
        ConfigurationComplianceRepository(db_session),
        ConfigurationProfileRepository(db_session),
        publish_event=publish_event,
    )


async def test_evaluate_creates_evaluation_with_organization_id(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)

    evaluation = await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={"score": 100},
        exception_reason=None,
    )

    assert evaluation.organization_id == profile.organization_id
    assert evaluation.status == ComplianceStatus.COMPLIANT


async def test_evaluate_publishes_compliance_failed_on_non_compliant(
    db_session: AsyncSession,
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)

    await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.POLICY,
        status=ComplianceStatus.NON_COMPLIANT,
        details={},
        exception_reason=None,
    )

    assert any(event.event_name == "ComplianceFailed" for event in published)


async def test_evaluate_no_event_when_exception_reason_given(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)

    await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.BASELINE,
        status=ComplianceStatus.NON_COMPLIANT,
        details={},
        exception_reason="Approved exception ticket #123.",
    )

    assert not any(event.event_name == "ComplianceFailed" for event in published)


async def test_evaluate_no_event_when_compliant(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)

    await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.ENVIRONMENT,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )

    assert published == []


async def test_list_for_profile_filters_by_eval_type(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )
    await service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.INDUSTRY_STANDARDS,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )

    security_only = await service.list_for_profile(
        profile.id, eval_type=ComplianceEvalType.SECURITY
    )
    assert len(security_only) == 1
    assert security_only[0].eval_type == ComplianceEvalType.SECURITY

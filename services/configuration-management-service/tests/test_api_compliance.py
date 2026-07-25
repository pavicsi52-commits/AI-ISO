"""Tests for ``GET /configurations/compliance``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplianceEvalType, ComplianceStatus
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.compliance import ConfigurationComplianceService
from tests.conftest import AuthHeadersFn, make_profile


async def test_list_compliance_for_profile(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session)
    compliance_service = ConfigurationComplianceService(
        ConfigurationComplianceRepository(db_session), ConfigurationProfileRepository(db_session)
    )
    await compliance_service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )

    response = await client.get(
        "/configurations/compliance",
        params={"profile_id": str(profile.id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_list_compliance_filters_by_eval_type(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session)
    compliance_service = ConfigurationComplianceService(
        ConfigurationComplianceRepository(db_session), ConfigurationProfileRepository(db_session)
    )
    await compliance_service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.SECURITY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )
    await compliance_service.evaluate(
        profile_id=profile.id,
        eval_type=ComplianceEvalType.POLICY,
        status=ComplianceStatus.COMPLIANT,
        details={},
        exception_reason=None,
    )

    response = await client.get(
        "/configurations/compliance",
        params={"profile_id": str(profile.id), "eval_type": ComplianceEvalType.POLICY.value},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["eval_type"] == "policy"

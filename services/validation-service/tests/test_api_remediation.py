"""Tests for the ``/validation/remediation`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationResultStatus, ValidationSeverity
from app.models.validation_result import ValidationResult
from app.repositories.validation_failure import ValidationFailureRepository
from app.services.failure import ValidationFailureService
from tests.conftest import AuthHeadersFn, make_check, make_execution, make_profile, make_target


async def _make_failure(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    check = await make_check(db_session, organization_id=org_id)
    profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
    target = await make_target(db_session, organization_id=org_id)
    execution = await make_execution(db_session, profile, [target])
    result = ValidationResult(
        organization_id=org_id,
        execution_id=execution.id,
        target_id=target.id,
        check_id=check.id,
        check_type=check.check_type,
        status=ValidationResultStatus.FAILED,
    )
    db_session.add(result)
    await db_session.flush()
    failure = await ValidationFailureService(ValidationFailureRepository(db_session)).record(
        organization_id=org_id, result_id=result.id, severity=ValidationSeverity.HIGH, reason="r"
    )
    return org_id, failure.id


class TestRemediationApi:
    async def test_suggest_then_list(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id, failure_id = await _make_failure(db_session)

        suggested = await client.post(
            f"/validation/remediation/{failure_id}",
            params={
                "organization_id": str(org_id),
                "action_type": "recommended_fix",
                "description": "Free up disk space.",
            },
            headers=headers,
        )
        assert suggested.status_code == 201
        remediation_id = suggested.json()["data"]["id"]

        listed = await client.get(
            "/validation/remediation", params={"organization_id": str(org_id)}, headers=headers
        )
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

        applied = await client.post(
            f"/validation/remediation/{remediation_id}/apply", headers=headers
        )
        assert applied.status_code == 200
        assert applied.json()["data"]["is_applied"] is True

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/validation/remediation", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401

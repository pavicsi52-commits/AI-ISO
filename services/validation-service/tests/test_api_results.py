"""Tests for the ``/validation-results`` router, including its
``failures``/``exceptions`` actions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationResultStatus, ValidationSeverity
from app.models.validation_result import ValidationResult
from app.models.validation_score import ValidationScore
from app.repositories.validation_failure import ValidationFailureRepository
from app.services.failure import ValidationFailureService
from tests.conftest import AuthHeadersFn, make_check, make_execution, make_profile, make_target


class TestValidationResultsApi:
    async def test_list_by_execution_and_get(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
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
            status=ValidationResultStatus.PASSED,
        )
        db_session.add(result)
        await db_session.flush()

        list_response = await client.get(
            "/validation-results", params={"execution_id": str(execution.id)}, headers=headers
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1

        get_response = await client.get(f"/validation-results/{result.id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["data"]["status"] == "passed"

    async def test_list_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/validation-results", params={"execution_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401

    async def test_get_missing_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/validation-results/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404


class TestValidationFailuresAndExceptionsApi:
    async def _make_failure(self, db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
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
            organization_id=org_id,
            result_id=result.id,
            severity=ValidationSeverity.HIGH,
            reason="disk usage too high",
        )
        return result.id, failure.id

    async def test_list_result_failures(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        result_id, _failure_id = await self._make_failure(db_session)

        response = await client.get(f"/validation-results/{result_id}/failures", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_request_and_decide_exception(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        _result_id, failure_id = await self._make_failure(db_session)

        requested = await client.post(
            f"/validation-results/failures/{failure_id}/exceptions",
            json={"reason": "accepted risk"},
            headers=headers,
        )
        assert requested.status_code == 201
        exception_id = requested.json()["data"]["id"]

        listed = await client.get(
            f"/validation-results/failures/{failure_id}/exceptions", headers=headers
        )
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

        decided = await client.post(
            f"/validation-results/failures/{failure_id}/exceptions/{exception_id}/decide",
            json={"approve": True},
            headers=headers,
        )
        assert decided.status_code == 200
        assert decided.json()["data"]["status"] == "approved"


class TestValidationExecutionActionsApi:
    async def test_get_execution(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])

        response = await client.get(
            f"/validation-results/executions/{execution.id}", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(execution.id)

    async def test_get_execution_missing_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            f"/validation-results/executions/{uuid.uuid4()}", headers=headers
        )
        assert response.status_code == 404

    async def test_get_score_uncomputed_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])

        response = await client.get(
            f"/validation-results/executions/{execution.id}/score", headers=headers
        )
        assert response.status_code == 404

    async def test_get_score_returns_computed_score(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])
        db_session.add(
            ValidationScore(
                organization_id=org_id,
                execution_id=execution.id,
                overall_score=88.0,
                computed_at=datetime.now(UTC),
            )
        )
        await db_session.flush()

        response = await client.get(
            f"/validation-results/executions/{execution.id}/score", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["overall_score"] == 88.0

"""Tests for ``GET /configurations/drift``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DriftType
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.services.drift import ConfigurationDriftService
from tests.conftest import AuthHeadersFn, make_profile


async def test_list_drift_by_profile_id(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session)
    drift_service = ConfigurationDriftService(ConfigurationDriftRepository(db_session))
    await drift_service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.UNEXPECTED_CHANGES,
        details={"field": "port"},
    )

    response = await client.get(
        "/configurations/drift",
        params={"organization_id": str(profile.organization_id), "profile_id": str(profile.id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_list_drift_unresolved_for_org(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session)
    drift_service = ConfigurationDriftService(ConfigurationDriftRepository(db_session))
    await drift_service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.POLICY_DRIFT,
        details={},
    )

    response = await client.get(
        "/configurations/drift",
        params={"organization_id": str(profile.organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1

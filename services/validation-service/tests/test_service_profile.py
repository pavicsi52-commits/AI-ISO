"""Tests for :class:`app.services.profile.ValidationProfileService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationConcurrencyStrategy, ValidationProfileType
from app.repositories.validation_profile import ValidationProfileRepository
from app.services.profile import ValidationProfileService


def _service(db_session: AsyncSession) -> ValidationProfileService:
    return ValidationProfileService(ValidationProfileRepository(db_session))


class TestValidationProfileService:
    async def test_create_sets_initial_version(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        profile = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Infra Profile",
            description=None,
            profile_type=ValidationProfileType.INFRASTRUCTURE,
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            scoring_weights={},
            tags=[],
            owner=None,
        )
        assert profile.current_version_number == "1.0.0"

    async def test_update_bumps_version(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        profile = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Infra Profile",
            description=None,
            profile_type=ValidationProfileType.INFRASTRUCTURE,
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            scoring_weights={},
            tags=[],
            owner=None,
        )
        updated = await service.update(
            profile.id,
            name="Infra Profile v2",
            description="updated",
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.PARALLEL,
            scoring_weights={},
            tags=["prod"],
            owner="team-infra",
        )
        assert updated.current_version_number == "1.0.1"
        assert updated.name == "Infra Profile v2"
        assert updated.concurrency_strategy == str(ValidationConcurrencyStrategy.PARALLEL)

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org_filters(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org_id = uuid.uuid4()
        await service.create(
            organization_id=org_id,
            project_id=None,
            name="Profile A",
            description=None,
            profile_type=ValidationProfileType.SECURITY,
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            scoring_weights={},
            tags=[],
            owner=None,
        )
        await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Profile B",
            description=None,
            profile_type=ValidationProfileType.SECURITY,
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            scoring_weights={},
            tags=[],
            owner=None,
        )
        profiles = await service.list_for_org(org_id)
        assert len(profiles) == 1

    async def test_delete(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        profile = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Deletable",
            description=None,
            profile_type=ValidationProfileType.CUSTOM,
            target_types=[],
            check_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            scoring_weights={},
            tags=[],
            owner=None,
        )
        await service.delete(profile.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(profile.id)

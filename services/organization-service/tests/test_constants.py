"""Tests for ``app/constants.py``."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.repositories.organization import OrganizationRepository


def test_default_organization_id_is_the_well_known_placeholder() -> None:
    assert UUID("00000000-0000-0000-0000-000000000001") == DEFAULT_ORGANIZATION_ID


async def test_default_organization_id_resolves_to_a_real_seeded_row(
    db_session: AsyncSession,
) -> None:
    """The seed migration provisions a real organization at this id -- unlike
    every other AI-IOS service, where the identical placeholder resolves
    to nothing.
    """
    repository = OrganizationRepository(db_session)
    organization = await repository.require_by_id(DEFAULT_ORGANIZATION_ID)
    assert organization.id == DEFAULT_ORGANIZATION_ID
    assert organization.organization_id == DEFAULT_ORGANIZATION_ID

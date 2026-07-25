"""Direct tests for ``app/api/deps.py`` factory functions with no REST
surface exercising them (business units, subscriptions, resource
limits, preferences, custom metadata, tags, domains, audit -- see each
service module's own "no dedicated REST surface" docstring), plus the
``require_role_in_org`` insufficient-role branch, distinct from the
not-a-member branch every ``*_requires_admin`` API test already covers.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.authorization import AuthorizationError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import add_member, make_org

from app.api import deps
from app.models.enums import MemberRole
from app.repositories.activity import OrganizationActivityRepository
from app.services.activity import OrganizationActivityService


async def test_service_factories_with_no_rest_surface_build_real_services(
    db_session: AsyncSession,
) -> None:
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))

    assert deps.get_audit_service(db_session) is not None
    assert deps.get_business_unit_service(db_session) is not None
    assert deps.get_limits_service(db_session) is not None
    assert deps.get_subscription_service(db_session, activity) is not None
    assert deps.get_preferences_service(db_session) is not None
    assert deps.get_metadata_service(db_session) is not None
    assert deps.get_tag_service(db_session) is not None
    assert deps.get_domain_service(db_session) is not None


async def test_require_role_in_org_insufficient_role_raises(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    member_user = uuid.uuid4()
    await add_member(db_session, organization.id, member_user, role=MemberRole.MEMBER)
    members = deps.get_member_service(
        db_session, OrganizationActivityService(OrganizationActivityRepository(db_session))
    )

    with pytest.raises(AuthorizationError, match="requires at least"):
        await deps.require_role_in_org(organization.id, member_user, members, MemberRole.ADMIN)

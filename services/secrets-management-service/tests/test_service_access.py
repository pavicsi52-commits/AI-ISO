"""Direct service-layer tests for ``app/services/access.py`` -- the
self-contained secret access-control list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SecretAccessAction
from app.repositories.secret_access import SecretAccessRepository
from app.services.access import SecretAccessService
from tests.conftest import make_secret


def _access_service(db_session: AsyncSession) -> SecretAccessService:
    return SecretAccessService(SecretAccessRepository(db_session))


async def test_grant_creates_new_grant(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()

    grant = await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ, SecretAccessAction.ROTATE],
        granted_by=uuid.uuid4(),
    )
    assert set(grant.actions) == {"read", "rotate"}


async def test_grant_replaces_existing_grant(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()

    first = await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
    )
    second = await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.WRITE, SecretAccessAction.DELETE],
        granted_by=uuid.uuid4(),
    )
    assert first.id == second.id
    assert set(second.actions) == {"write", "delete"}


async def test_has_action_true_when_granted(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
    )
    assert await service.has_action(secret.id, principal_id, SecretAccessAction.READ) is True


async def test_has_action_false_when_action_not_granted(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
    )
    assert await service.has_action(secret.id, principal_id, SecretAccessAction.DELETE) is False


async def test_has_action_false_when_no_grant_exists(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    assert await service.has_action(secret.id, uuid.uuid4(), SecretAccessAction.READ) is False


async def test_has_action_false_when_grant_expired(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert await service.has_action(secret.id, principal_id, SecretAccessAction.READ) is False


async def test_has_action_true_when_grant_not_yet_expired(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert await service.has_action(secret.id, principal_id, SecretAccessAction.READ) is True


async def test_revoke_removes_grant(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    principal_id = uuid.uuid4()
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=principal_id,
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
    )
    await service.revoke(secret.id, principal_id)
    assert await service.has_action(secret.id, principal_id, SecretAccessAction.READ) is False


async def test_revoke_is_noop_when_no_grant_exists(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    await service.revoke(secret.id, uuid.uuid4())  # must not raise


async def test_list_for_secret_returns_all_grants(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = _access_service(db_session)
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=uuid.uuid4(),
        actions=[SecretAccessAction.READ],
        granted_by=uuid.uuid4(),
    )
    await service.grant(
        secret.id,
        organization_id=secret.organization_id,
        principal_id=uuid.uuid4(),
        actions=[SecretAccessAction.WRITE],
        granted_by=uuid.uuid4(),
    )
    grants = await service.list_for_secret(secret.id)
    assert len(grants) == 2

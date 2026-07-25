"""Direct service-layer tests for ``app/services/tag.py``. No REST
surface of its own -- see ``test_services_no_rest_surface.py``'s
module docstring.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.secret_tag import SecretTagRepository
from app.services.tag import SecretTagService
from tests.conftest import make_secret


async def test_assign_and_list(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretTagService(SecretTagRepository(db_session))

    tag = await service.assign(secret.id, organization_id=secret.organization_id, label="prod")
    assert tag.label == "prod"

    tags = await service.list_for_secret(secret.id)
    assert len(tags) == 1


async def test_assign_duplicate_label_conflicts(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretTagService(SecretTagRepository(db_session))
    await service.assign(secret.id, organization_id=secret.organization_id, label="dup")
    with pytest.raises(ConflictError):
        await service.assign(secret.id, organization_id=secret.organization_id, label="dup")


async def test_remove(db_session: AsyncSession) -> None:
    secret = await make_secret(db_session)
    service = SecretTagService(SecretTagRepository(db_session))
    tag = await service.assign(secret.id, organization_id=secret.organization_id, label="removable")
    await service.remove(secret.id, tag.id)
    assert await service.list_for_secret(secret.id) == []


async def test_remove_wrong_secret_raises(db_session: AsyncSession) -> None:
    secret_a = await make_secret(db_session)
    secret_b = await make_secret(db_session)
    service = SecretTagService(SecretTagRepository(db_session))
    tag = await service.assign(secret_a.id, organization_id=secret_a.organization_id, label="a-tag")
    with pytest.raises(NotFoundError):
        await service.remove(secret_b.id, tag.id)

"""Tests for the ``/playbooks/repository`` router.

Docs/041's own REST list only calls for a ``GET`` endpoint here -- there
is no ``POST`` -- so folders are seeded directly through
:class:`PlaybookRepositoryFolderService` against the same request-scoped
``db_session`` the ``client`` fixture's app is wired to, then read back
over real HTTP.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RepositoryType, RepositoryVisibility
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository
from app.services.repository_folder import PlaybookRepositoryFolderService
from tests.conftest import AuthHeadersFn


class TestRepositoryFoldersApi:
    async def test_list_repository_folders(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        service = PlaybookRepositoryFolderService(PlaybookRepositoryFolderRepository(db_session))
        await service.create(
            organization_id=org_id,
            name="platform-team",
            description="Shared platform playbooks",
            repository_type=RepositoryType.SHARED,
            visibility=RepositoryVisibility.ORGANIZATION,
        )

        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/playbooks/repository", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"][0]["name"] == "platform-team"

    async def test_list_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/playbooks/repository", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401

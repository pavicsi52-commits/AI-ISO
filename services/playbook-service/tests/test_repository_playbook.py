"""Direct tests for :class:`app.repositories.playbook.PlaybookRepository`
methods not otherwise reached through :class:`~app.services.playbook
.PlaybookService` -- ``list_for_repository`` (no service method wraps
it; ``repository_id`` filing has no dedicated endpoint of its own) and
``search_and_paginate``'s own ``sort_fields`` branch.
"""

from __future__ import annotations

import uuid

from shared_core.database.sorting import SortDirection, SortField
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RepositoryType, RepositoryVisibility
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository
from app.services.repository_folder import PlaybookRepositoryFolderService
from tests.conftest import make_playbook


class TestPlaybookRepository:
    async def test_list_for_repository(self, db_session: AsyncSession) -> None:
        folder_service = PlaybookRepositoryFolderService(
            PlaybookRepositoryFolderRepository(db_session)
        )
        folder = await folder_service.create(
            organization_id=uuid.uuid4(),
            name="platform-team",
            description=None,
            repository_type=RepositoryType.SHARED,
            visibility=RepositoryVisibility.ORGANIZATION,
        )
        playbook = await make_playbook(db_session)
        playbook.repository_id = folder.id
        await db_session.flush()

        repository = PlaybookRepository(db_session)
        results = await repository.list_for_repository(folder.id)
        assert [item.id for item in results] == [playbook.id]

    async def test_list_for_repository_empty(self, db_session: AsyncSession) -> None:
        repository = PlaybookRepository(db_session)
        assert await repository.list_for_repository(uuid.uuid4()) == []

    async def test_search_and_paginate_with_sort_fields(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await make_playbook(db_session, organization_id=org_id, name="b-playbook")
        await make_playbook(db_session, organization_id=org_id, name="a-playbook")

        repository = PlaybookRepository(db_session)
        result = await repository.search_and_paginate(
            sort_fields=[SortField(field="name", direction=SortDirection.ASC)]
        )
        names = [playbook.name for playbook in result.items]
        assert names == sorted(names)

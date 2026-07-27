"""Tests for :class:`app.repositories.playbook_artifact.PlaybookArtifactRepository`.

No dedicated :class:`~app.services` layer exists for
:class:`~app.models.playbook_artifact.PlaybookArtifact` -- docs/041's
own REST list names no ``/artifacts`` endpoint of its own, so this
repository is exercised directly, matching the same "repository without
a router" precedent already established for schema-only modules (see
``test_schemas_unrouted.py``).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ArtifactType, ContentType
from app.models.playbook_artifact import PlaybookArtifact
from app.repositories.playbook_artifact import PlaybookArtifactRepository
from tests.conftest import build_version_service, make_playbook


class TestPlaybookArtifactRepository:
    async def test_create_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        repository = PlaybookArtifactRepository(db_session)

        artifact = await repository.create(
            PlaybookArtifact(
                organization_id=playbook.organization_id,
                playbook_id=playbook.id,
                version_id=None,
                artifact_type=ArtifactType.CHECKSUM_MANIFEST,
                name="manifest.json",
                content={"files": []},
                checksum="deadbeef",
            )
        )
        assert artifact.name == "manifest.json"

        artifacts = await repository.list_for_playbook(playbook.id)
        assert [item.id for item in artifacts] == [artifact.id]

    async def test_list_for_version(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        version_service = build_version_service(db_session)
        version = await version_service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        repository = PlaybookArtifactRepository(db_session)
        await repository.create(
            PlaybookArtifact(
                organization_id=playbook.organization_id,
                playbook_id=playbook.id,
                version_id=version.id,
                artifact_type=ArtifactType.SOURCE_BUNDLE,
                name="bundle.tar",
                content={},
                checksum=None,
            )
        )

        artifacts = await repository.list_for_version(version.id)
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == ArtifactType.SOURCE_BUNDLE

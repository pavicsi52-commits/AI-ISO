"""Playbook version management. Per docs/041 "VERSIONING" "Support":
Semantic Versioning, Version History, Rollback, Diff, Comparison,
Release Notes, Change Tracking, Approval Per Version.

Every new version is structurally validated
(:func:`app.validators.content_validator.validate_content_or_raise`)
and checksummed (``shared_core.helpers.hash_helper.sha256_hex``)
before it's persisted -- a version is an immutable, verifiable content
snapshot, never a bare string. "Rollback" is not a separate mechanism:
since every prior version stays retrievable via
:meth:`get_by_id`/:meth:`list_for_playbook`, rolling back means the
caller re-submits an old version's own ``content`` as a new version,
the same "content lives in a snapshot, roll back by re-snapshotting"
shape ``services/configuration-management-service``'s own
``ConfigurationVersion`` established.
"""

from __future__ import annotations

import difflib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.helpers.hash_helper import sha256_hex

from app.events.playbook_events import VersionCreatedEvent
from app.models.playbook_version import PlaybookVersion
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.validators.content_validator import validate_content_or_raise

_INITIAL_VERSION = "1.0.0"

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class PlaybookVersionService:
    """Creates, reads, and compares playbook content version snapshots."""

    def __init__(
        self,
        versions: PlaybookVersionRepository,
        playbooks: PlaybookRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._versions = versions
        self._playbooks = playbooks
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, version_id: UUID) -> PlaybookVersion:
        """Return the version identified by *version_id*.

        Raises:
            NotFoundError: If no such version exists.
        """
        return await self._versions.require_by_id(version_id)

    async def get_latest_for_playbook(self, playbook_id: UUID) -> PlaybookVersion | None:
        """Return *playbook_id*'s most recently created version, or ``None``."""
        return await self._versions.get_latest_for_playbook(playbook_id)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookVersion]:
        """Every version recorded for *playbook_id*, newest first ("Version History")."""
        return await self._versions.list_for_playbook(playbook_id)

    async def create_version(
        self,
        playbook_id: UUID,
        *,
        content: str,
        release_notes: str | None,
        change_summary: str | None,
        changed_by: UUID | None,
    ) -> PlaybookVersion:
        """Structurally validate, checksum, and snapshot new content as
        the next semantic version, updating the playbook's own
        ``current_version`` pointer.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
            ContentValidationError: If *content* fails structural
                validation for the playbook's own declared content type.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        await validate_content_or_raise(playbook.content_type, content)

        latest = await self._versions.get_latest_for_playbook(playbook_id)
        version_number = _bump_patch(latest.version_number) if latest else _INITIAL_VERSION

        version = await self._versions.create(
            PlaybookVersion(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                version_number=version_number,
                content=content,
                checksum=sha256_hex(content),
                release_notes=release_notes,
                change_summary=change_summary,
                changed_by=changed_by,
            )
        )
        playbook.current_version = version_number
        await self._playbooks.update(playbook)
        await self._publish(
            VersionCreatedEvent(
                source_service="playbook-service",
                payload={"playbook_id": str(playbook_id), "version_id": str(version.id)},
            )
        )
        return version

    async def record_approval(self, version_id: UUID, *, approved_by: UUID) -> PlaybookVersion:
        """Record who approved a version ("Approval Per Version")."""
        version = await self.get_by_id(version_id)
        version.approved_by = approved_by
        version.approved_at = datetime.now(UTC)
        return await self._versions.update(version)

    async def diff(self, from_version_id: UUID, to_version_id: UUID) -> dict[str, Any]:
        """A real line-based unified diff between two versions' own content
        ("Diff"/"Comparison").
        """
        from_version = await self.get_by_id(from_version_id)
        to_version = await self.get_by_id(to_version_id)
        diff_lines = list(
            difflib.unified_diff(
                from_version.content.splitlines(),
                to_version.content.splitlines(),
                fromfile=from_version.version_number,
                tofile=to_version.version_number,
                lineterm="",
            )
        )
        return {
            "from_version": from_version.version_number,
            "to_version": to_version.version_number,
            "diff": diff_lines,
        }


def _bump_patch(version_number: str) -> str:
    major, minor, patch = version_number.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


__all__ = ["PlaybookVersionService"]

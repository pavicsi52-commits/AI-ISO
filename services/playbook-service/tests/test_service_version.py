"""Tests for :class:`app.services.version.PlaybookVersionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.validators.content_validator import ContentValidationError
from tests.conftest import build_version_service, make_playbook


class TestPlaybookVersionService:
    async def test_create_version_starts_at_initial_and_bumps_patch(
        self, db_session: AsyncSession
    ) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        service = build_version_service(db_session)

        first = await service.create_version(
            playbook.id,
            content="echo one",
            release_notes=None,
            change_summary="Initial.",
            changed_by=None,
        )
        assert first.version_number == "1.0.0"
        assert first.checksum

        second = await service.create_version(
            playbook.id,
            content="echo two",
            release_notes="Notes.",
            change_summary="Second change.",
            changed_by=None,
        )
        assert second.version_number == "1.0.1"
        assert playbook.current_version == "1.0.1"

    async def test_create_version_publishes_event(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = build_version_service(db_session, publish_event=_collect)
        await service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        assert len(events) == 1
        assert events[0].event_name == "VersionCreated"

    async def test_create_version_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = build_version_service(db_session)
        with pytest.raises(NotFoundError):
            await service.create_version(
                uuid.uuid4(),
                content="echo hi",
                release_notes=None,
                change_summary=None,
                changed_by=None,
            )

    async def test_create_version_invalid_content_raises(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.PYTHON_SCRIPT)
        service = build_version_service(db_session)
        with pytest.raises(ContentValidationError):
            await service.create_version(
                playbook.id,
                content="def broken(:",
                release_notes=None,
                change_summary=None,
                changed_by=None,
            )

    async def test_get_latest_for_playbook_none_when_empty(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = build_version_service(db_session)
        assert await service.get_latest_for_playbook(playbook.id) is None

    async def test_list_for_playbook_newest_first(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        service = build_version_service(db_session)
        await service.create_version(
            playbook.id,
            content="echo one",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        await service.create_version(
            playbook.id,
            content="echo two",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        versions = await service.list_for_playbook(playbook.id)
        assert [v.version_number for v in versions] == ["1.0.1", "1.0.0"]

    async def test_record_approval(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        service = build_version_service(db_session)
        version = await service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        approver_id = uuid.uuid4()
        approved = await service.record_approval(version.id, approved_by=approver_id)
        assert approved.approved_by == approver_id
        assert approved.approved_at is not None

    async def test_diff_returns_unified_diff(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        service = build_version_service(db_session)
        first = await service.create_version(
            playbook.id,
            content="echo one",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        second = await service.create_version(
            playbook.id,
            content="echo two",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        result = await service.diff(first.id, second.id)
        assert result["from_version"] == "1.0.0"
        assert result["to_version"] == "1.0.1"
        assert any("echo one" in line for line in result["diff"])
        assert any("echo two" in line for line in result["diff"])

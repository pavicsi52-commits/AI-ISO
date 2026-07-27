"""Tests for :class:`app.services.signature.PlaybookSignatureService`.

Uses real Ed25519 sign/verify via :mod:`app.signing.signer` -- no mocking
of the cryptography involved, matching this service's own "genuinely
real Ed25519 sign/verify" testing discipline (see ``conftest.py``).
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType
from app.repositories.playbook_signature import PlaybookSignatureRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.services.signature import EventPublisher, PlaybookSignatureService
from app.signing.signer import generate_signing_keypair
from tests.conftest import build_version_service, make_playbook


def _build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> PlaybookSignatureService:
    return PlaybookSignatureService(
        PlaybookSignatureRepository(db_session),
        PlaybookVersionRepository(db_session),
        publish_event=publish_event,
    )


class TestPlaybookSignatureService:
    async def test_sign_produces_verified_signature(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        version_service = build_version_service(db_session)
        version = await version_service.create_version(
            playbook.id,
            content="echo signed",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        private_pem, public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        signer_id = uuid.uuid4()

        signature = await service.sign(
            version.id, signer_id=signer_id, private_key_pem=private_pem, public_key_pem=public_pem
        )
        assert signature.verified is True
        assert signature.checksum == version.checksum
        assert signature.signer_id == signer_id
        assert signature.public_key_fingerprint.startswith("SHA256:")

    async def test_sign_publishes_signature_verified_event(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        version_service = build_version_service(db_session)
        version = await version_service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        private_pem, public_pem = generate_signing_keypair()
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = _build_service(db_session, publish_event=_collect)
        await service.sign(
            version.id, signer_id=None, private_key_pem=private_pem, public_key_pem=public_pem
        )
        assert [event.event_name for event in events] == ["SignatureVerified"]

    async def test_sign_missing_version_raises(self, db_session: AsyncSession) -> None:
        private_pem, public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.sign(
                uuid.uuid4(), signer_id=None, private_key_pem=private_pem, public_key_pem=public_pem
            )

    async def test_verify_with_correct_public_key_returns_true(
        self, db_session: AsyncSession
    ) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        version_service = build_version_service(db_session)
        version = await version_service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        private_pem, public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        signature = await service.sign(
            version.id, signer_id=None, private_key_pem=private_pem, public_key_pem=public_pem
        )

        assert await service.verify(signature.id, public_key_pem=public_pem) is True

    async def test_verify_with_wrong_public_key_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        playbook = await make_playbook(db_session, content_type=ContentType.SHELL_SCRIPT)
        version_service = build_version_service(db_session)
        version = await version_service.create_version(
            playbook.id,
            content="echo hi",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )
        private_pem, public_pem = generate_signing_keypair()
        _other_private_pem, other_public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        signature = await service.sign(
            version.id, signer_id=None, private_key_pem=private_pem, public_key_pem=public_pem
        )

        assert await service.verify(signature.id, public_key_pem=other_public_pem) is False

    async def test_verify_missing_signature_raises(self, db_session: AsyncSession) -> None:
        _private_pem, public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.verify(uuid.uuid4(), public_key_pem=public_pem)

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
        private_pem, public_pem = generate_signing_keypair()
        service = _build_service(db_session)
        await service.sign(
            version.id, signer_id=None, private_key_pem=private_pem, public_key_pem=public_pem
        )

        signatures = await service.list_for_version(version.id)
        assert len(signatures) == 1

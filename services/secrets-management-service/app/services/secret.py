"""Secret lifecycle: the crypto-critical orchestrator.

Per docs/035 "SECRET MODEL"/"SECRET STATUS"/"AUDIT". Owns the one place
in this service where a secret's plaintext value passes through Python
code on its way to/from encryption -- every other layer (repositories,
API responses for list/search views) only ever sees ciphertext or
nothing at all. Every operation here that touches a value is paired
with an audit entry that captures **metadata only** -- see
``app/models/secret_audit.py``'s own docstring.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent

from app.events.secret_events import (
    SecretAccessedEvent,
    SecretCreatedEvent,
    SecretDeletedEvent,
    SecretExpiredEvent,
    SecretRotatedEvent,
    SecretUpdatedEvent,
)
from app.models.enums import (
    RotationOutcome,
    RotationTrigger,
    SecretStatus,
    SecretType,
)
from app.models.secret import Secret
from app.repositories.secret import SecretRepository
from app.services.audit import SecretAuditService
from app.services.rotation_history import SecretRotationHistoryService
from app.services.secret_version import SecretVersionService
from app.services.tag import SecretTagService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class SecretService:
    """Creates, reads, updates, rotates, and deletes secrets."""

    def __init__(
        self,
        secrets: SecretRepository,
        versions: SecretVersionService,
        tags: SecretTagService,
        rotation_history: SecretRotationHistoryService,
        audit: SecretAuditService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._secrets = secrets
        self._versions = versions
        self._tags = tags
        self._rotation_history = rotation_history
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, secret_id: UUID) -> Secret:
        """Return the secret identified by *secret_id* -- metadata only,
        never its value.

        Raises:
            NotFoundError: If no such secret exists.
        """
        return await self._secrets.require_by_id(secret_id)

    async def list_for_org(self, organization_id: UUID) -> list[Secret]:
        """Every secret belonging to *organization_id* -- metadata only ("SECRET SEARCH")."""
        return await self._secrets.list_for_org(organization_id)

    async def list_expiring_before(self, cutoff: datetime) -> list[Secret]:
        """Every still-active secret expiring before *cutoff* -- used by
        the background expiry worker.
        """
        return await self._secrets.list_expiring_before(cutoff)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[Secret]:
        """Full-text search plus filter plus sort plus pagination ("SECRET SEARCH")."""
        return await self._secrets.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def get_decrypted(self, secret_id: UUID, *, actor_id: UUID | None) -> tuple[Secret, str]:
        """Return *secret_id* together with its decrypted current value
        ("Decrypt"/"Read"). Every call is audited and published as a
        :class:`~app.events.secret_events.SecretAccessedEvent`.

        Raises:
            NotFoundError: If no such secret, or no current version, exists.
        """
        secret = await self.get_by_id(secret_id)
        current = await self._versions.get_current(secret_id)
        plaintext = await self._versions.decrypt(current)
        await self._audit.record(
            secret_id,
            organization_id=secret.organization_id,
            actor_id=actor_id,
            action="read",
        )
        await self._publish(
            SecretAccessedEvent(
                source_service="secrets-management-service",
                payload={
                    "secret_id": str(secret_id),
                    "actor_id": str(actor_id) if actor_id else None,
                },
            )
        )
        return secret, plaintext

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        category_id: UUID | None,
        secret_type: SecretType,
        owner_id: UUID,
        value: str,
        expires_at: datetime | None,
        rotation_policy: dict[str, Any],
        metadata: dict[str, Any],
        tags: list[str],
    ) -> Secret:
        """Create a new secret and its initial value version ("Create")."""
        secret = await self._secrets.create(
            Secret(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                description=description,
                category_id=category_id,
                secret_type=secret_type,
                status=SecretStatus.ACTIVE,
                owner_id=owner_id,
                current_version=0,
                expires_at=expires_at,
                rotation_policy=rotation_policy,
                metadata_=metadata,
            )
        )
        version = await self._versions.create_version(
            secret.id, organization_id=organization_id, plaintext=value, created_by=owner_id
        )
        secret.current_version = version.version_number
        for label in tags:
            await self._tags.assign(secret.id, organization_id=organization_id, label=label)
        await self._audit.record(
            secret.id,
            organization_id=organization_id,
            actor_id=owner_id,
            action="create",
            after={"name": name, "secret_type": secret_type.value},
        )
        await self._publish(
            SecretCreatedEvent(
                source_service="secrets-management-service", payload={"secret_id": str(secret.id)}
            )
        )
        return secret

    async def update(
        self,
        secret_id: UUID,
        *,
        actor_id: UUID | None,
        name: str,
        description: str | None,
        category_id: UUID | None,
        status: SecretStatus,
        expires_at: datetime | None,
        rotation_policy: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Secret:
        """Update a secret's identity/lifecycle fields -- never its value
        (see :meth:`rotate` for that) ("Update").
        """
        secret = await self.get_by_id(secret_id)
        # ``str()``, not ``.value`` -- ``secret.status`` was just loaded via
        # a fresh SELECT (the row's own SQLAlchemy identity-map entry is
        # weakly referenced and may have already been GC'd since the row
        # was first inserted in an earlier request), and this column's
        # ``String`` type -- the same convention every AI-IOS enum column
        # uses -- doesn't reconstitute a genuine ``SecretStatus`` member on
        # load, only the raw string. ``SecretStatus`` is a ``StrEnum``, so
        # ``str()`` gives the identical result whichever shape it's in.
        before = {"name": secret.name, "status": str(secret.status)}
        secret.name = name
        secret.description = description
        secret.category_id = category_id
        secret.status = status
        secret.expires_at = expires_at
        secret.rotation_policy = rotation_policy
        secret.metadata_ = metadata
        await self._audit.record(
            secret_id,
            organization_id=secret.organization_id,
            actor_id=actor_id,
            action="update",
            before=before,
            after={"name": name, "status": status.value},
        )
        await self._publish(
            SecretUpdatedEvent(
                source_service="secrets-management-service", payload={"secret_id": str(secret_id)}
            )
        )
        return secret

    async def rotate(
        self,
        secret_id: UUID,
        *,
        new_value: str,
        rotated_by: UUID | None,
        trigger: RotationTrigger = RotationTrigger.MANUAL,
    ) -> Secret:
        """Rotate a secret's value to *new_value*, recording history either
        way ("Manual Rotation"/"Scheduled Rotation"/"Automatic Rotation",
        "Failure Recovery").

        Raises:
            NotFoundError: If no such secret exists.
        """
        secret = await self.get_by_id(secret_id)
        previous_version_number = secret.current_version
        try:
            version = await self._versions.create_version(
                secret_id,
                organization_id=secret.organization_id,
                plaintext=new_value,
                created_by=rotated_by,
            )
        except Exception as exc:
            await self._rotation_history.record(
                secret_id,
                organization_id=secret.organization_id,
                rotated_by=rotated_by,
                trigger=trigger,
                previous_version_number=previous_version_number,
                new_version_number=None,
                outcome=RotationOutcome.FAILED,
                error_message=str(exc),
            )
            raise
        secret.current_version = version.version_number
        secret.status = SecretStatus.ACTIVE
        await self._rotation_history.record(
            secret_id,
            organization_id=secret.organization_id,
            rotated_by=rotated_by,
            trigger=trigger,
            previous_version_number=previous_version_number,
            new_version_number=version.version_number,
            outcome=RotationOutcome.SUCCESS,
        )
        await self._audit.record(
            secret_id,
            organization_id=secret.organization_id,
            actor_id=rotated_by,
            action="rotate",
            before={"version": previous_version_number},
            after={"version": version.version_number},
        )
        await self._publish(
            SecretRotatedEvent(
                source_service="secrets-management-service", payload={"secret_id": str(secret_id)}
            )
        )
        return secret

    async def delete(self, secret_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete a secret ("Soft Delete")."""
        secret = await self.get_by_id(secret_id)
        await self._secrets.delete(secret_id)
        await self._audit.record(
            secret_id,
            organization_id=secret.organization_id,
            actor_id=actor_id,
            action="delete",
        )
        await self._publish(
            SecretDeletedEvent(
                source_service="secrets-management-service", payload={"secret_id": str(secret_id)}
            )
        )

    async def mark_expired(self, secret_id: UUID) -> Secret:
        """Mark a secret expired ("SECRET STATUS": Expired), if not already."""
        secret = await self.get_by_id(secret_id)
        if secret.status != SecretStatus.EXPIRED:
            secret.status = SecretStatus.EXPIRED
            await self._publish(
                SecretExpiredEvent(
                    source_service="secrets-management-service",
                    payload={"secret_id": str(secret_id)},
                )
            )
        return secret

    async def is_expired(self, secret: Secret, *, now: datetime | None = None) -> bool:
        """Whether *secret* has passed its expiration time."""
        if secret.expires_at is None:
            return False
        return (now or datetime.now(UTC)) >= secret.expires_at


__all__ = ["EventPublisher", "SecretService"]

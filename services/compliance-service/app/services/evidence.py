"""Evidence collection and verification.

**Evidence is immutable** (docs/051, "SECURITY: Immutable evidence").
This service is where that is enforced: it writes rows and it verifies
them, and it has no method that changes a stored payload.

The reason is narrow and worth stating. Evidence exists to be shown to
somebody who does not trust you. Evidence that *could* have been edited
after the fact proves only that a row existed at some point -- and an
auditor who finds one editable row has to discard the whole trail, not
just that row. So correction is by supersession, and every row carries a
digest that can be recomputed by anyone holding the payload.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.compliance_events import SOURCE_SERVICE, EvidenceCollectedEvent
from app.models.enums import EvidenceKind, EvidenceSource
from app.models.evidence import ComplianceEvidence, content_digest
from app.repositories.runs import EvidenceRepository
from app.types import EventPublisher

logger = get_logger("app.services.evidence")


class EvidenceService:
    """Records and verifies immutable proof."""

    def __init__(
        self,
        evidence: EvidenceRepository,
        *,
        publish_event: EventPublisher | None = None,
        max_payload_bytes: int = 1_048_576,
        default_validity_days: int = 90,
    ) -> None:
        self._evidence = evidence
        self._publish = publish_event
        self._max_payload_bytes = max_payload_bytes
        self._default_validity_days = default_validity_days

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def collect(
        self,
        organization_id: UUID,
        *,
        kind: EvidenceKind,
        source: EvidenceSource,
        title: str,
        payload: dict[str, Any],
        control_id: UUID | None = None,
        assessment_id: UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        source_reference: str | None = None,
        description: str | None = None,
        collected_at: datetime | None = None,
        collected_by: str | None = None,
        validity_days: int | None = None,
        content_type: str | None = None,
        storage_key: str | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceEvidence:
        """Record one piece of proof, hashed at the moment it arrives.

        Raises:
            ValidationError: If the payload is empty or oversized. Empty
                is refused because a piece of evidence proving nothing is
                worse than an absent one -- it makes a gap look filled.
        """
        if not payload:
            raise ValidationError(
                "Evidence needs a payload. An empty record makes a gap look filled, "
                "which is worse than having no evidence at all."
            )

        size = len(str(payload))
        if size > self._max_payload_bytes:
            raise ValidationError(
                f"Evidence payload is {size} bytes; the inline ceiling is "
                f"{self._max_payload_bytes}. Store the artefact in object storage and "
                "record its key and digest here."
            )

        moment = collected_at or datetime.now(UTC)
        days = validity_days if validity_days is not None else self._default_validity_days

        stored = await self._evidence.create(
            ComplianceEvidence(
                organization_id=organization_id,
                assessment_id=assessment_id,
                control_id=control_id,
                kind=kind,
                source=source,
                source_reference=source_reference,
                title=title,
                description=description,
                target_type=target_type,
                target_id=target_id,
                payload=payload,
                digest=content_digest(payload),
                collected_at=moment,
                collected_by=collected_by,
                expires_at=moment + timedelta(days=days),
                size_bytes=size,
                content_type=content_type,
                storage_key=storage_key,
                tags=list(tags or []),
                created_by=actor_id,
            )
        )

        await self._publish_event(
            EvidenceCollectedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "evidence_id": str(stored.id),
                    "kind": str(kind),
                    "source": str(source),
                    "control_id": str(control_id) if control_id else None,
                    "target_id": target_id,
                    # The digest, never the payload: evidence can be
                    # megabytes and can contain exactly the configuration
                    # detail an organization is least willing to
                    # broadcast on a shared bus.
                    "digest": stored.digest,
                },
            )
        )
        return stored

    async def supersede(
        self,
        organization_id: UUID,
        evidence_id: UUID,
        *,
        payload: dict[str, Any],
        title: str | None = None,
        reason: str | None = None,
        collected_by: str | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceEvidence:
        """Correct evidence by replacing it, never by editing it.

        Both rows survive and the new one points at the old, so the chain
        shows what was believed and when. The superseded row keeps its
        original payload and digest, which is what makes it still
        verifiable afterwards -- a corrected record whose predecessor no
        longer checks out is not a correction, it is a gap.

        Raises:
            NotFoundError: If the original does not exist here.
            ValidationError: If the replacement payload is empty.
        """
        original = await self._evidence.require_in_org(organization_id, evidence_id)
        replacement = await self.collect(
            organization_id,
            kind=original.kind,
            source=original.source,
            title=title or original.title,
            payload=payload,
            control_id=original.control_id,
            assessment_id=original.assessment_id,
            target_type=original.target_type,
            target_id=original.target_id,
            source_reference=original.source_reference,
            description=reason or original.description,
            collected_by=collected_by,
            actor_id=actor_id,
        )
        replacement.supersedes_id = original.id
        await self._evidence.mark_superseded(original.id)
        logger.info(
            "Evidence was superseded rather than edited.",
            extra={
                "extra_fields": {
                    "organization_id": str(organization_id),
                    "original_id": str(original.id),
                    "replacement_id": str(replacement.id),
                }
            },
        )
        return replacement

    async def get(self, organization_id: UUID, evidence_id: UUID) -> ComplianceEvidence:
        """One evidence row, with its integrity checked.

        Verification happens on every single read, not on request. An
        integrity check somebody has to remember to ask for is one that
        gets asked for after the audit rather than before it.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stored = await self._evidence.require_in_org(organization_id, evidence_id)
        if not self.verify(stored):
            logger.error(
                "Evidence failed its integrity check; the stored payload no longer "
                "matches the digest recorded when it was collected.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "evidence_id": str(evidence_id),
                        "recorded_digest": stored.digest,
                    }
                },
            )
        return stored

    async def list_evidence(
        self,
        organization_id: UUID,
        *,
        control_id: UUID | None = None,
        assessment_id: UUID | None = None,
        target_id: str | None = None,
        include_superseded: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceEvidence]:
        """Evidence, newest first."""
        return await self._evidence.list_for_org(
            organization_id,
            control_id=control_id,
            assessment_id=assessment_id,
            target_id=target_id,
            include_superseded=include_superseded,
            limit=limit,
            offset=offset,
        )

    async def payload_for_targets(
        self, organization_id: UUID, target_ids: list[str], *, per_target: int = 50
    ) -> dict[str, dict[str, Any]]:
        """The merged current evidence for each target, for an assessment.

        Merged **oldest-first so newer evidence wins**, because a
        collector that re-reported a host after a change must not be
        overwritten by the stale snapshot it replaced. Getting this
        backwards would make an assessment evaluate yesterday's estate
        and report it as today's.
        """
        merged: dict[str, dict[str, Any]] = {}
        for target_id in target_ids:
            rows = await self._evidence.latest_for_target(
                organization_id, target_id, limit=per_target
            )
            document: dict[str, Any] = {}
            for row in reversed(rows):
                document.update(row.payload or {})
            merged[target_id] = document
        return merged

    async def expiring_soon(
        self, organization_id: UUID, *, within_days: int = 30, limit: int = 500
    ) -> list[ComplianceEvidence]:
        """Evidence about to stop being current."""
        return await self._evidence.list_expiring(
            organization_id,
            before=datetime.now(UTC) + timedelta(days=within_days),
            limit=limit,
        )

    async def verify_all(self, organization_id: UUID, *, limit: int = 1_000) -> dict[str, Any]:
        """Recompute every digest and report any that no longer match.

        The check an audit-preparation window actually needs. Superseded
        rows are included on purpose -- a tampered historical record is
        exactly what this is looking for, and excluding them would leave
        the largest and least-watched part of the trail unchecked.
        """
        rows = await self._evidence.list_for_org(
            organization_id, include_superseded=True, limit=limit
        )
        failures = [
            {
                "evidence_id": str(one.id),
                "title": one.title,
                "recorded_digest": one.digest,
                "computed_digest": content_digest(one.payload or {}),
                "collected_at": one.collected_at.isoformat(),
            }
            for one in rows
            if not self.verify(one)
        ]
        if failures:
            logger.error(
                "Evidence integrity verification found mismatched digests.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "checked": len(rows),
                        "failed": len(failures),
                    }
                },
            )
        return {
            "checked": len(rows),
            "intact": len(rows) - len(failures),
            "failed": len(failures),
            "failures": failures,
        }

    @staticmethod
    def verify(evidence: ComplianceEvidence) -> bool:
        """Whether a row's payload still matches the digest it was stored with.

        A mismatch means the row was changed by something that bypassed
        this service -- direct SQL, a restore from a doctored backup --
        which is precisely the case a stored checksum is for, and
        precisely the case an application-level "immutable" flag would
        miss.
        """
        return content_digest(evidence.payload or {}) == evidence.digest

    @staticmethod
    def is_current(evidence: ComplianceEvidence, *, now: datetime | None = None) -> bool:
        """Whether this proof still describes the estate.

        A configuration snapshot from eighteen months ago does not show
        today's systems, and an audit package built from stale evidence
        fails in the room.
        """
        if evidence.expires_at is None:
            return True
        return evidence.expires_at > (now or datetime.now(UTC))


__all__ = ["EvidenceService"]

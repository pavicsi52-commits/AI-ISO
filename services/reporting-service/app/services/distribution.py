"""Report delivery ("DISTRIBUTION").

Every attempt is persisted -- successes and failures alike -- both
before and after the delivery is tried, so "was the compliance report
actually sent?" is answerable from the database rather than from logs.

Deliveries are dispatched **sequentially**, not gathered. Each one
writes its own row, and an ``AsyncSession`` is not safe for concurrent
use; the network win would not survive the corruption.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.logger import get_logger

from app.distribution.channels import DeliveryOutcome, DistributionDispatcher
from app.events.report_events import SOURCE_SERVICE, ReportDeliveredEvent
from app.export.engine import ExportedArtifact
from app.models.enums import DistributionChannel, DistributionStatus, ExportFormat
from app.models.report_distribution import ReportDistribution
from app.models.report_export import ReportExport
from app.models.report_recipient import ReportRecipient
from app.repositories.report_distribution import ReportDistributionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_recipient import ReportRecipientRepository
from app.types import EventPublisher
from app.validators.distribution import validate_target

logger = get_logger("app.services.distribution")


class ReportDistributionService:
    """Delivers rendered artifacts and records every attempt."""

    def __init__(
        self,
        distributions: ReportDistributionRepository,
        recipients: ReportRecipientRepository,
        exports: ReportExportRepository,
        dispatcher: DistributionDispatcher,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._distributions = distributions
        self._recipients = recipients
        self._exports = exports
        self._dispatcher = dispatcher
        self._publish_event = publish_event

    async def list_recipients(self, job_id: UUID) -> list[ReportRecipient]:
        """Standing recipients of one report."""
        return await self._recipients.list_for_job(job_id)

    async def add_recipient(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        job_id: UUID,
        channel: DistributionChannel,
        target: str,
        export_format: ExportFormat = ExportFormat.PDF,
        headers: dict[str, str] | None = None,
    ) -> ReportRecipient:
        """Register a standing recipient.

        Raises:
            ValidationError: If the target is not valid for the channel.
        """
        validate_target(channel, target)
        return await self._recipients.create(
            ReportRecipient(
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                channel=channel,
                target=target,
                export_format=export_format,
                headers=headers or {},
            )
        )

    async def remove_recipient(self, recipient_id: UUID) -> None:
        """Remove a standing recipient.

        Raises:
            NotFoundError: If no such recipient exists.
        """
        await self._recipients.require_by_id(recipient_id)
        await self._recipients.purge(recipient_id)

    async def deliver(
        self,
        export_record: ReportExport,
        artifact: ExportedArtifact,
        *,
        channel: DistributionChannel,
        target: str,
        report_title: str,
        recipient_id: UUID | None = None,
        headers: dict[str, str] | None = None,
    ) -> ReportDistribution:
        """Deliver one artifact over one channel, recording the attempt.

        The row is written *before* the delivery is attempted and
        updated after, so a crash mid-delivery still leaves evidence
        that it was tried.
        """
        record = await self._distributions.create(
            ReportDistribution(
                organization_id=export_record.organization_id,
                project_id=export_record.project_id,
                export_id=export_record.id,
                recipient_id=recipient_id,
                channel=channel,
                target=target,
                status=DistributionStatus.PENDING,
                attempts=1,
            )
        )
        outcome = await self._dispatch(
            channel, artifact, target, report_title=report_title, headers=headers
        )

        record.status = (
            DistributionStatus.DELIVERED if outcome.delivered else DistributionStatus.FAILED
        )
        record.error_message = None if outcome.delivered else outcome.detail
        record.share_token = outcome.share_token
        record.expires_at = outcome.expires_at
        record.storage_uri = outcome.storage_uri
        record.delivered_at = datetime.now(UTC) if outcome.delivered else None
        stored = await self._distributions.update(record)

        if outcome.delivered:
            await self._publish_event(
                ReportDeliveredEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "distribution_id": str(stored.id),
                        "export_id": str(export_record.id),
                        "channel": str(channel),
                    },
                )
            )
        else:
            logger.warning(
                "Report delivery failed.",
                extra={
                    "extra_fields": {
                        "channel": str(channel),
                        "target": target,
                        "error": outcome.detail,
                    }
                },
            )
        return stored

    async def deliver_to_recipients(
        self,
        export_record: ReportExport,
        artifact: ExportedArtifact,
        *,
        job_id: UUID,
        report_title: str,
    ) -> list[ReportDistribution]:
        """Deliver to every enabled standing recipient of a report.

        One failing recipient does not stop the others: each delivery
        records its own outcome, which is the whole reason failures are
        rows rather than exceptions.
        """
        recipients = await self._recipients.list_for_job(job_id, enabled_only=True)
        delivered: list[ReportDistribution] = []
        for recipient in recipients:
            channel = (
                recipient.channel
                if isinstance(recipient.channel, DistributionChannel)
                else DistributionChannel(recipient.channel)
            )
            delivered.append(
                await self.deliver(
                    export_record,
                    artifact,
                    channel=channel,
                    target=recipient.target,
                    report_title=report_title,
                    recipient_id=recipient.id,
                    headers=recipient.headers,
                )
            )
        return delivered

    async def _dispatch(
        self,
        channel: DistributionChannel,
        artifact: ExportedArtifact,
        target: str,
        *,
        report_title: str,
        headers: dict[str, str] | None,
    ) -> DeliveryOutcome:
        """Route to the dispatcher method for *channel*."""
        match channel:
            case DistributionChannel.EMAIL:
                return await self._dispatcher.deliver_email(
                    artifact, target, report_title=report_title
                )
            case DistributionChannel.WEBHOOK:
                return await self._dispatcher.deliver_webhook(artifact, target, headers=headers)
            case DistributionChannel.SHARED_LINK:
                return await self._dispatcher.deliver_shared_link()
            case DistributionChannel.OBJECT_STORAGE:
                return await self._dispatcher.deliver_object_storage(
                    artifact, key=f"{artifact.checksum_sha256[:16]}/{artifact.filename}"
                )
        return await self._dispatcher.deliver_download()

    async def resolve_share_token(self, share_token: str) -> ReportExport:
        """Resolve a shared link to its artifact.

        Raises:
            NotFoundError: If the token is unknown.
            ConflictError: If the link has expired. Expiry is enforced
                here -- storing an ``expires_at`` that nothing checks
                would make the link time-limited in name only.
        """
        record = await self._distributions.get_by_share_token(share_token)
        if record is None:
            raise NotFoundError("That shared report link is not valid.")
        if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
            record.status = DistributionStatus.EXPIRED
            await self._distributions.update(record)
            raise ConflictError("That shared report link has expired.")
        return await self._exports.require_by_id(record.export_id)

    async def list_for_export(self, export_id: UUID) -> list[ReportDistribution]:
        """Every delivery attempt for one artifact."""
        return await self._distributions.list_for_export(export_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: DistributionStatus | None = None,
        limit: int = 200,
    ) -> list[ReportDistribution]:
        """Delivery attempts for an organization."""
        return await self._distributions.list_for_org(organization_id, status=status, limit=limit)


__all__ = ["ReportDistributionService"]

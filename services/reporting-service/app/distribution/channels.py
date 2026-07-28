"""Report delivery channels ("DISTRIBUTION").

Six channels, each a real delivery mechanism:

- ``DOWNLOAD`` / ``API`` -- no push at all; the artifact is already
  persisted and fetched on demand. Recording the attempt is still
  meaningful, because it is what makes "who has this report?"
  answerable.
- ``EMAIL`` -- through ``shared_core``'s own notification manager.
- ``WEBHOOK`` -- a real signed HTTP POST.
- ``SHARED_LINK`` -- a time-limited opaque token.
- ``OBJECT_STORAGE`` -- a real MinIO upload plus a presigned URL.

**Every attempt is recorded, successes and failures alike.** A delivery
that silently vanished is indistinguishable from one never attempted,
and "was the compliance report actually sent?" has to be answerable
from the record rather than from logs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager
from shared_core.storage.wrapper import StorageWrapper

from app.export.engine import ExportedArtifact

logger = get_logger("app.distribution.channels")

_TOKEN_BYTES = 32
"""256 bits of entropy for a shared-link token.

The token *is* the credential for an unauthenticated recipient, so it
has to be unguessable. ``secrets`` rather than ``random``: the latter
is seeded predictably and is not safe for anything security-bearing.
"""

_WEBHOOK_SIGNATURE_HEADER = "X-AIIOS-Signature"
_WEBHOOK_TIMESTAMP_HEADER = "X-AIIOS-Timestamp"


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """What one delivery attempt produced."""

    delivered: bool
    detail: str | None = None
    share_token: str | None = None
    expires_at: datetime | None = None
    storage_uri: str | None = None


def new_share_token() -> str:
    """Generate an unguessable shared-link token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """Compute the HMAC-SHA256 signature for a webhook delivery.

    The timestamp is inside the signed payload, so a captured request
    cannot be replayed indefinitely -- the receiver rejects a stale
    timestamp even though the signature itself still verifies.
    """
    message = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class DistributionDispatcher:
    """Delivers a rendered artifact over one channel."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        notifications: NotificationManager,
        storage: StorageWrapper | None,
        *,
        bucket: str,
        share_link_ttl_seconds: int,
        webhook_timeout_seconds: float,
        webhook_secret: str = "",
    ) -> None:
        self._http = http_client
        self._notifications = notifications
        self._storage = storage
        self._bucket = bucket
        self._share_ttl = share_link_ttl_seconds
        self._webhook_timeout = webhook_timeout_seconds
        self._webhook_secret = webhook_secret

    async def deliver_download(self) -> DeliveryOutcome:
        """Record a pull-based delivery; nothing is pushed."""
        return DeliveryOutcome(
            delivered=True, detail="Artifact available for authenticated download."
        )

    async def deliver_email(
        self, artifact: ExportedArtifact, target: str, *, report_title: str
    ) -> DeliveryOutcome:
        """Email a report to one recipient.

        The artifact is *not* attached. ``shared_core``'s notification
        manager sends a body, not attachments, and inventing an
        attachment path here would mean two divergent mail
        implementations. The recipient gets the report's identity and
        fetches it through an authenticated download, which also avoids
        mailing potentially sensitive infrastructure data as an
        unencrypted attachment.
        """
        try:
            await self._notifications.send(
                user_id=target,
                notification_type=NotificationType.INFORMATION,
                subject=f"Report ready: {report_title}",
                body=(
                    f"The report '{report_title}' has been generated "
                    f"({artifact.filename}, {artifact.size_bytes:,} bytes). "
                    "Sign in to download it."
                ),
                channel=NotificationChannel.EMAIL,
            )
        except NotificationError as exc:
            return DeliveryOutcome(delivered=False, detail=str(exc))
        return DeliveryOutcome(delivered=True, detail=f"Emailed {target}.")

    async def deliver_webhook(
        self, artifact: ExportedArtifact, target: str, *, headers: dict[str, str] | None = None
    ) -> DeliveryOutcome:
        """POST the artifact to a webhook endpoint.

        The body carries the content base64-encoded so any format --
        including PDF and XLSX -- survives a JSON transport intact.
        Signed when a secret is configured, so a receiver can verify
        the request genuinely came from this platform.
        """
        timestamp = datetime.now(UTC).isoformat()
        payload = {
            "filename": artifact.filename,
            "content_type": artifact.content_type,
            "format": str(artifact.export_format),
            "size_bytes": artifact.size_bytes,
            "checksum_sha256": artifact.checksum_sha256,
            "content_base64": b64encode(artifact.content).decode("ascii"),
            "timestamp": timestamp,
        }
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        # Serialised explicitly rather than via ``json=``: the signature
        # must cover the exact bytes sent, and letting the client
        # re-encode would risk signing something different from what
        # goes on the wire.
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if self._webhook_secret:
            request_headers[_WEBHOOK_SIGNATURE_HEADER] = sign_webhook(
                self._webhook_secret, timestamp, body
            )
            request_headers[_WEBHOOK_TIMESTAMP_HEADER] = timestamp

        try:
            response = await self._http.post(
                target,
                content=body,
                headers=request_headers,
                timeout=self._webhook_timeout,
            )
        except httpx.HTTPError as exc:
            return DeliveryOutcome(delivered=False, detail=f"Webhook unreachable: {exc}")

        if response.status_code >= httpx.codes.BAD_REQUEST:
            return DeliveryOutcome(
                delivered=False, detail=f"Webhook returned HTTP {response.status_code}."
            )
        return DeliveryOutcome(delivered=True, detail=f"Webhook accepted ({response.status_code}).")

    async def deliver_shared_link(self) -> DeliveryOutcome:
        """Mint a time-limited shared link.

        The expiry is stored on the delivery row and enforced when the
        token is redeemed, which is what makes the link genuinely
        time-limited rather than merely labelled so.
        """
        return DeliveryOutcome(
            delivered=True,
            detail="Shared link issued.",
            share_token=new_share_token(),
            expires_at=datetime.now(UTC) + timedelta(seconds=self._share_ttl),
        )

    async def deliver_object_storage(
        self, artifact: ExportedArtifact, *, key: str
    ) -> DeliveryOutcome:
        """Upload the artifact to object storage and presign a URL."""
        if self._storage is None:
            return DeliveryOutcome(
                delivered=False, detail="Object storage is not configured on this deployment."
            )
        try:
            await self._storage.ensure_bucket(self._bucket)
            await self._storage.upload(self._bucket, key, artifact.content, artifact.content_type)
            url = await self._storage.presigned_url(self._bucket, key, self._share_ttl)
        except Exception as exc:
            logger.warning(
                "Object storage delivery failed.",
                extra={"extra_fields": {"key": key, "error": str(exc)}},
            )
            return DeliveryOutcome(delivered=False, detail=f"Object storage upload failed: {exc}")
        return DeliveryOutcome(
            delivered=True,
            detail="Uploaded to object storage.",
            storage_uri=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._share_ttl),
        )


__all__ = ["DeliveryOutcome", "DistributionDispatcher", "new_share_token", "sign_webhook"]

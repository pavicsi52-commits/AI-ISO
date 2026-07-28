"""Archive retention and integrity ("ARCHIVE").

The archive keeps its own copy of the bytes and the checksum rather
than pointing at the live export row. That is what makes it an archive:
regenerating or deleting a report cannot retroactively alter what was
retained, and a compliance auditor is looking at exactly the artifact
that was produced at the time.

Retention is stored **per row**, computed when the artifact is
archived. Deriving it from a global policy at read time would mean
shortening an existing artifact's retention by editing configuration,
which is precisely the silent change an immutable archive exists to
prevent.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import ArchiveStatus
from app.models.report_archive import ReportArchive


def retention_deadline(*, archived_at: datetime, retention_days: int) -> datetime:
    """When an artifact archived at *archived_at* becomes purgeable."""
    return archived_at + timedelta(days=retention_days)


def verify_integrity(archive: ReportArchive) -> bool:
    """Whether the stored bytes still match the stored checksum.

    Recomputed from the content rather than trusted, so tampering with
    the row -- or silent storage corruption -- is detectable. This is
    what "immutable archive" has to mean in practice: not that the
    bytes *cannot* change, but that a change cannot go unnoticed.
    """
    return hashlib.sha256(archive.content).hexdigest() == archive.checksum_sha256


def is_expired(archive: ReportArchive, *, moment: datetime | None = None) -> bool:
    """Whether an archive's retention window has elapsed.

    An archive with no ``retention_until`` is retained indefinitely and
    never reported as expired -- "keep forever" is a legitimate policy
    and must not be mistaken for "expired immediately".
    """
    if archive.retention_until is None:
        return False
    return archive.retention_until <= (moment or datetime.now(UTC))


def ensure_purgeable(archive: ReportArchive, *, moment: datetime | None = None) -> None:
    """Guard a purge against retention policy.

    Raises:
        ConflictError: If the artifact is still within its retention
            window, or has already been purged. Deleting inside the
            retention window is exactly the action the archive exists
            to prevent, so it fails rather than warns.
    """
    status = (
        archive.status
        if isinstance(archive.status, ArchiveStatus)
        else ArchiveStatus(archive.status)
    )
    if status is ArchiveStatus.PURGED:
        raise ConflictError(f"Archive {archive.id!r} has already been purged.")
    if not is_expired(archive, moment=moment):
        until = archive.retention_until.isoformat() if archive.retention_until else "never"
        raise ConflictError(
            f"Archive {archive.id!r} is retained until {until} and cannot be purged yet."
        )


__all__ = [
    "ensure_purgeable",
    "is_expired",
    "retention_deadline",
    "verify_integrity",
]

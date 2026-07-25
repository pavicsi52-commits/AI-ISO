"""Notification attachments.

Per docs/025_Enterprise_Notification_Framework.md.txt "ATTACHMENTS":
PDF, CSV, TXT, JSON, ZIP, Images, Maximum Size Validation, Virus Scan
Hook. The hook is exactly that -- a hook; a real virus scanner is
business/infrastructure integration out of this framework's scope
("DO NOT IMPLEMENT": Business Logic), so :func:`scan_attachment`
defaults to a no-op pass-through when no hook is supplied.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from shared_core.notifications.constants import DEFAULT_MAX_ATTACHMENT_SIZE_BYTES
from shared_core.notifications.exceptions import AttachmentTooLargeError


class AttachmentKind(StrEnum):
    """Every attachment kind docs/025 "ATTACHMENTS" names."""

    PDF = "pdf"
    CSV = "csv"
    TXT = "txt"
    JSON = "json"
    ZIP = "zip"
    IMAGE = "image"


_KIND_BY_EXTENSION: dict[str, AttachmentKind] = {
    "pdf": AttachmentKind.PDF,
    "csv": AttachmentKind.CSV,
    "txt": AttachmentKind.TXT,
    "json": AttachmentKind.JSON,
    "zip": AttachmentKind.ZIP,
    "png": AttachmentKind.IMAGE,
    "jpg": AttachmentKind.IMAGE,
    "jpeg": AttachmentKind.IMAGE,
    "gif": AttachmentKind.IMAGE,
    "webp": AttachmentKind.IMAGE,
}


@dataclass(frozen=True, slots=True)
class Attachment:
    """One file attached to a notification."""

    filename: str
    content_type: str
    kind: AttachmentKind
    data: bytes

    @property
    def size_bytes(self) -> int:
        """The attachment's size, in bytes."""
        return len(self.data)


def kind_from_filename(filename: str) -> AttachmentKind | None:
    """Infer an :class:`AttachmentKind` from *filename*'s extension, if recognized."""
    _, _dot, extension = filename.rpartition(".")
    return _KIND_BY_EXTENSION.get(extension.lower())


def validate_attachment_size(
    attachment: Attachment, *, max_bytes: int = DEFAULT_MAX_ATTACHMENT_SIZE_BYTES
) -> None:
    """Raise :class:`AttachmentTooLargeError` if *attachment* exceeds *max_bytes*."""
    if attachment.size_bytes > max_bytes:
        raise AttachmentTooLargeError(
            f"Attachment {attachment.filename!r} is {attachment.size_bytes} bytes, "
            f"exceeding the {max_bytes}-byte limit."
        )


VirusScanHook = Callable[[Attachment], Awaitable[bool]]


async def scan_attachment(attachment: Attachment, *, hook: VirusScanHook | None = None) -> bool:
    """Run *hook* against *attachment* if supplied ("Virus Scan Hook").

    Returns ``True`` (clean) unconditionally when no hook is configured
    -- this framework provides the integration point, not a scanner.
    """
    if hook is None:
        return True
    return await hook(attachment)


__all__ = [
    "Attachment",
    "AttachmentKind",
    "VirusScanHook",
    "kind_from_filename",
    "scan_attachment",
    "validate_attachment_size",
]

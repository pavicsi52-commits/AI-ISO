"""Avatar upload, replace, delete, resize, and thumbnailing.

Per docs/031 "AVATAR MANAGEMENT": Upload, Replace, Delete, Resize,
Thumbnail, Storage Integration, Validation, Virus Scan Hook. Storage
integration reuses :class:`shared_core.storage.wrapper.StorageWrapper`
(the sanctioned MinIO wrapper, per docs/012 "STORAGE") directly --
nothing else in ``shared_core`` provides image resizing/thumbnailing or
a key-naming convention, so both are implemented here with ``Pillow``.

**Virus Scan Hook, honestly scoped**: like
``shared_core.notifications.attachments``' identically-named hook (the
only other virus-scan pattern in this codebase) and
``shared_core.plugins.sandbox``'s CPU-limit field, this service has no
actual virus scanner of its own -- :data:`VirusScanHook` is a declared
extension point (``Callable[[bytes], Awaitable[bool]]``) a deployment
wires up to a real scanner; with none configured, every upload is
treated as passing (``virus_scan_passed=None`` recorded, not a false
``True``), rather than fabricating a scan that never happened.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image
from shared_core.exceptions.validation import ValidationError
from shared_core.storage import StorageWrapper

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.avatar import UserAvatar
from app.repositories.avatar import UserAvatarRepository

VirusScanHook = Callable[[bytes], Awaitable[bool]]

_ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_THUMBNAIL_SIZE = (128, 128)


class AvatarService:
    """Uploads, replaces, deletes, and thumbnails a user's avatar."""

    def __init__(
        self,
        avatars: UserAvatarRepository,
        storage: StorageWrapper,
        *,
        bucket: str,
        virus_scan_hook: VirusScanHook | None = None,
    ) -> None:
        self._avatars = avatars
        self._storage = storage
        self._bucket = bucket
        self._virus_scan_hook = virus_scan_hook

    async def upload(
        self, user_id: UUID, *, filename: str, content: bytes, content_type: str
    ) -> UserAvatar:
        """Upload a new avatar, replacing any current one ("Upload"/"Replace").

        Raises:
            ValidationError: If the file is too large, an unsupported
                type, not a decodable image, or fails the virus scan.
        """
        self._validate(content, content_type)
        virus_scan_passed = await self._scan(content)

        image = Image.open(BytesIO(content))
        width, height = image.size
        thumbnail = image.copy()
        thumbnail.thumbnail(_THUMBNAIL_SIZE)
        thumbnail_bytes = BytesIO()
        thumbnail.save(thumbnail_bytes, format=image.format or "PNG")

        await self._storage.ensure_bucket(self._bucket)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        base_key = f"avatars/{user_id}/{uuid4().hex}"
        storage_key = f"{base_key}.{extension}"
        thumbnail_key = f"{base_key}_thumb.{extension}"
        await self._storage.upload(self._bucket, storage_key, content, content_type)
        await self._storage.upload(
            self._bucket, thumbnail_key, thumbnail_bytes.getvalue(), content_type
        )

        previous = await self._avatars.get_current_for_user(user_id)
        if previous is not None:
            previous.is_current = False
            previous.replaced_at = datetime.now(UTC)

        return await self._avatars.create(
            UserAvatar(
                user_id=user_id,
                storage_key=storage_key,
                thumbnail_key=thumbnail_key,
                content_type=content_type,
                size_bytes=len(content),
                width=width,
                height=height,
                is_current=True,
                virus_scan_passed=virus_scan_passed,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def delete(self, user_id: UUID) -> None:
        """Delete *user_id*'s current avatar ("Delete")."""
        current = await self._avatars.get_current_for_user(user_id)
        if current is None:
            return
        await self._storage.delete(self._bucket, current.storage_key)
        if current.thumbnail_key is not None:
            await self._storage.delete(self._bucket, current.thumbnail_key)
        current.is_current = False
        current.replaced_at = datetime.now(UTC)

    async def presigned_url(self, avatar: UserAvatar, *, expires_seconds: int = 3600) -> str:
        """A time-limited URL to download *avatar*'s original image."""
        return await self._storage.presigned_url(self._bucket, avatar.storage_key, expires_seconds)

    async def presigned_thumbnail_url(
        self, avatar: UserAvatar, *, expires_seconds: int = 3600
    ) -> str | None:
        """A time-limited URL to download *avatar*'s thumbnail, if one exists."""
        if avatar.thumbnail_key is None:
            return None
        return await self._storage.presigned_url(
            self._bucket, avatar.thumbnail_key, expires_seconds
        )

    def _validate(self, content: bytes, content_type: str) -> None:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValidationError(f"Unsupported avatar content type: {content_type!r}.")
        if len(content) == 0:
            raise ValidationError("Avatar file is empty.")
        if len(content) > _MAX_AVATAR_BYTES:
            raise ValidationError("Avatar file exceeds the 5 MB size limit.")
        try:
            Image.open(BytesIO(content)).verify()
        except Exception as exc:
            raise ValidationError("Avatar file is not a valid image.") from exc

    async def _scan(self, content: bytes) -> bool | None:
        if self._virus_scan_hook is None:
            return None
        passed = await self._virus_scan_hook(content)
        if not passed:
            raise ValidationError("Avatar file failed the virus scan.")
        return True


__all__ = ["AvatarService", "VirusScanHook"]

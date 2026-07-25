"""Tests for :class:`app.storage.avatar_storage.AvatarService`, against real MinIO."""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image
from shared_core.exceptions.validation import ValidationError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.avatar import UserAvatar
from app.models.user import User
from app.repositories.avatar import UserAvatarRepository
from app.repositories.user import UserRepository
from app.storage.avatar_storage import AvatarService

_BUCKET = "test-avatars"


def _png_bytes(*, size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


async def _make_user(session: AsyncSession) -> User:
    return await UserRepository(session).create(
        User(
            username=f"user-{uuid.uuid4().hex[:12]}",
            email=f"user-{uuid.uuid4().hex}@example.com",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )


def _service(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> AvatarService:
    return AvatarService(UserAvatarRepository(db_session), storage_wrapper, bucket=_BUCKET)


async def test_upload_creates_avatar_with_thumbnail(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)

    avatar = await service.upload(
        user.id, filename="avatar.png", content=_png_bytes(), content_type="image/png"
    )

    assert avatar.width == 64
    assert avatar.height == 64
    assert avatar.thumbnail_key is not None
    assert avatar.is_current is True
    url = await service.presigned_url(avatar)
    assert url.startswith("http")
    thumb_url = await service.presigned_thumbnail_url(avatar)
    assert thumb_url is not None


async def test_upload_replaces_previous_avatar(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)
    first = await service.upload(
        user.id, filename="a.png", content=_png_bytes(), content_type="image/png"
    )

    second = await service.upload(
        user.id, filename="b.png", content=_png_bytes(size=(32, 32)), content_type="image/png"
    )

    current = await UserAvatarRepository(db_session).get_current_for_user(user.id)
    assert current is not None
    assert current.id == second.id
    assert first.is_current is False
    assert first.replaced_at is not None


async def test_upload_rejects_unsupported_content_type(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)

    with pytest.raises(ValidationError):
        await service.upload(
            user.id, filename="a.txt", content=b"not an image", content_type="text/plain"
        )


async def test_upload_rejects_empty_file(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)

    with pytest.raises(ValidationError):
        await service.upload(user.id, filename="a.png", content=b"", content_type="image/png")


async def test_upload_rejects_oversized_file(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)
    oversized = b"0" * (5 * 1024 * 1024 + 1)

    with pytest.raises(ValidationError):
        await service.upload(user.id, filename="a.png", content=oversized, content_type="image/png")


async def test_upload_rejects_corrupt_image(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)

    with pytest.raises(ValidationError):
        await service.upload(
            user.id, filename="a.png", content=b"\x89PNGnotreallyapng", content_type="image/png"
        )


async def test_upload_with_failing_virus_scan_raises(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)

    async def _reject(_content: bytes) -> bool:
        return False

    service = AvatarService(
        UserAvatarRepository(db_session), storage_wrapper, bucket=_BUCKET, virus_scan_hook=_reject
    )

    with pytest.raises(ValidationError):
        await service.upload(
            user.id, filename="a.png", content=_png_bytes(), content_type="image/png"
        )


async def test_upload_with_passing_virus_scan_records_true(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)

    async def _accept(_content: bytes) -> bool:
        return True

    service = AvatarService(
        UserAvatarRepository(db_session), storage_wrapper, bucket=_BUCKET, virus_scan_hook=_accept
    )

    avatar = await service.upload(
        user.id, filename="a.png", content=_png_bytes(), content_type="image/png"
    )

    assert avatar.virus_scan_passed is True


async def test_delete_removes_current_avatar(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)
    await service.upload(user.id, filename="a.png", content=_png_bytes(), content_type="image/png")

    await service.delete(user.id)

    assert await UserAvatarRepository(db_session).get_current_for_user(user.id) is None


async def test_delete_with_no_avatar_is_a_no_op(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    user = await _make_user(db_session)
    service = _service(db_session, storage_wrapper)

    await service.delete(user.id)


async def test_presigned_thumbnail_url_returns_none_without_thumbnail(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _service(db_session, storage_wrapper)
    avatar = UserAvatar(
        user_id=uuid.uuid4(),
        storage_key="k",
        thumbnail_key=None,
        content_type="image/png",
        size_bytes=1,
        organization_id=DEFAULT_ORGANIZATION_ID,
    )

    assert await service.presigned_thumbnail_url(avatar) is None

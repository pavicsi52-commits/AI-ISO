"""Tests for structural interfaces (Protocols)."""

from __future__ import annotations

from uuid import UUID, uuid4

from shared_core.interfaces import (
    EventPublisherProtocol,
    QueueProtocol,
    RepositoryProtocol,
    ServiceProtocol,
    StorageProtocol,
    ValidatorProtocol,
)
from shared_core.validators.results import ValidationResult


class _FakeRepository:
    async def get_by_id(self, entity_id: UUID) -> dict | None:
        return {"id": str(entity_id)}

    async def create(self, entity: dict) -> dict:
        return entity

    async def update(self, entity: dict) -> dict:
        return entity

    async def delete(self, entity_id: UUID) -> None:
        return None

    async def exists(self, entity_id: UUID) -> bool:
        return True


class _FakePublisher:
    async def publish(self, event_name: str, payload: dict) -> None:
        return None


class _FakeQueue:
    async def enqueue(self, queue_name: str, message: dict) -> None:
        return None

    async def dequeue(self, queue_name: str) -> dict | None:
        return None


class _FakeStorage:
    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        return b""

    async def delete(self, bucket: str, key: str) -> None:
        return None

    async def presigned_url(self, bucket: str, key: str, expires_seconds: int) -> str:
        return f"https://storage/{bucket}/{key}"


class _FakeValidator:
    def validate(self, value: str) -> ValidationResult:
        return ValidationResult.ok()


class _NotARepository:
    pass


def test_repository_protocol_is_structurally_satisfied() -> None:
    assert isinstance(_FakeRepository(), RepositoryProtocol)
    assert not isinstance(_NotARepository(), RepositoryProtocol)


def test_service_protocol_requires_matching_methods() -> None:
    class _FakeService:
        async def get(self, entity_id: UUID) -> dict:
            return {}

        async def create(self, payload: dict) -> dict:
            return payload

        async def update(self, entity_id: UUID, payload: dict) -> dict:
            return payload

        async def delete(self, entity_id: UUID) -> None:
            return None

    assert isinstance(_FakeService(), ServiceProtocol)


def test_event_publisher_protocol() -> None:
    assert isinstance(_FakePublisher(), EventPublisherProtocol)


def test_queue_protocol() -> None:
    assert isinstance(_FakeQueue(), QueueProtocol)


def test_storage_protocol() -> None:
    assert isinstance(_FakeStorage(), StorageProtocol)


async def test_fake_repository_behaves_as_expected() -> None:
    repo = _FakeRepository()
    entity_id = uuid4()

    result = await repo.get_by_id(entity_id)

    assert result == {"id": str(entity_id)}


def test_validator_protocol() -> None:
    assert isinstance(_FakeValidator(), ValidatorProtocol)

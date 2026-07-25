"""Tests ``SecretService.rotate``'s "Failure Recovery" path -- a failed
rotation attempt must be recorded (outcome=FAILED) and the original
exception re-raised, never silently swallowed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import RotationOutcome, SecretType
from app.repositories.secret_rotation import SecretRotationRepository
from tests.conftest import build_secret_service


async def test_rotate_records_failure_and_reraises(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = build_secret_service(db_session, envelope)
    owner_id = uuid.uuid4()
    secret = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="rotation-failure",
        description=None,
        category_id=None,
        secret_type=SecretType.PASSWORD,
        owner_id=owner_id,
        value="original-value",
        expires_at=None,
        rotation_policy={},
        metadata={},
        tags=[],
    )

    service._versions.create_version = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("simulated encryption backend outage")
    )

    with pytest.raises(RuntimeError, match="simulated encryption backend outage"):
        await service.rotate(secret.id, new_value="new-value", rotated_by=owner_id)

    history = await SecretRotationRepository(db_session).list_for_secret(secret.id)
    assert len(history) == 1
    assert history[0].outcome == RotationOutcome.FAILED
    assert history[0].error_message == "simulated encryption backend outage"
    assert history[0].new_version_number is None

    # The secret's own current_version must be untouched by the failed attempt.
    refreshed = await service.get_by_id(secret.id)
    assert refreshed.current_version == 1

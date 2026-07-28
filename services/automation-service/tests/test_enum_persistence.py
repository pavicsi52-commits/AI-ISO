"""Regression tests for enum columns read back from the database.

``AutomationTarget.connector_type`` is annotated
``Mapped[ConnectorType]`` but stored in a plain ``String(24)`` column,
so SQLAlchemy returns a raw ``str`` for any row loaded from Postgres.
An ``is`` comparison against an enum member is ``False`` for every such
row.

That hid a live bug: :func:`_dispatch_remote` rejected *every* stored
target with "no concrete provider registered", including correctly
configured SSH ones, so remote execution could not work at all in
production. ``tests/test_execution_dispatcher.py`` did not catch it
because it builds its target in memory, where the attribute really is
an enum.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatchers.execution_dispatcher import _connector_type_of
from app.models.automation_target import AutomationTarget
from app.models.enums import ConnectorType, ExecutionTargetType


async def _persisted_target(
    db_session: AsyncSession, connector_type: ConnectorType
) -> AutomationTarget:
    """Store a target, then force a genuine reload from Postgres."""
    target = AutomationTarget(
        organization_id=uuid.uuid4(),
        name=f"target-{uuid.uuid4().hex[:8]}",
        target_type=ExecutionTargetType.PHYSICAL_SERVER,
        connector_type=connector_type,
        address="10.0.0.1",
        port=22,
        username="root",
    )
    db_session.add(target)
    await db_session.flush()
    # Refreshing re-SELECTs the row, which is what makes the stored
    # (string) representation visible. ``expire()`` would defer the
    # load to attribute access, which cannot do async I/O.
    await db_session.refresh(target)
    return target


class TestConnectorTypeRoundTrip:
    async def test_stored_connector_type_really_is_a_plain_string(
        self, db_session: AsyncSession
    ) -> None:
        """Documents the root cause this module guards against."""
        target = await _persisted_target(db_session, ConnectorType.SSH)
        assert not isinstance(target.connector_type, ConnectorType)
        assert target.connector_type == ConnectorType.SSH

    async def test_ssh_target_is_recognised_after_a_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        """The live bug: every stored SSH target failed this check."""
        target = await _persisted_target(db_session, ConnectorType.SSH)
        assert _connector_type_of(target) is ConnectorType.SSH

    @pytest.mark.parametrize(
        "connector_type",
        [connector for connector in ConnectorType if connector is not ConnectorType.SSH],
    )
    async def test_non_ssh_targets_stay_unsupported(
        self, db_session: AsyncSession, connector_type: ConnectorType
    ) -> None:
        """The guard must keep rejecting what genuinely has no provider."""
        target = await _persisted_target(db_session, connector_type)
        assert _connector_type_of(target) is not ConnectorType.SSH

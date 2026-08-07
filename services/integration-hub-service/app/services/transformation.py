"""Connector transformation rule management (docs/058 "DATA TRANSFORMATION")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import DataFormat, TransformationKind
from app.models.transformation import ConnectorTransformation
from app.repositories.transformation import ConnectorTransformationRepository
from app.transformations import engine as transformations_engine


class TransformationService:
    """A connector's own payload-shaping rule set."""

    def __init__(self, transformations: ConnectorTransformationRepository) -> None:
        self._transformations = transformations

    async def create(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID,
        name: str,
        kind: TransformationKind,
        source_format: DataFormat = DataFormat.JSON,
        target_format: DataFormat = DataFormat.JSON,
        config: dict[str, Any] | None = None,
        priority: int = 100,
    ) -> ConnectorTransformation:
        """Register a new transformation rule for one connector."""
        return await self._transformations.create(
            ConnectorTransformation(
                organization_id=organization_id,
                connector_id=connector_id,
                name=name,
                kind=kind,
                source_format=source_format,
                target_format=target_format,
                config=dict(config or {}),
                priority=priority,
            )
        )

    async def get(self, organization_id: UUID, transformation_id: UUID) -> ConnectorTransformation:
        """One transformation.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._transformations.require_in_org(organization_id, transformation_id)

    async def list_for_connector(
        self, connector_id: UUID, *, enabled: bool | None = None
    ) -> list[ConnectorTransformation]:
        """Every transformation attached to one connector, in priority order."""
        return await self._transformations.list_for_connector(connector_id, enabled=enabled)

    async def apply_all(self, connector_id: UUID, data: Any) -> Any:
        """Run *data* through every enabled transformation attached to *connector_id*, in order."""
        rules = await self.list_for_connector(connector_id, enabled=True)
        result = data
        for rule in rules:
            result = transformations_engine.apply_transformation(
                result, kind=rule.kind, config=rule.config
            )
        return result


__all__ = ["TransformationService"]

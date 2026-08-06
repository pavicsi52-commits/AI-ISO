"""Webhook payload/header transformation management (docs/057 "PAYLOAD TRANSFORMATION")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import TransformationKind
from app.models.transformation import WebhookTransformation
from app.repositories.transformation import WebhookTransformationRepository
from app.transformations import engine as transformations_engine


class TransformationService:
    """An endpoint's own outbound-payload transformation rules."""

    def __init__(self, transformations: WebhookTransformationRepository) -> None:
        self._transformations = transformations

    async def create(
        self,
        organization_id: UUID,
        *,
        endpoint_id: UUID,
        name: str,
        kind: TransformationKind,
        config: dict[str, Any] | None = None,
        priority: int = 100,
    ) -> WebhookTransformation:
        """Register a new transformation rule."""
        return await self._transformations.create(
            WebhookTransformation(
                organization_id=organization_id,
                endpoint_id=endpoint_id,
                name=name,
                kind=kind,
                config=dict(config or {}),
                priority=priority,
            )
        )

    async def get(self, organization_id: UUID, transformation_id: UUID) -> WebhookTransformation:
        """One transformation rule.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._transformations.require_in_org(organization_id, transformation_id)

    async def list_for_endpoint(self, endpoint_id: UUID) -> list[WebhookTransformation]:
        """Every enabled transformation rule attached to one endpoint, in priority order."""
        return await self._transformations.list_for_endpoint(endpoint_id)

    @staticmethod
    def apply_all(
        rules: list[WebhookTransformation],
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Apply every rule to *payload*/*headers*, in priority order."""
        for rule in rules:
            kind = TransformationKind(rule.kind)
            if kind == TransformationKind.HEADER_MAPPING:
                headers = transformations_engine.apply_header_mapping(headers, rule.config)
            else:
                payload = transformations_engine.apply_transformation(
                    payload, kind=kind, config=rule.config
                )
        return payload, headers


__all__ = ["TransformationService"]

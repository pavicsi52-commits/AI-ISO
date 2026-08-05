"""Request/response transformation rule management and application."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import TransformationDirection, TransformationKind
from app.models.transformation import ApiTransformationRule
from app.repositories.transformation import ApiTransformationRuleRepository
from app.transform import engine as transform_engine


class TransformationService:
    """Transformation rules: configuration and application."""

    def __init__(self, rules: ApiTransformationRuleRepository) -> None:
        self._rules = rules

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        kind: TransformationKind,
        direction: TransformationDirection = TransformationDirection.REQUEST,
        config: dict[str, Any] | None = None,
        route_id: UUID | None = None,
        priority: int = 100,
    ) -> ApiTransformationRule:
        """Register a new transformation rule."""
        return await self._rules.create(
            ApiTransformationRule(
                organization_id=organization_id,
                route_id=route_id,
                name=name,
                kind=kind,
                direction=direction,
                config=dict(config or {}),
                priority=priority,
            )
        )

    async def list_for_route(
        self, organization_id: UUID, route_id: UUID | None
    ) -> list[ApiTransformationRule]:
        """Every enabled rule applying to *route_id* (global rules plus route-specific ones)."""
        return await self._rules.list_for_route(organization_id, route_id)

    @staticmethod
    def apply_request(
        rules: list[ApiTransformationRule],
        *,
        headers: dict[str, str],
        path: str,
        body: dict[str, Any] | None,
    ) -> tuple[dict[str, str], str, dict[str, Any] | None]:
        """Apply every enabled ``REQUEST``-direction rule, in priority order."""
        for rule in rules:
            if rule.direction != TransformationDirection.REQUEST:
                continue
            if rule.kind == TransformationKind.HEADER:
                headers = transform_engine.apply_header_transform(headers, rule.config)
            elif rule.kind == TransformationKind.URL_REWRITE:
                path = transform_engine.apply_url_rewrite(path, rule.config)
            elif rule.kind == TransformationKind.BODY and body is not None:
                body = transform_engine.apply_body_transform(body, rule.config)
        return headers, path, body

    @staticmethod
    def apply_response(
        rules: list[ApiTransformationRule], *, headers: dict[str, str], body: dict[str, Any] | None
    ) -> tuple[dict[str, str], dict[str, Any] | None]:
        """Apply every enabled ``RESPONSE``-direction rule, in priority order."""
        for rule in rules:
            if rule.direction != TransformationDirection.RESPONSE:
                continue
            if rule.kind == TransformationKind.HEADER:
                headers = transform_engine.apply_header_transform(headers, rule.config)
            elif (
                rule.kind in (TransformationKind.RESPONSE_MAPPING, TransformationKind.BODY)
                and body is not None
            ):
                body = transform_engine.apply_body_transform(body, rule.config)
        return headers, body


__all__ = ["TransformationService"]

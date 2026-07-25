"""TOSCA template components.

Per docs/039 "TOSCA INTEGRATION" "Integrate". Every create is validated
against its declared :class:`~app.models.enums.ToscaComponentType`
shape via :func:`app.tosca.validator.validate_tosca_content_or_raise`
before persistence.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.configuration_tosca_template import ConfigurationToscaTemplate
from app.models.enums import ToscaComponentType
from app.repositories.configuration_tosca_template import ConfigurationToscaTemplateRepository
from app.tosca.validator import ToscaValidationError, validate_tosca_content_or_raise


class ConfigurationToscaService:
    """Creates, reads, and lists TOSCA template components."""

    def __init__(self, templates: ConfigurationToscaTemplateRepository) -> None:
        self._templates = templates

    async def get_by_id(self, template_id: UUID) -> ConfigurationToscaTemplate:
        """Return the TOSCA template identified by *template_id*.

        Raises:
            NotFoundError: If no such template exists.
        """
        return await self._templates.require_by_id(template_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationToscaTemplate]:
        """Every TOSCA template component backing *profile_id*."""
        return await self._templates.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID | None,
        component_type: ToscaComponentType,
        name: str,
        content: dict[str, Any],
        csar_url: str | None,
    ) -> ConfigurationToscaTemplate:
        """Define a new TOSCA template component.

        Raises:
            ValidationError: If *content* does not match the shape
                *component_type* requires.
        """
        try:
            validate_tosca_content_or_raise(component_type, content)
        except ToscaValidationError as exc:
            raise ValidationError(str(exc)) from exc
        return await self._templates.create(
            ConfigurationToscaTemplate(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                component_type=component_type,
                name=name,
                content=content,
                csar_url=csar_url,
            )
        )

    async def delete(self, template_id: UUID) -> None:
        """Soft-delete a TOSCA template component."""
        await self._templates.delete(template_id)


__all__ = ["ConfigurationToscaService"]

"""Framework and control management.

The authoring half: what an organization is measured against, and how
those measures relate to each other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.frameworks.builtin import BUILTIN_FRAMEWORKS, BUILTIN_MAPPINGS, FrameworkTemplate
from app.models.enums import (
    ControlCategory,
    ControlRelationKind,
    ControlSeverity,
    ControlStatus,
    FrameworkCode,
    FrameworkKind,
    FrameworkStatus,
    control_status_of,
    framework_status_of,
)
from app.models.framework import ComplianceControl, ComplianceFramework, ControlMapping
from app.repositories.catalogue import (
    ControlMappingRepository,
    ControlRepository,
    FrameworkRepository,
)
from app.rules.engine import Rule, rule_from_dict, rule_to_dict, validate_rule

logger = get_logger("app.services.catalogue")

_TERMINAL_FRAMEWORK_STATUSES = frozenset({FrameworkStatus.ARCHIVED})


class CatalogueService:
    """Frameworks, controls, and the mappings between them."""

    def __init__(
        self,
        frameworks: FrameworkRepository,
        controls: ControlRepository,
        mappings: ControlMappingRepository,
    ) -> None:
        self._frameworks = frameworks
        self._controls = controls
        self._mappings = mappings

    # ---- frameworks ---------------------------------------------------

    async def create_framework(
        self,
        organization_id: UUID,
        *,
        slug: str,
        name: str,
        code: FrameworkCode = FrameworkCode.CUSTOM,
        kind: FrameworkKind = FrameworkKind.CUSTOM,
        description: str | None = None,
        publisher: str | None = None,
        framework_version: str = "1.0.0",
        reference_url: str | None = None,
        weight: float = 1.0,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceFramework:
        """Register a framework.

        Raises:
            ConflictError: If the slug is already taken here.
        """
        if await self._frameworks.get_by_slug(organization_id, slug):
            raise ConflictError(f"A framework with slug {slug!r} already exists.")
        return await self._frameworks.create(
            ComplianceFramework(
                organization_id=organization_id,
                slug=slug,
                name=name,
                description=description,
                code=code,
                kind=kind,
                status=FrameworkStatus.DRAFT,
                publisher=publisher,
                framework_version=framework_version,
                reference_url=reference_url,
                weight=weight,
                tags=list(tags or []),
                created_by=actor_id,
            )
        )

    async def get_framework(self, organization_id: UUID, framework_id: UUID) -> ComplianceFramework:
        """One framework.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._frameworks.require_in_org(organization_id, framework_id)

    async def list_frameworks(
        self,
        organization_id: UUID,
        *,
        status: FrameworkStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceFramework]:
        """Frameworks, newest first."""
        return await self._frameworks.list_for_org(
            organization_id, status=status, limit=limit, offset=offset
        )

    async def update_framework(
        self,
        organization_id: UUID,
        framework_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        status: FrameworkStatus | None = None,
        weight: float | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceFramework:
        """Change a framework's metadata.

        Raises:
            ConflictError: If it is built-in. A shipped framework whose
                controls an organization had reworded would report
                against something that is not the standard while still
                calling it by the standard's name -- which is worse than
                not tracking it, because the report would be believed.
        """
        stored = await self._frameworks.require_in_org(organization_id, framework_id)
        if stored.is_builtin and (name is not None or description is not None):
            raise ConflictError(
                f"Framework {stored.slug!r} ships with the platform and its identity "
                "cannot be edited. Create a custom framework to express a local "
                "interpretation."
            )
        if name is not None:
            stored.name = name
        if description is not None:
            stored.description = description
        if status is not None:
            stored.status = status
        if weight is not None:
            stored.weight = weight
        if tags is not None:
            stored.tags = list(tags)
        stored.updated_by = actor_id
        return await self._frameworks.update(stored)

    async def archive_framework(
        self, organization_id: UUID, framework_id: UUID, *, actor_id: UUID | None = None
    ) -> ComplianceFramework:
        """Take a framework out of scoring.

        Archived rather than deleted, because every historical finding,
        result, and score points at it -- and a report from last quarter
        that cannot name the framework it measured is not a report.
        """
        stored = await self._frameworks.require_in_org(organization_id, framework_id)
        if framework_status_of(stored) in _TERMINAL_FRAMEWORK_STATUSES:
            raise ConflictError(f"Framework {stored.slug!r} is already archived.")
        stored.status = FrameworkStatus.ARCHIVED
        stored.updated_by = actor_id
        return await self._frameworks.update(stored)

    # ---- controls -----------------------------------------------------

    async def create_control(
        self,
        organization_id: UUID,
        framework_id: UUID,
        *,
        code: str,
        title: str,
        description: str | None = None,
        guidance: str | None = None,
        category: ControlCategory = ControlCategory.OTHER,
        severity: ControlSeverity = ControlSeverity.MEDIUM,
        status: ControlStatus = ControlStatus.NOT_IMPLEMENTED,
        owner_id: str | None = None,
        owner_team: str | None = None,
        rule: Rule | None = None,
        remediation_guidance: str | None = None,
        references: list[str] | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceControl:
        """Add a control to a framework.

        Raises:
            ConflictError: If the code is already used in this framework.
            ValidationError: If the rule cannot be evaluated meaningfully.
        """
        await self._frameworks.require_in_org(organization_id, framework_id)
        if await self._controls.get_by_code(organization_id, framework_id, code):
            raise ConflictError(f"Control {code!r} already exists in this framework.")
        if rule is not None:
            validate_rule(rule)

        created = await self._controls.create(
            ComplianceControl(
                organization_id=organization_id,
                framework_id=framework_id,
                code=code,
                title=title,
                description=description,
                guidance=guidance,
                category=category,
                severity=severity,
                status=status,
                owner_id=owner_id,
                owner_team=owner_team,
                is_automatable=rule is not None,
                rule=rule_to_dict(rule) if rule is not None else {},
                remediation_guidance=remediation_guidance,
                references=list(references or []),
                tags=list(tags or []),
                created_by=actor_id,
            )
        )
        await self._frameworks.refresh_control_count(organization_id, framework_id)
        return created

    async def get_control(self, organization_id: UUID, control_id: UUID) -> ComplianceControl:
        """One control.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._controls.require_in_org(organization_id, control_id)

    async def list_controls(
        self,
        organization_id: UUID,
        *,
        framework_id: UUID | None = None,
        category: ControlCategory | None = None,
        severity: ControlSeverity | None = None,
        status: ControlStatus | None = None,
        owner_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceControl]:
        """Controls matching a caller's filters."""
        return await self._controls.list_filtered(
            organization_id,
            framework_id=framework_id,
            category=category,
            severity=severity,
            status=status,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

    async def update_control(
        self,
        organization_id: UUID,
        control_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        severity: ControlSeverity | None = None,
        status: ControlStatus | None = None,
        owner_id: str | None = None,
        owner_team: str | None = None,
        remediation_guidance: str | None = None,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceControl:
        """Change a control's metadata or ownership.

        A built-in control's *text* is not editable, but its status,
        owner, and severity are: those are statements about this
        organization's programme rather than about the standard, and
        scoping a control out or assigning it to a team is exactly what
        an organization is supposed to do with a shipped catalogue.
        """
        stored = await self._controls.require_in_org(organization_id, control_id)
        if stored.is_builtin and (title is not None or description is not None):
            raise ConflictError(
                f"Control {stored.code!r} ships with the platform; its wording comes "
                "from the standard and cannot be edited. Status, ownership, and "
                "severity are yours to set."
            )
        if title is not None:
            stored.title = title
        if description is not None:
            stored.description = description
        if severity is not None:
            stored.severity = severity
        if status is not None:
            stored.status = status
        if owner_id is not None:
            stored.owner_id = owner_id
        if owner_team is not None:
            stored.owner_team = owner_team
        if remediation_guidance is not None:
            stored.remediation_guidance = remediation_guidance
        if tags is not None:
            stored.tags = list(tags)
        stored.updated_by = actor_id
        return await self._controls.update(stored)

    async def set_control_rule(
        self,
        organization_id: UUID,
        control_id: UUID,
        rule: Rule,
        *,
        actor_id: UUID | None = None,
    ) -> ComplianceControl:
        """Give a control a machine-checkable rule.

        Validated **before** the existing rule is replaced. Writing the
        new rule and then discovering it is malformed would leave the
        control with nothing evaluable while still flagged automatable
        -- which reports ``NOT_ASSESSED`` forever while looking
        configured.

        Raises:
            ConflictError: If the control ships with the platform.
            ValidationError: If the rule would pass everything, nest too
                deep, or name a path that cannot address anything.
        """
        stored = await self._controls.require_in_org(organization_id, control_id)
        if stored.is_builtin:
            raise ConflictError(
                f"Control {stored.code!r} ships with the platform and its rule is part "
                "of what the platform asserts about the standard."
            )
        validate_rule(rule)
        stored.rule = rule_to_dict(rule)
        stored.is_automatable = True
        stored.control_version += 1
        stored.updated_by = actor_id
        return await self._controls.update(stored)

    async def load_control_rule(self, control: ComplianceControl) -> Rule | None:
        """Rebuild a control's rule from its stored form.

        Raises:
            ValidationError: If the stored rule names an operator that no
                longer exists.
        """
        return rule_from_dict(control.rule, name=control.code) if control.rule else None

    # ---- mappings -----------------------------------------------------

    async def map_controls(
        self,
        organization_id: UUID,
        *,
        source_control_id: UUID,
        target_control_id: UUID,
        relation: ControlRelationKind = ControlRelationKind.EQUIVALENT_TO,
        confidence: float = 1.0,
        note: str | None = None,
        actor_id: UUID | None = None,
    ) -> ControlMapping:
        """Record that two controls ask related questions.

        Raises:
            ValidationError: If a control is mapped to itself. A
                self-mapping is not merely useless -- it makes a control
                appear twice in any coverage count that follows the
                mapping graph, which inflates exactly the number the
                graph exists to compute.
            ConflictError: If the same directed mapping already exists.
        """
        if source_control_id == target_control_id:
            raise ValidationError(
                "A control cannot be mapped to itself; that would count it twice in "
                "every coverage calculation that follows mappings."
            )
        await self._controls.require_in_org(organization_id, source_control_id)
        await self._controls.require_in_org(organization_id, target_control_id)
        if await self._mappings.get_pair(organization_id, source_control_id, target_control_id):
            raise ConflictError("These two controls are already mapped.")

        return await self._mappings.create(
            ControlMapping(
                organization_id=organization_id,
                source_control_id=source_control_id,
                target_control_id=target_control_id,
                relation=relation,
                confidence=confidence,
                note=note,
                created_by=actor_id,
            )
        )

    async def related_controls(
        self, organization_id: UUID, control_id: UUID
    ) -> list[dict[str, Any]]:
        """Every control this one is mapped to, in either direction."""
        mappings = await self._mappings.list_for_control(organization_id, control_id)
        related: list[dict[str, Any]] = []
        for mapping in mappings:
            other_id = (
                mapping.target_control_id
                if mapping.source_control_id == control_id
                else mapping.source_control_id
            )
            related.append(
                {
                    "mapping_id": str(mapping.id),
                    "control_id": str(other_id),
                    "relation": str(mapping.relation),
                    "confidence": mapping.confidence,
                    "note": mapping.note,
                }
            )
        return related

    # ---- seeding ------------------------------------------------------

    async def seed_builtin(
        self, organization_id: UUID, *, actor_id: UUID | None = None
    ) -> list[ComplianceFramework]:
        """Install the shipped frameworks, controls, and mappings.

        Idempotent by slug, so re-running adds only what is missing
        rather than duplicating. Seeded **ACTIVE**: a framework sitting
        in draft is a framework that is not measuring anything, and an
        organization that has asked for CIS wants CIS now.
        """
        created: list[ComplianceFramework] = []
        for template in BUILTIN_FRAMEWORKS:
            if await self._frameworks.get_by_slug(organization_id, template.slug):
                continue
            created.append(await self._seed_framework(organization_id, template, actor_id))

        if created:
            await self._seed_mappings(organization_id, actor_id)
            logger.info(
                "Seeded built-in compliance frameworks for an organization.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "seeded": [one.slug for one in created],
                    }
                },
            )
        return created

    async def _seed_framework(
        self, organization_id: UUID, template: FrameworkTemplate, actor_id: UUID | None
    ) -> ComplianceFramework:
        """Install one shipped framework and all its controls."""
        framework = await self._frameworks.create(
            ComplianceFramework(
                organization_id=organization_id,
                slug=template.slug,
                name=template.name,
                description=template.description,
                code=template.code,
                kind=template.kind,
                status=FrameworkStatus.ACTIVE,
                publisher=template.publisher,
                framework_version=template.framework_version,
                reference_url=template.reference_url,
                weight=template.weight,
                is_builtin=True,
                tags=list(template.tags),
                control_count=len(template.controls),
                created_by=actor_id,
            )
        )
        for one in template.controls:
            await self._controls.create(
                ComplianceControl(
                    organization_id=organization_id,
                    framework_id=framework.id,
                    code=one.code,
                    title=one.title,
                    description=one.description,
                    guidance=one.guidance or None,
                    category=one.category,
                    severity=one.severity,
                    status=ControlStatus.NOT_IMPLEMENTED,
                    is_builtin=True,
                    is_automatable=True,
                    rule=rule_to_dict(one.rule),
                    remediation_guidance=one.remediation_guidance or None,
                    references=list(one.references),
                    created_by=actor_id,
                )
            )
        return framework

    async def _seed_mappings(self, organization_id: UUID, actor_id: UUID | None) -> None:
        """Install the shipped cross-framework mappings.

        Skips any whose endpoints are not both present -- an organization
        that seeded only some frameworks should get the mappings that
        apply to what it has, not an error about the ones it does not.
        """
        for mapping in BUILTIN_MAPPINGS:
            source_framework = await self._frameworks.get_by_slug(
                organization_id, mapping.source_framework
            )
            target_framework = await self._frameworks.get_by_slug(
                organization_id, mapping.target_framework
            )
            if source_framework is None or target_framework is None:
                continue
            source = await self._controls.get_by_code(
                organization_id, source_framework.id, mapping.source_code
            )
            target = await self._controls.get_by_code(
                organization_id, target_framework.id, mapping.target_code
            )
            if source is None or target is None:
                continue
            if await self._mappings.get_pair(organization_id, source.id, target.id):
                continue
            await self._mappings.create(
                ControlMapping(
                    organization_id=organization_id,
                    source_control_id=source.id,
                    target_control_id=target.id,
                    relation=mapping.relation,
                    confidence=mapping.confidence,
                    note=mapping.note or None,
                    created_by=actor_id,
                )
            )

    async def implementation_summary(self, organization_id: UUID) -> dict[str, Any]:
        """How far through its programme an organization is.

        Reports implemented-over-applicable rather than
        implemented-over-total. A control formally scoped out is not
        outstanding work, and counting it as such makes a finished
        programme look permanently incomplete -- which is how a useful
        number becomes one people stop looking at.
        """
        counts = await self._controls.count_by_status(organization_id)
        total = sum(counts.values())
        not_applicable = counts.get(str(ControlStatus.NOT_APPLICABLE), 0)
        applicable = total - not_applicable
        implemented = counts.get(str(ControlStatus.IMPLEMENTED), 0)
        return {
            "total": total,
            "applicable": applicable,
            "not_applicable": not_applicable,
            "implemented": implemented,
            "implementation_rate": (
                round(implemented / applicable * 100.0, 2) if applicable else 0.0
            ),
            "by_status": counts,
        }

    @staticmethod
    def status_of(control: ComplianceControl) -> ControlStatus:
        """A control's status as a genuine enum member."""
        return control_status_of(control.status)

    @staticmethod
    def now() -> datetime:
        """The current moment, timezone-aware."""
        return datetime.now(UTC)


__all__ = ["CatalogueService"]

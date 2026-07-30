"""Policy authoring: create, edit, publish, roll back.

**Publishing is the only thing that changes live authorization.** Every
edit here writes to the authored tables and leaves ``compiled_rule``
alone; a decision keeps using whatever was last published. That gap is
the review window, and collapsing it -- by compiling on every edit --
would make each keystroke in a policy editor a change to production
authorization.

**Rollback restores a stored version, it does not reconstruct one.**
``policy_versions`` holds exactly what was live, so rolling back points
at a row rather than replaying a change log and hoping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.policy_events import (
    SOURCE_SERVICE,
    PolicyCreatedEvent,
    PolicyPublishedEvent,
    PolicyUpdatedEvent,
)
from app.guardrails.builtin import BUILTIN_GUARDRAILS, GuardrailTemplate
from app.models.enums import (
    AttributeSource,
    LogicalOperator,
    PolicyCategory,
    PolicyEffect,
    PolicyStatus,
    PolicyType,
    RuleOperator,
)
from app.models.policy import Policy, PolicyVersion
from app.models.rule import PolicyCondition, PolicyRule
from app.publishing.compiler import (
    checksum,
    compile_policy,
    next_version,
    verify_integrity,
)
from app.repositories.policy import (
    PolicyConditionRepository,
    PolicyRepository,
    PolicyRuleRepository,
    PolicyVersionRepository,
)
from app.rules.engine import Rule, validate_rule
from app.types import EventPublisher

logger = get_logger("app.services.policy")

_TERMINAL_STATUSES: frozenset[PolicyStatus] = frozenset({PolicyStatus.ARCHIVED})

_ALLOWED_TRANSITIONS: dict[PolicyStatus, frozenset[PolicyStatus]] = {
    PolicyStatus.DRAFT: frozenset({PolicyStatus.REVIEW, PolicyStatus.ARCHIVED}),
    PolicyStatus.REVIEW: frozenset(
        {PolicyStatus.DRAFT, PolicyStatus.APPROVED, PolicyStatus.ARCHIVED}
    ),
    PolicyStatus.APPROVED: frozenset(
        {PolicyStatus.PUBLISHED, PolicyStatus.DRAFT, PolicyStatus.ARCHIVED}
    ),
    PolicyStatus.PUBLISHED: frozenset({PolicyStatus.ARCHIVED, PolicyStatus.DRAFT}),
    PolicyStatus.ARCHIVED: frozenset({PolicyStatus.DRAFT}),
}
"""Which lifecycle moves are legal.

A table rather than a free-for-all, because the one move that must be
impossible is DRAFT straight to PUBLISHED. The review states exist so
that somebody other than the author looks at a rule before it starts
refusing people's work; letting a draft publish itself deletes the whole
point of having them.
"""


def status_of(record: Policy) -> PolicyStatus:
    """A policy's status as a genuine enum member.

    ``status`` is annotated ``Mapped[PolicyStatus]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = record.status
    return value if isinstance(value, PolicyStatus) else PolicyStatus(value)


def effect_of(record: Policy) -> PolicyEffect:
    """A policy's effect as a genuine enum member."""
    value = record.effect
    return value if isinstance(value, PolicyEffect) else PolicyEffect(value)


class PolicyService:
    """Creates, edits, publishes, and rolls back policies."""

    def __init__(
        self,
        policies: PolicyRepository,
        rules: PolicyRuleRepository,
        conditions: PolicyConditionRepository,
        versions: PolicyVersionRepository,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._policies = policies
        self._rules = rules
        self._conditions = conditions
        self._versions = versions
        self._publish_event = publish_event

    # ---- catalogue ----------------------------------------------------

    async def list_policies(
        self,
        organization_id: UUID,
        *,
        status: PolicyStatus | None = None,
        category: PolicyCategory | None = None,
        policy_type: PolicyType | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Policy]:
        """Policies for one organization."""
        return await self._policies.list_for_org(
            organization_id,
            status=status,
            category=category,
            policy_type=policy_type,
            limit=limit,
            offset=offset,
        )

    async def get_policy(self, organization_id: UUID, policy_id: UUID) -> Policy:
        """One policy by id.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        return await self._policies.require_in_org(organization_id, policy_id)

    async def create_policy(
        self,
        organization_id: UUID,
        *,
        slug: str,
        name: str,
        effect: PolicyEffect,
        category: PolicyCategory = PolicyCategory.AUTHORIZATION,
        policy_type: PolicyType = PolicyType.RBAC,
        description: str | None = None,
        priority: int = 100,
        subject_types: list[str] | None = None,
        resource_types: list[str] | None = None,
        actions: list[str] | None = None,
        obligations: dict[str, Any] | None = None,
        risk_weight: float = 0.0,
        tags: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> Policy:
        """Create a policy in DRAFT.

        Always DRAFT, whatever the caller asks for. A policy that could
        be created already published would let the whole review pipeline
        be bypassed by one extra field on a create call.

        Raises:
            ConflictError: If the slug is already used.
        """
        if await self._policies.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"A policy with slug {slug!r} already exists.")

        stored = await self._policies.create(
            Policy(
                organization_id=organization_id,
                slug=slug,
                name=name,
                description=description,
                category=category,
                policy_type=policy_type,
                effect=effect,
                status=PolicyStatus.DRAFT,
                priority=priority,
                subject_types=subject_types or [],
                resource_types=resource_types or [],
                actions=actions or [],
                obligations=obligations or {},
                risk_weight=max(0.0, min(1.0, risk_weight)),
                tags=tags or [],
                created_by=actor_id,
            )
        )
        await self._publish_event(
            PolicyCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "policy_id": str(stored.id),
                    "slug": stored.slug,
                    "effect": str(effect),
                },
            )
        )
        return stored

    async def update_policy(
        self,
        organization_id: UUID,
        policy_id: UUID,
        *,
        changes: dict[str, Any],
        actor_id: UUID | None = None,
    ) -> Policy:
        """Edit a policy's metadata.

        Does **not** publish. The edit lands on the authored row and
        live decisions carry on using the last published content until
        somebody publishes deliberately.

        Raises:
            ConflictError: If the policy is a system guardrail.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        if stored.is_system:
            raise ConflictError(
                f"Policy {stored.slug!r} is a platform guardrail and cannot be edited. "
                "Write a higher-priority policy of your own to override it."
            )

        editable = {
            "name",
            "description",
            "category",
            "policy_type",
            "effect",
            "priority",
            "subject_types",
            "resource_types",
            "actions",
            "obligations",
            "risk_weight",
            "tags",
            "labels",
        }
        rejected = sorted(set(changes) - editable)
        if rejected:
            # Refused rather than ignored: a caller who sent `status` or
            # `compiled_rule` and got a 200 back would reasonably believe
            # the change took effect.
            raise ValidationError(
                f"These fields cannot be set directly: {', '.join(rejected)}. "
                "Use the publish and rollback endpoints for lifecycle and content."
            )

        for field_name, value in changes.items():
            setattr(stored, field_name, value)
        stored.updated_by = actor_id
        updated = await self._policies.update(stored)

        await self._publish_event(
            PolicyUpdatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "policy_id": str(policy_id),
                    "slug": updated.slug,
                    "fields": sorted(changes),
                },
            )
        )
        return updated

    async def delete_policy(
        self, organization_id: UUID, policy_id: UUID, *, actor_id: UUID | None = None
    ) -> bool:
        """Archive a policy.

        Archived rather than deleted: a policy that produced ten thousand
        decisions is the explanation for all of them, and removing the
        row makes every one of those traces unreadable.

        Raises:
            ConflictError: If it is a platform guardrail.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        if stored.is_system:
            raise ConflictError(
                f"Policy {stored.slug!r} is a platform guardrail and cannot be deleted."
            )
        stored.status = PolicyStatus.ARCHIVED
        stored.archived_at = datetime.now(UTC)
        stored.updated_by = actor_id
        await self._policies.update(stored)
        return True

    async def transition(
        self,
        organization_id: UUID,
        policy_id: UUID,
        *,
        target: PolicyStatus,
        actor_id: UUID | None = None,
    ) -> Policy:
        """Move a policy through its lifecycle.

        Raises:
            ValidationError: If the move is not legal. In particular a
                draft cannot become published directly -- the review
                states exist so somebody other than the author looks at a
                rule before it starts refusing people's work.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        current = status_of(stored)
        if target not in _ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(str(one) for one in _ALLOWED_TRANSITIONS[current]))
            raise ValidationError(
                f"A {str(current)!r} policy cannot move to {str(target)!r}. "
                f"Allowed from here: {allowed}."
            )
        stored.status = target
        stored.updated_by = actor_id
        return await self._policies.update(stored)

    # ---- rule authoring -------------------------------------------------

    async def set_rule_tree(
        self,
        organization_id: UUID,
        policy_id: UUID,
        rule: Rule,
        *,
        actor_id: UUID | None = None,
    ) -> int:
        """Replace a policy's authored rules with one tree.

        Returns how many conditions were written. Replaces rather than
        merges: a partial update of a boolean tree has no sensible
        meaning -- half a rule is a different rule -- and reconciling
        node by node would produce trees nobody authored.

        Raises:
            ValidationError: If the tree is unusable.
            ConflictError: If the policy is a platform guardrail.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        if stored.is_system:
            raise ConflictError(
                f"Policy {stored.slug!r} is a platform guardrail and its rules cannot be edited."
            )

        # Validated before anything is deleted. Writing the new tree over
        # a wiped old one and *then* discovering it is malformed would
        # leave the policy with no rules at all -- which, once published,
        # is a policy that matches nothing.
        validate_rule(rule)

        for existing in await self._rules.list_for_policy(organization_id, policy_id):
            await self._rules.purge(existing.id)
        for existing_condition in await self._conditions.list_for_policy(
            organization_id, policy_id
        ):
            await self._conditions.purge(existing_condition.id)

        written = await self._write_rule(
            organization_id, policy_id, rule, parent_id=None, order=0, actor_id=actor_id
        )
        stored.updated_by = actor_id
        await self._policies.update(stored)
        return written

    async def _write_rule(
        self,
        organization_id: UUID,
        policy_id: UUID,
        rule: Rule,
        *,
        parent_id: UUID | None,
        order: int,
        actor_id: UUID | None,
    ) -> int:
        """Persist one rule node and everything under it."""
        node = await self._rules.create(
            PolicyRule(
                organization_id=organization_id,
                policy_id=policy_id,
                parent_rule_id=parent_id,
                name=rule.name,
                description=rule.description or None,
                logical_operator=rule.logical_operator,
                negate=rule.negate,
                display_order=order,
                created_by=actor_id,
            )
        )

        written = 0
        for index, condition in enumerate(rule.conditions):
            await self._conditions.create(
                PolicyCondition(
                    organization_id=organization_id,
                    policy_id=policy_id,
                    rule_id=node.id,
                    attribute_source=condition.source,
                    attribute_path=condition.path,
                    operator=condition.operator,
                    comparison_value={"value": condition.value},
                    negate=condition.negate,
                    display_order=index,
                    description=condition.description or None,
                    created_by=actor_id,
                )
            )
            written += 1

        for index, child in enumerate(rule.children):
            written += await self._write_rule(
                organization_id,
                policy_id,
                child,
                parent_id=node.id,
                order=index,
                actor_id=actor_id,
            )
        return written

    # ---- publishing -----------------------------------------------------

    async def publish(
        self,
        organization_id: UUID,
        policy_id: UUID,
        *,
        change_summary: str | None = None,
        breaking: bool = False,
        feature: bool = False,
        actor_id: UUID | None = None,
    ) -> Policy:
        """Compile the authored rules and make them live.

        Compilation validates first, so a policy that cannot be evaluated
        is refused here -- while a person is waiting for an answer --
        rather than at 03:00 inside a decision nobody is watching.

        Raises:
            ValidationError: If the authored rules will not compile.
            ConflictError: If the policy is archived.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        if status_of(stored) in _TERMINAL_STATUSES:
            raise ConflictError(
                f"Policy {stored.slug!r} is archived. Move it back to draft before publishing."
            )

        rules = await self._rules.list_for_policy(organization_id, policy_id)
        conditions = await self._conditions.list_for_policy(organization_id, policy_id)
        compiled, digest, condition_count = compile_policy(
            rules, conditions, policy_slug=stored.slug
        )

        version = next_version(stored.semantic_version, breaking=breaking, feature=feature)
        sequence = await self._versions.next_sequence(organization_id, policy_id)
        moment = datetime.now(UTC)

        await self._versions.create(
            PolicyVersion(
                organization_id=organization_id,
                policy_id=policy_id,
                sequence=sequence,
                semantic_version=version,
                name=stored.name,
                description=stored.description,
                effect=effect_of(stored),
                policy_type=stored.policy_type,
                category=stored.category,
                priority=stored.priority,
                subject_types=list(stored.subject_types or []),
                resource_types=list(stored.resource_types or []),
                actions=list(stored.actions or []),
                compiled_rule=compiled,
                obligations=dict(stored.obligations or {}),
                risk_weight=stored.risk_weight,
                change_summary=change_summary,
                published_at=moment,
                published_by=actor_id,
                checksum_sha256=digest,
                created_by=actor_id,
            )
        )

        stored.compiled_rule = compiled
        stored.semantic_version = version
        stored.status = PolicyStatus.PUBLISHED
        stored.published_at = moment
        stored.published_by = actor_id
        stored.updated_by = actor_id
        published = await self._policies.update(stored)

        await self._publish_event(
            PolicyPublishedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "policy_id": str(policy_id),
                    "slug": stored.slug,
                    "version": version,
                    "effect": str(effect_of(stored)),
                    "condition_count": condition_count,
                },
            )
        )
        logger.info(
            "A policy was published and is now influencing decisions.",
            extra={
                "extra_fields": {
                    "policy_id": str(policy_id),
                    "slug": stored.slug,
                    "version": version,
                    "effect": str(effect_of(stored)),
                }
            },
        )
        return published

    async def rollback(
        self,
        organization_id: UUID,
        policy_id: UUID,
        *,
        version: str | None = None,
        actor_id: UUID | None = None,
    ) -> Policy:
        """Restore a previously published version.

        Points at a stored row rather than replaying a change log, which
        is what makes rollback a certainty rather than a reconstruction.
        Without an explicit version this restores the one *before* the
        current, which is what "roll back" means when something has just
        gone wrong.

        Raises:
            ValidationError: If there is no such version, or nothing to
                roll back to.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        history = await self._versions.list_for_policy(organization_id, policy_id)
        if not history:
            raise ValidationError(
                f"Policy {stored.slug!r} has never been published, so there is "
                "nothing to roll back to."
            )

        if version is not None:
            target = next((one for one in history if one.semantic_version == version), None)
            if target is None:
                available = ", ".join(one.semantic_version for one in history[:10])
                raise ValidationError(
                    f"Policy {stored.slug!r} has no version {version!r}. Available: {available}."
                )
        else:
            previous = [one for one in history if one.semantic_version != stored.semantic_version]
            if not previous:
                raise ValidationError(
                    f"Policy {stored.slug!r} has only one published version "
                    f"({stored.semantic_version}); there is nothing earlier to roll back to."
                )
            target = previous[0]

        integrity = verify_integrity(target.compiled_rule, target.checksum_sha256)
        if not integrity["verified"]:
            # A stored version that no longer matches its digest was
            # changed by something that did not go through publishing.
            # Restoring it would make that change live, which is the one
            # outcome an integrity check exists to prevent.
            raise ValidationError(
                f"Version {target.semantic_version} of {stored.slug!r} failed its integrity "
                f"check ({integrity['reason']}) and will not be restored."
            )

        stored.compiled_rule = dict(target.compiled_rule or {})
        stored.effect = target.effect
        stored.priority = target.priority
        stored.subject_types = list(target.subject_types or [])
        stored.resource_types = list(target.resource_types or [])
        stored.actions = list(target.actions or [])
        stored.obligations = dict(target.obligations or {})
        stored.risk_weight = target.risk_weight
        stored.semantic_version = target.semantic_version
        stored.status = PolicyStatus.PUBLISHED
        stored.updated_by = actor_id
        restored = await self._policies.update(stored)

        logger.warning(
            "A policy was rolled back to an earlier published version.",
            extra={
                "extra_fields": {
                    "policy_id": str(policy_id),
                    "slug": stored.slug,
                    "restored_version": target.semantic_version,
                }
            },
        )
        return restored

    async def versions(
        self, organization_id: UUID, policy_id: UUID, *, limit: int = 100
    ) -> list[PolicyVersion]:
        """Published versions of one policy, newest first."""
        return await self._versions.list_for_policy(organization_id, policy_id, limit=limit)

    async def verify(self, organization_id: UUID, policy_id: UUID) -> dict[str, Any]:
        """Check a live policy against the digest of its published version.

        A mismatch means the stored rule changed without going through
        publishing -- which for the service that authorizes every
        protected operation is the one tampering signal worth having.
        """
        stored = await self._policies.require_in_org(organization_id, policy_id)
        latest = await self._versions.latest_for_policy(organization_id, policy_id)
        if latest is None:
            return {
                "verified": False,
                "reason": "this policy has never been published",
                "slug": stored.slug,
            }
        result = verify_integrity(stored.compiled_rule or {}, latest.checksum_sha256)
        return {
            **result,
            "slug": stored.slug,
            "version": latest.semantic_version,
            "live_checksum": checksum(stored.compiled_rule or {}),
        }

    # ---- guardrails -----------------------------------------------------

    async def seed_guardrails(
        self, organization_id: UUID, *, actor_id: UUID | None = None
    ) -> list[Policy]:
        """Install the platform's baseline policies, published.

        Idempotent by slug, so re-running on an existing organization
        adds only what is missing rather than duplicating. Seeded
        **published**, unlike everything else here: a guardrail sitting
        in draft is a guardrail that is not guarding, and these are the
        rules whose absence names a specific incident.
        """
        created: list[Policy] = []
        for template in BUILTIN_GUARDRAILS:
            if await self._policies.get_by_slug(organization_id, template.slug):
                continue
            created.append(await self._seed_one(organization_id, template, actor_id=actor_id))
        if created:
            logger.info(
                "Seeded platform guardrails for an organization.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "seeded": [one.slug for one in created],
                    }
                },
            )
        return created

    async def _seed_one(
        self,
        organization_id: UUID,
        template: GuardrailTemplate,
        *,
        actor_id: UUID | None,
    ) -> Policy:
        """Install one guardrail, compiled and published."""
        compiled = template.rule.as_dict()
        moment = datetime.now(UTC)
        stored = await self._policies.create(
            Policy(
                organization_id=organization_id,
                slug=template.slug,
                name=template.name,
                description=template.description,
                category=template.category,
                policy_type=template.policy_type,
                effect=template.effect,
                status=PolicyStatus.PUBLISHED,
                priority=template.priority,
                subject_types=list(template.subject_types),
                resource_types=list(template.resource_types),
                actions=list(template.actions),
                compiled_rule=compiled,
                obligations=dict(template.obligations),
                risk_weight=template.risk_weight,
                is_system=True,
                published_at=moment,
                published_by=actor_id,
                created_by=actor_id,
            )
        )
        await self._versions.create(
            PolicyVersion(
                organization_id=organization_id,
                policy_id=stored.id,
                sequence=1,
                semantic_version="1.0.0",
                name=template.name,
                description=template.description,
                effect=template.effect,
                policy_type=template.policy_type,
                category=template.category,
                priority=template.priority,
                subject_types=list(template.subject_types),
                resource_types=list(template.resource_types),
                actions=list(template.actions),
                compiled_rule=compiled,
                obligations=dict(template.obligations),
                risk_weight=template.risk_weight,
                change_summary="Platform guardrail, seeded at organization setup.",
                published_at=moment,
                published_by=actor_id,
                checksum_sha256=checksum(compiled),
                created_by=actor_id,
            )
        )
        await self._write_rule(
            organization_id,
            stored.id,
            template.rule,
            parent_id=None,
            order=0,
            actor_id=actor_id,
        )
        return stored


def condition_payload(
    source: AttributeSource,
    path: str,
    operator: RuleOperator,
    value: Any = None,
) -> dict[str, Any]:
    """Build the JSON shape a stored condition's value column expects."""
    return {
        "source": str(source),
        "path": path,
        "operator": str(operator),
        "value": value,
    }


def empty_rule(name: str = "root") -> Rule:
    """A root rule with no conditions.

    Refused by validation, deliberately -- offered here only so callers
    have a named starting point rather than constructing one that looks
    valid.
    """
    return Rule(name=name, logical_operator=LogicalOperator.ALL)


__all__ = [
    "PolicyService",
    "condition_payload",
    "effect_of",
    "empty_rule",
    "status_of",
]

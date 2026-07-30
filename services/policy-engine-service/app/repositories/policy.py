"""Repositories for the policy catalogue and its authored rules.

Every read here is scoped by ``organization_id``, including the ones
keyed by slug. A slug is a human-chosen identifier -- ``deny-secret-export``,
``prod-approval`` -- so an unscoped lookup by slug lets one tenant read
another's governance by guessing a name, which is not a hard guess.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PolicyCategory, PolicyStatus, PolicyType
from app.models.policy import Policy, PolicyCategoryRecord, PolicyVersion
from app.models.rule import PolicyAttribute, PolicyCondition, PolicyRule


class PolicyRepository(BaseRepository[Policy]):
    """The catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Policy, tenant_scope=tenant_scope)

    async def get_by_slug(self, organization_id: UUID, slug: str) -> Policy | None:
        """One policy by its slug within an organization."""
        stmt = (
            self._base_select()
            .where(Policy.organization_id == organization_id)
            .where(Policy.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def require_by_slug(self, organization_id: UUID, slug: str) -> Policy:
        """One policy by slug.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        found = await self.get_by_slug(organization_id, slug)
        if found is None:
            raise NotFoundError(f"No policy with slug {slug!r}.")
        return found

    async def require_by_id(self, organization_id: UUID, policy_id: UUID) -> Policy:
        """One policy by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. Deliberately not a
                permission error: telling a caller a policy exists but
                belongs to someone else confirms the id, which is the one
                thing they did not already know.
        """
        stmt = (
            self._base_select()
            .where(Policy.organization_id == organization_id)
            .where(Policy.id == policy_id)
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No policy with id {policy_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: PolicyStatus | None = None,
        category: PolicyCategory | None = None,
        policy_type: PolicyType | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Policy]:
        """Policies for one organization, highest priority first."""
        stmt = self._base_select().where(Policy.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Policy.status == status)
        if category is not None:
            stmt = stmt.where(Policy.category == category)
        if policy_type is not None:
            stmt = stmt.where(Policy.policy_type == policy_type)
        stmt = stmt.order_by(desc(Policy.priority), Policy.slug).offset(max(0, offset)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_evaluable(self, organization_id: UUID, *, limit: int = 500) -> list[Policy]:
        """Every policy eligible to influence a live decision.

        Filtered on ``status == PUBLISHED``, never on ``is_active``. A
        draft must not reach a decision, and that guarantee has to rest
        on the lifecycle column somebody deliberately advances rather
        than on a soft-delete flag anything could set.
        """
        stmt = (
            self._base_select()
            .where(Policy.organization_id == organization_id)
            .where(Policy.status == PolicyStatus.PUBLISHED)
            .order_by(desc(Policy.priority), Policy.slug)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, organization_id: UUID, policy_ids: list[UUID]) -> list[Policy]:
        """Named policies, scoped to one organization.

        Used by simulation to pull in drafts. Scoped even though the ids
        are unguessable, because obscurity is not authorization and a
        forwarded id should not become a read of another tenant's
        governance.
        """
        if not policy_ids:
            return []
        stmt = (
            self._base_select()
            .where(Policy.organization_id == organization_id)
            .where(Policy.id.in_(policy_ids))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many policies sit in each lifecycle state.

        Counted in the database rather than by loading every row: this
        feeds the statistics rollup, which runs over every organization.
        """
        stmt = (
            select(Policy.status, func.count())
            .where(Policy.organization_id == organization_id)
            .where(Policy.is_active.is_(True))
            .group_by(Policy.status)
        )
        result = await self._session.execute(stmt)
        return {str(status): int(count) for status, count in result.all()}

    async def list_unused(self, organization_id: UUID, *, limit: int = 100) -> list[Policy]:
        """Published policies nothing has ever matched.

        Either dead weight or -- far more dangerous -- a rule whose
        conditions have drifted out of line with reality, so it looks
        like governance and enforces nothing.
        """
        stmt = (
            self._base_select()
            .where(Policy.organization_id == organization_id)
            .where(Policy.status == PolicyStatus.PUBLISHED)
            .where(Policy.evaluation_count == 0)
            .order_by(Policy.slug)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PolicyVersionRepository(BaseRepository[PolicyVersion]):
    """Immutable published snapshots."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyVersion, tenant_scope=tenant_scope)

    async def list_for_policy(
        self, organization_id: UUID, policy_id: UUID, *, limit: int = 100
    ) -> list[PolicyVersion]:
        """Every published version of one policy, newest first."""
        stmt = (
            self._base_select()
            .where(PolicyVersion.organization_id == organization_id)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(desc(PolicyVersion.sequence))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_version(
        self, organization_id: UUID, policy_id: UUID, version: str
    ) -> PolicyVersion | None:
        """One specific published version."""
        stmt = (
            self._base_select()
            .where(PolicyVersion.organization_id == organization_id)
            .where(PolicyVersion.policy_id == policy_id)
            .where(PolicyVersion.semantic_version == version)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def latest_for_policy(
        self, organization_id: UUID, policy_id: UUID
    ) -> PolicyVersion | None:
        """The most recently published version."""
        versions = await self.list_for_policy(organization_id, policy_id, limit=1)
        return versions[0] if versions else None

    async def next_sequence(self, organization_id: UUID, policy_id: UUID) -> int:
        """The next version sequence for one policy."""
        stmt = (
            select(func.max(PolicyVersion.sequence))
            .where(PolicyVersion.organization_id == organization_id)
            .where(PolicyVersion.policy_id == policy_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0) + 1


class PolicyRuleRepository(BaseRepository[PolicyRule]):
    """Authored rule nodes."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyRule, tenant_scope=tenant_scope)

    async def list_for_policy(self, organization_id: UUID, policy_id: UUID) -> list[PolicyRule]:
        """Every rule node belonging to one policy, in authoring order."""
        stmt = (
            self._base_select()
            .where(PolicyRule.organization_id == organization_id)
            .where(PolicyRule.policy_id == policy_id)
            .order_by(PolicyRule.display_order, PolicyRule.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def require_by_id(self, organization_id: UUID, rule_id: UUID) -> PolicyRule:
        """One rule node.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        stmt = (
            self._base_select()
            .where(PolicyRule.organization_id == organization_id)
            .where(PolicyRule.id == rule_id)
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No policy rule with id {rule_id} in this organization.")
        return found


class PolicyConditionRepository(BaseRepository[PolicyCondition]):
    """Authored conditions."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyCondition, tenant_scope=tenant_scope)

    async def list_for_policy(
        self, organization_id: UUID, policy_id: UUID
    ) -> list[PolicyCondition]:
        """Every condition in one policy.

        One query rather than a recursive walk of the rule tree, which is
        what ``policy_id`` is denormalised onto the row for.
        """
        stmt = (
            self._base_select()
            .where(PolicyCondition.organization_id == organization_id)
            .where(PolicyCondition.policy_id == policy_id)
            .order_by(PolicyCondition.display_order, PolicyCondition.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_rule(self, organization_id: UUID, rule_id: UUID) -> list[PolicyCondition]:
        """The conditions attached to one rule node."""
        stmt = (
            self._base_select()
            .where(PolicyCondition.organization_id == organization_id)
            .where(PolicyCondition.rule_id == rule_id)
            .order_by(PolicyCondition.display_order, PolicyCondition.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PolicyAttributeRepository(BaseRepository[PolicyAttribute]):
    """The attribute catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyAttribute, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 500
    ) -> list[PolicyAttribute]:
        """Every declared attribute, by source then path."""
        stmt = (
            self._base_select()
            .where(PolicyAttribute.organization_id == organization_id)
            .order_by(PolicyAttribute.source, PolicyAttribute.path)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def sensitive_paths(self, organization_id: UUID) -> set[tuple[str, str]]:
        """Every ``(source, path)`` that must be redacted from a trace.

        A decision trace records what each condition saw. For most
        attributes that is the point; for an authentication token or a
        personal identifier it would turn the decision log into a second
        copy of data protected elsewhere.
        """
        stmt = (
            select(PolicyAttribute.source, PolicyAttribute.path)
            .where(PolicyAttribute.organization_id == organization_id)
            .where(PolicyAttribute.is_sensitive.is_(True))
            .where(PolicyAttribute.is_active.is_(True))
        )
        result = await self._session.execute(stmt)
        return {(str(source), str(path)) for source, path in result.all()}


class PolicyCategoryRepository(BaseRepository[PolicyCategoryRecord]):
    """Organization-defined groupings."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyCategoryRecord, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[PolicyCategoryRecord]:
        """Categories in display order."""
        stmt = (
            self._base_select()
            .where(PolicyCategoryRecord.organization_id == organization_id)
            .order_by(PolicyCategoryRecord.display_order, PolicyCategoryRecord.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, organization_id: UUID, slug: str) -> PolicyCategoryRecord | None:
        """One category by slug."""
        stmt = (
            self._base_select()
            .where(PolicyCategoryRecord.organization_id == organization_id)
            .where(PolicyCategoryRecord.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = [
    "PolicyAttributeRepository",
    "PolicyCategoryRepository",
    "PolicyConditionRepository",
    "PolicyRepository",
    "PolicyRuleRepository",
    "PolicyVersionRepository",
]

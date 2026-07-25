"""Asset group management. Per docs/036 "GROUPS": Static, Dynamic,
Rule-Based, Location, Application, Environment, Custom Groups. See
``app/models/asset_group.py``'s own docstring for the static-vs-dynamic
membership storage split.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.asset import Asset
from app.models.asset_group import AssetGroup
from app.models.enums import GroupType
from app.repositories.asset import AssetRepository
from app.repositories.asset_group import AssetGroupRepository


def _matches_rule(asset: Asset, rule: dict[str, Any]) -> bool:
    """Evaluate a simple ``{field, operator, value}`` rule against *asset*.

    Only ``eq``/``ne`` on direct :class:`Asset` columns are supported --
    the same "documented scope limit, not a silent gap" every prior
    AI-IOS service's own simple filter model already establishes for
    dimensions a full query-builder would be needed to cover completely.
    """
    field = rule.get("field")
    operator = rule.get("operator", "eq")
    expected = rule.get("value")
    if not field or not hasattr(asset, field):
        return False
    actual = getattr(asset, field)
    actual = str(actual) if actual is not None else None
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    return False


class AssetGroupService:
    """Creates and lists asset groups, resolving dynamic membership on read."""

    def __init__(self, groups: AssetGroupRepository, assets: AssetRepository) -> None:
        self._groups = groups
        self._assets = assets

    async def list_for_org(self, organization_id: UUID) -> list[AssetGroup]:
        """Every group defined for *organization_id*."""
        return await self._groups.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None = None,
        group_type: GroupType = GroupType.STATIC,
        rule: dict[str, Any] | None = None,
        member_asset_ids: list[UUID] | None = None,
    ) -> AssetGroup:
        """Create a new group.

        Raises:
            ConflictError: If *name* is already taken within *organization_id*.
        """
        if await self._groups.get_by_name(organization_id, name) is not None:
            raise ConflictError(f"Group {name!r} already exists in this organization.")
        return await self._groups.create(
            AssetGroup(
                organization_id=organization_id,
                name=name,
                description=description,
                group_type=group_type,
                rule=rule or {},
                member_asset_ids=[str(asset_id) for asset_id in (member_asset_ids or [])],
            )
        )

    async def resolve_members(self, group_id: UUID) -> list[Asset]:
        """Resolve *group_id*'s current membership -- the stored id list
        for static/location/application/environment/custom groups, or a
        live rule evaluation for dynamic/rule-based groups.
        """
        group = await self._groups.require_by_id(group_id)
        if group.group_type in (GroupType.DYNAMIC, GroupType.RULE_BASED):
            candidates = await self._assets.list_for_org(group.organization_id)
            return [asset for asset in candidates if _matches_rule(asset, group.rule)]
        members: list[Asset] = []
        for raw_id in group.member_asset_ids:
            asset = await self._assets.get_by_id(UUID(raw_id))
            if asset is not None:
                members.append(asset)
        return members

    async def add_member(self, group_id: UUID, asset_id: UUID) -> AssetGroup:
        """Add *asset_id* to a static group's membership, if not already present."""
        group = await self._groups.require_by_id(group_id)
        if str(asset_id) not in group.member_asset_ids:
            group.member_asset_ids = [*group.member_asset_ids, str(asset_id)]
        return group

    async def remove_member(self, group_id: UUID, asset_id: UUID) -> AssetGroup:
        """Remove *asset_id* from a static group's membership."""
        group = await self._groups.require_by_id(group_id)
        group.member_asset_ids = [
            existing for existing in group.member_asset_ids if existing != str(asset_id)
        ]
        return group

    async def delete(self, group_id: UUID) -> None:
        """Delete a group.

        Raises:
            NotFoundError: If no such group exists.
        """
        await self._groups.delete(group_id)


__all__ = ["AssetGroupService"]

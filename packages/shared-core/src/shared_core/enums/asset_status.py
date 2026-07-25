"""Asset status enumeration."""

from enum import StrEnum


class AssetStatus(StrEnum):
    """Lifecycle states for a discovered or managed infrastructure asset."""

    DISCOVERED = "discovered"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"
    UNREACHABLE = "unreachable"

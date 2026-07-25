"""Plugin identity and descriptive metadata.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN TYPES" and the
identity fields of "PLUGIN MANIFEST" (Plugin ID, Name, Version, Author,
Vendor, Description, License, Category). The remaining manifest fields
(Dependencies, Permissions, Compatibility, Entry Point, Configuration
Schema) live in :mod:`shared_core.plugins.manifest`, which wraps one
:class:`PluginMetadata` plus those.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PluginType(StrEnum):
    """Every plugin type docs/029 "PLUGIN TYPES" names."""

    CONNECTOR = "connector"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    NOTIFICATION = "notification"
    DASHBOARD = "dashboard"
    WIDGET = "widget"
    AI = "ai"
    CLI = "cli"
    REST_API = "rest_api"
    AUTHENTICATION = "authentication"
    STORAGE = "storage"
    INTEGRATION = "integration"
    REPORTING = "reporting"
    CUSTOM_BUSINESS_LOGIC = "custom_business_logic"


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    """A plugin's identity ("Every plugin shall declare metadata")."""

    plugin_id: str
    name: str
    version: str
    category: PluginType
    author: str | None = None
    vendor: str | None = None
    description: str | None = None
    license: str | None = None
    homepage: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["PluginMetadata", "PluginType"]

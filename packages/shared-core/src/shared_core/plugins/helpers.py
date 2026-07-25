"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

from typing import Any

from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.registry import PluginRecord


def plugin_summary(record: PluginRecord) -> dict[str, Any]:
    """A JSON-serializable summary of one plugin's current state."""
    return {
        "plugin_id": record.manifest.metadata.plugin_id,
        "name": record.manifest.metadata.name,
        "version": record.manifest.metadata.version,
        "category": record.manifest.metadata.category.value,
        "state": record.lifecycle.state.value,
    }


def manifest_summary(manifest: PluginManifest) -> dict[str, Any]:
    """A JSON-serializable summary of a plugin manifest."""
    return {
        "plugin_id": manifest.metadata.plugin_id,
        "name": manifest.metadata.name,
        "version": manifest.metadata.version,
        "category": manifest.metadata.category.value,
        "dependency_count": len(manifest.dependencies),
        "permission_count": len(manifest.permissions),
        "compatibility": manifest.compatibility,
    }


__all__ = ["manifest_summary", "plugin_summary"]

"""Inventory model.

Per docs/027_Enterprise_Connector_SDK.md.txt "INVENTORY": Hardware,
Software, OS, CPU, Memory, Storage, Network, Services, Processes,
Certificates, Packages, Applications. This module only defines the
shared result shape every provider's ``collect_inventory()`` returns --
what's actually collected is entirely protocol-specific (an SSH host's
inventory looks nothing like a Kubernetes cluster's), so each field is
a loosely-typed mapping/tuple a concrete connector populates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class InventoryReport:
    """One ``BaseConnector.collect_inventory()`` call's full result ("Collect")."""

    host: str
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    hardware: dict[str, Any] = field(default_factory=dict)
    software: dict[str, Any] = field(default_factory=dict)
    operating_system: dict[str, Any] = field(default_factory=dict)
    cpu: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    storage: tuple[dict[str, Any], ...] = ()
    network: tuple[dict[str, Any], ...] = ()
    services: tuple[dict[str, Any], ...] = ()
    processes: tuple[dict[str, Any], ...] = ()
    certificates: tuple[dict[str, Any], ...] = ()
    packages: tuple[dict[str, Any], ...] = ()
    applications: tuple[dict[str, Any], ...] = ()


__all__ = ["InventoryReport"]

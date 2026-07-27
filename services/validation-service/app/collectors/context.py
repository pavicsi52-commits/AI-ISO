"""The bundle of live service clients every collector needs.

A single dataclass rather than five separate function parameters on
every collector -- each collector only actually uses one or two of
these clients, but the registry (:mod:`app.collectors.registry`) calls
every collector through one uniform signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.workflow_client import WorkflowRuntimeClient


@dataclass(frozen=True, slots=True)
class CollectorContext:
    """Live service clients available to every collector."""

    inventory: InventoryClient
    configuration: ConfigurationClient
    automation: AutomationClient
    workflow: WorkflowRuntimeClient
    discovery: DiscoveryClient


__all__ = ["CollectorContext"]

"""The bundle of live service clients every collector needs.

A single dataclass rather than six separate function parameters on
every collector -- each collector only actually uses one or two of
these clients, but the registry (:mod:`app.collectors.registry`) calls
every collector through one uniform signature. Matches
``services/validation-service``'s own
:class:`app.collectors.context.CollectorContext`, extended with
:attr:`validation` for this service's own sixth integration.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.validation_client import ValidationClient
from app.clients.workflow_client import WorkflowRuntimeClient


@dataclass(frozen=True, slots=True)
class CollectorContext:
    """Live service clients available to every collector."""

    inventory: InventoryClient
    configuration: ConfigurationClient
    automation: AutomationClient
    workflow: WorkflowRuntimeClient
    discovery: DiscoveryClient
    validation: ValidationClient


__all__ = ["CollectorContext"]

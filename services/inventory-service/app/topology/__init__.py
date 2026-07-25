"""Neo4j-backed asset topology for the inventory service."""

from __future__ import annotations

from app.topology.client import create_neo4j_driver
from app.topology.graph import TopologyGraphClient

__all__ = ["TopologyGraphClient", "create_neo4j_driver"]

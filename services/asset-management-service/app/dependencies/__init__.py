"""Read-only Neo4j dependency-graph integration.

Per docs/038 "DEPENDENCY ANALYSIS": "Integrate with Neo4j." This
package never writes graph state -- ``services/inventory-service``
owns that -- it only queries the graph that service already populates.
"""

from __future__ import annotations

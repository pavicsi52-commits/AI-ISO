"""Neo4j-related constants."""

from typing import Final


class Neo4jConstants:
    """Neo4j connection constants."""

    DEFAULT_BOLT_PORT: Final[int] = 7687
    DEFAULT_HTTP_PORT: Final[int] = 7474
    DEFAULT_DATABASE: Final[str] = "neo4j"
    DEFAULT_MAX_CONNECTION_POOL_SIZE: Final[int] = 50
    DEFAULT_CONNECTION_TIMEOUT_SECONDS: Final[int] = 30

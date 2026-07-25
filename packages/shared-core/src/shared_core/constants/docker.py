"""Docker-related constants."""

from typing import Final


class DockerConstants:
    """Docker runtime constants."""

    DEFAULT_NETWORK: Final[str] = "aiios_network"
    HEALTHCHECK_INTERVAL_SECONDS: Final[int] = 10
    HEALTHCHECK_TIMEOUT_SECONDS: Final[int] = 5
    HEALTHCHECK_RETRIES: Final[int] = 5
    HEALTHCHECK_START_PERIOD_SECONDS: Final[int] = 10

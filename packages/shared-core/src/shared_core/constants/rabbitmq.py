"""RabbitMQ-related constants."""

from typing import Final


class RabbitMQConstants:
    """RabbitMQ connection and messaging constants."""

    DEFAULT_PORT: Final[int] = 5672
    DEFAULT_MANAGEMENT_PORT: Final[int] = 15672
    DEFAULT_VHOST: Final[str] = "/aiios"

    EXCHANGE_EVENTS: Final[str] = "aiios.events"
    EXCHANGE_DEAD_LETTER: Final[str] = "aiios.dead_letter"

    DEFAULT_RETRY_MAX_ATTEMPTS: Final[int] = 5
    DEFAULT_RETRY_INITIAL_DELAY_SECONDS: Final[float] = 1.0
    DEFAULT_RETRY_BACKOFF_MULTIPLIER: Final[float] = 2.0
    DEFAULT_PREFETCH_COUNT: Final[int] = 10

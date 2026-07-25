"""AI-related constants."""

from typing import Final


class AIConstants:
    """AI assistant framework constants."""

    DEFAULT_MODEL_TEMPERATURE: Final[float] = 0.2
    DEFAULT_MAX_TOKENS: Final[int] = 4_096
    EMBEDDING_DIMENSIONS: Final[int] = 1_536
    CONVERSATION_HISTORY_MAX_MESSAGES: Final[int] = 50

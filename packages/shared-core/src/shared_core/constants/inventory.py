"""Inventory-related constants."""

from typing import Final


class InventoryConstants:
    """Asset inventory constants."""

    DEFAULT_DISCOVERY_TIMEOUT_SECONDS: Final[int] = 30
    MAX_ASSETS_PER_ORGANIZATION: Final[int] = 100_000
    DEFAULT_SCAN_BATCH_SIZE: Final[int] = 100

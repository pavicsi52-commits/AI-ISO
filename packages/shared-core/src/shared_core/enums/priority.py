"""Priority level enumeration."""

from enum import StrEnum


class Priority(StrEnum):
    """Priority used by jobs, queues, and workflows.

    Five levels per docs/021_Enterprise_Queue_Framework.md.txt "PRIORITY".
    Nothing outside this package referenced the Prompt 012 baseline's
    ``URGENT`` member, so it was renamed to ``CRITICAL`` (the spec's own
    term) rather than kept as a redundant alias.
    """

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"

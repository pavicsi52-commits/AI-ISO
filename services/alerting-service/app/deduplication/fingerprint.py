"""Alert fingerprinting ("DEDUPLICATION" "Support": Fingerprinting,
Hash Matching).

A fingerprint is a stable, deterministic identity for "the same
condition recurring" -- two alerts sharing one are the same underlying
problem reported twice, not two independent problems. It deliberately
excludes anything that varies between occurrences (timestamps, the
alert's own id, a message's own embedded current value) and includes
only what identifies the *condition*: the organization, source, rule,
and whichever ``source_reference`` keys the caller declares
identity-bearing.

Uses SHA-256 (not Python's own :func:`hash`, which is salted per
process and therefore differs across restarts and across workers --
the exact opposite of what deduplication needs).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.models.enums import AlertSource

DEFAULT_IDENTITY_KEYS: tuple[str, ...] = ("target_id", "metric_id", "check_id", "resource")
"""The ``source_reference`` keys treated as identity-bearing by default.

Each names a real entity a partner service's own event carries
(``target_id``/``metric_id`` from Monitoring, ``check_id`` from
Validation, ``resource`` as the generic fallback). Keys outside this
set (e.g. a current sampled ``value``) vary per occurrence and would
break deduplication if folded in.
"""


def compute_fingerprint(
    *,
    organization_id: UUID,
    source: AlertSource,
    rule_id: UUID | None,
    source_reference: dict[str, Any],
    identity_keys: Iterable[str] = DEFAULT_IDENTITY_KEYS,
) -> str:
    """Return a stable SHA-256 fingerprint identifying this condition.

    ``rule_id`` may be ``None`` (a directly-raised alert, per
    ``POST /alerts``); such alerts still fingerprint consistently, they
    simply group by source and reference alone.
    """
    identity = {
        key: source_reference[key]
        for key in sorted(set(identity_keys))
        if key in source_reference and source_reference[key] is not None
    }
    payload = json.dumps(
        {
            "organization_id": str(organization_id),
            "source": str(source),
            "rule_id": str(rule_id) if rule_id is not None else None,
            "identity": identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["DEFAULT_IDENTITY_KEYS", "compute_fingerprint"]

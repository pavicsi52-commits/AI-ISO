"""Secret resolution.

Per docs/013_Configuration_Framework.md.txt "SECRET MANAGEMENT": secrets are
never hardcoded. Resolution order:

1. ``<NAME>_FILE`` environment variable pointing at a mounted secret file
   (the Docker Swarm / Kubernetes convention).
2. The default Docker secrets mount, ``/run/secrets/<name>``.
3. The plain ``<NAME>`` environment variable.

Vault / AWS Secrets Manager / Azure Key Vault integration is future work
per the spec ("Future: Vault, AWS Secrets, Azure Key Vault").
"""

from __future__ import annotations

import os
from pathlib import Path

_DOCKER_SECRETS_DIR = Path("/run/secrets")


def resolve_secret(name: str) -> str | None:
    """Resolve a secret by name using the standard resolution order.

    Args:
        name: The environment variable name, e.g. ``"AIIOS_DATABASE_PASSWORD"``.

    Returns:
        The resolved secret value, or ``None`` if not found anywhere.
    """
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        resolved = _read_secret_file(Path(file_path))
        if resolved is not None:
            return resolved

    docker_secret = _read_secret_file(_DOCKER_SECRETS_DIR / name.lower())
    if docker_secret is not None:
        return docker_secret

    return os.environ.get(name)


def _read_secret_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

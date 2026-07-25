"""Ansible playbook runner, via the real ``ansible-playbook`` CLI. Per
docs/040 "PLAYBOOK SUPPORT" "Ansible Playbooks". No ``ansible``/
``ansible-core`` Python dependency -- this shells out to whatever
``ansible-playbook`` is actually installed and on ``PATH``, the same
"invoke the real CLI, don't vendor a client library" choice already
made for :mod:`app.runners.powershell_runner`.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.runners.base import RunnerResult
from app.runners.exceptions import RunnerError
from app.runners.subprocess_helper import run_argv


def is_ansible_available() -> bool:
    """Whether ``ansible-playbook`` is actually installed and on ``PATH``."""
    return shutil.which("ansible-playbook") is not None


async def run_ansible_playbook(
    content: str,
    *,
    inventory_hosts: list[str],
    extra_vars: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *content* as a real Ansible playbook against *inventory_hosts*.

    Raises:
        RunnerError: If ``ansible-playbook`` isn't installed, or the process times out.
    """
    if not is_ansible_available():
        raise RunnerError("'ansible-playbook' is not available on PATH.")

    with tempfile.TemporaryDirectory() as tmpdir:
        playbook_path = Path(tmpdir) / "playbook.yml"
        playbook_path.write_text(content, encoding="utf-8")

        inventory_path = Path(tmpdir) / "inventory.ini"
        inventory_path.write_text("\n".join(inventory_hosts) + "\n", encoding="utf-8")

        argv = ["ansible-playbook", "-i", str(inventory_path), str(playbook_path)]
        if extra_vars:
            argv.extend(["--extra-vars", json.dumps(extra_vars)])

        return await run_argv(argv, env=env, timeout_seconds=timeout_seconds)


__all__ = ["is_ansible_available", "run_ansible_playbook"]

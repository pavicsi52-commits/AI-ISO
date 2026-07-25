"""Exceptions raised by every local script/playbook runner."""

from __future__ import annotations


class RunnerError(Exception):
    """A local script/playbook runner failed to start, run, or timed out."""


__all__ = ["RunnerError"]

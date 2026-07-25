"""Plugin lifecycle state machine.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LIFECYCLE":
Discover, Validate, Install, Enable, Initialize, Start, Pause, Resume,
Stop, Disable, Update, Uninstall. Same shape as
:class:`shared_core.workflow.state_machine.StateMachine` -- a states
enum plus a validated transition table -- branded for plugins since
each framework in this codebase owns its own state machine rather than
sharing one generic implementation across domains.
"""

from __future__ import annotations

from enum import StrEnum

from shared_core.plugins.exceptions import InvalidLifecycleTransitionError


class PluginState(StrEnum):
    """Every state docs/029 "PLUGIN LIFECYCLE" names (as a settled noun/participle)."""

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INSTALLED = "installed"
    ENABLED = "enabled"
    INITIALIZED = "initialized"
    STARTED = "started"
    PAUSED = "paused"
    STOPPED = "stopped"
    DISABLED = "disabled"
    UPDATING = "updating"
    UNINSTALLED = "uninstalled"
    FAILED = "failed"


_DEFAULT_TRANSITIONS: dict[PluginState, frozenset[PluginState]] = {
    PluginState.DISCOVERED: frozenset({PluginState.VALIDATED, PluginState.FAILED}),
    PluginState.VALIDATED: frozenset({PluginState.INSTALLED, PluginState.FAILED}),
    PluginState.INSTALLED: frozenset(
        {PluginState.ENABLED, PluginState.UNINSTALLED, PluginState.UPDATING}
    ),
    PluginState.ENABLED: frozenset(
        {PluginState.INITIALIZED, PluginState.DISABLED, PluginState.UNINSTALLED}
    ),
    PluginState.INITIALIZED: frozenset(
        {PluginState.STARTED, PluginState.DISABLED, PluginState.FAILED}
    ),
    PluginState.STARTED: frozenset({PluginState.PAUSED, PluginState.STOPPED, PluginState.FAILED}),
    PluginState.PAUSED: frozenset({PluginState.STARTED, PluginState.STOPPED}),
    PluginState.STOPPED: frozenset(
        {
            PluginState.STARTED,
            PluginState.DISABLED,
            PluginState.UPDATING,
            PluginState.UNINSTALLED,
        }
    ),
    PluginState.DISABLED: frozenset(
        {PluginState.ENABLED, PluginState.UNINSTALLED, PluginState.UPDATING}
    ),
    PluginState.UPDATING: frozenset({PluginState.INSTALLED, PluginState.FAILED}),
    PluginState.UNINSTALLED: frozenset(),
    PluginState.FAILED: frozenset({PluginState.DISABLED, PluginState.UNINSTALLED}),
}


class PluginLifecycle:
    """Governs valid lifecycle transitions for one plugin instance."""

    def __init__(
        self,
        *,
        initial_state: PluginState = PluginState.DISCOVERED,
        transitions: dict[PluginState, frozenset[PluginState]] | None = None,
    ) -> None:
        self._state = initial_state
        self._transitions = transitions if transitions is not None else _DEFAULT_TRANSITIONS
        self._history: list[PluginState] = [initial_state]

    @property
    def state(self) -> PluginState:
        """This plugin's current lifecycle state."""
        return self._state

    @property
    def history(self) -> list[PluginState]:
        """Every state this plugin has been in, in order (including the current one)."""
        return list(self._history)

    def can_transition(self, target: PluginState) -> bool:
        """Whether moving from the current state to *target* is allowed."""
        return target in self._transitions.get(self._state, frozenset())

    def transition(self, target: PluginState) -> None:
        """Move to *target*.

        Raises:
            InvalidLifecycleTransitionError: If not allowed from the current state.
        """
        if not self.can_transition(target):
            raise InvalidLifecycleTransitionError(
                f"Cannot transition plugin from {self._state.value!r} to {target.value!r}."
            )
        self._state = target
        self._history.append(target)

    def is_terminal(self) -> bool:
        """Whether the current state has no further transitions defined."""
        return not self._transitions.get(self._state, frozenset())


__all__ = ["PluginLifecycle", "PluginState"]

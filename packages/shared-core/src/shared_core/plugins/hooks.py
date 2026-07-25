"""Event hooks.

Per docs/029_Enterprise_Plugin_Framework.md.txt "EVENT HOOKS": Before
Startup, After Startup, Before Shutdown, Workflow Started, Workflow
Completed, Connector Connected, Validation Completed, Automation
Finished, Notification Sent, Custom Hooks. A named, ordered callback
registry -- this framework provides the registration/firing
*mechanism*; actually calling ``fire("before_startup")`` at the right
moment is whatever host service embeds this framework's job, per
docs/029 "DO NOT IMPLEMENT" (Automation Engine, Discovery Engine, ...),
the same "mechanism, not business behavior" split as every other
Prompt 021-028 extension point.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shared_core.plugins.exceptions import HookExecutionError

HookCallback = Callable[..., Awaitable[None]]

# Named hook points docs/029 "EVENT HOOKS" lists explicitly. Any other
# string is also a valid hook name ("Custom Hooks") -- this registry
# never validates *names*, only ever appends/fires callbacks under them.
BEFORE_STARTUP = "before_startup"
AFTER_STARTUP = "after_startup"
BEFORE_SHUTDOWN = "before_shutdown"
WORKFLOW_STARTED = "workflow_started"
WORKFLOW_COMPLETED = "workflow_completed"
CONNECTOR_CONNECTED = "connector_connected"
VALIDATION_COMPLETED = "validation_completed"
AUTOMATION_FINISHED = "automation_finished"
NOTIFICATION_SENT = "notification_sent"


@dataclass(frozen=True, slots=True)
class HookRegistration:
    """One plugin's registered callback for one hook point."""

    plugin_id: str
    hook_name: str
    callback: HookCallback


class HookRegistry:
    """Registers and fires named callbacks ("Event Hooks")."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = {}

    def register(self, hook_name: str, plugin_id: str, callback: HookCallback) -> None:
        """Register *callback* for *hook_name*, attributed to *plugin_id* ("Custom Hooks")."""
        self._hooks.setdefault(hook_name, []).append(
            HookRegistration(plugin_id=plugin_id, hook_name=hook_name, callback=callback)
        )

    def unregister_all_from(self, plugin_id: str) -> None:
        """Remove every hook *plugin_id* registered, across every hook point."""
        for hook_name in list(self._hooks):
            self._hooks[hook_name] = [
                registration
                for registration in self._hooks[hook_name]
                if registration.plugin_id != plugin_id
            ]

    def registered_hooks(self, hook_name: str) -> list[HookRegistration]:
        """Every registration currently attached to *hook_name*, in registration order."""
        return list(self._hooks.get(hook_name, []))

    async def fire(self, hook_name: str, *args: object, **kwargs: object) -> None:
        """Call every callback registered for *hook_name*, in registration order.

        A single callback's failure doesn't prevent the others from
        running -- every failure is collected and raised together
        afterward.

        Raises:
            HookExecutionError: If any callback raised.
        """
        errors: list[str] = []
        for registration in self._hooks.get(hook_name, []):
            try:
                await registration.callback(*args, **kwargs)
            except Exception as exc:
                errors.append(f"{registration.plugin_id!r}: {exc}")
        if errors:
            raise HookExecutionError(
                f"{len(errors)} hook callback(s) for {hook_name!r} failed: {'; '.join(errors)}"
            )


__all__ = [
    "AFTER_STARTUP",
    "AUTOMATION_FINISHED",
    "BEFORE_SHUTDOWN",
    "BEFORE_STARTUP",
    "CONNECTOR_CONNECTED",
    "NOTIFICATION_SENT",
    "VALIDATION_COMPLETED",
    "WORKFLOW_COMPLETED",
    "WORKFLOW_STARTED",
    "HookCallback",
    "HookRegistration",
    "HookRegistry",
]

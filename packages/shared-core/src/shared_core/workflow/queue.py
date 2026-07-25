"""Queue integration.

Per docs/028_Enterprise_Workflow_SDK.md.txt "QUEUE INTEGRATION": Queue
Tasks, Background Execution, Worker Pools, Retry Queue, Dead Letter
Queue. "Integrate with Prompt 021." Reuses
:class:`shared_core.queue.manager.QueueManager`/
:class:`~shared_core.queue.producer.Producer`/
:class:`~shared_core.queue.consumer.Consumer` directly (already
implement durable delivery, retry-with-backoff, and dead-lettering)
rather than a second queue integration -- this module only defines the
envelope a ``QUEUE`` node's work is published as, mirroring
:mod:`shared_core.scheduler.queue`'s identical shape.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared_core.queue.consumer import Consumer
from shared_core.queue.manager import QueueManager
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

DEFAULT_WORKFLOW_TASK_QUEUE_NAME = "workflow.tasks"

WorkflowTaskHandler = Callable[[str, str, dict[str, Any]], Awaitable[None]]


def build_task_message(execution_id: str, node_id: str, payload: dict[str, Any]) -> QueueMessage:
    """Build the envelope published when a ``QUEUE`` node hands work to a background worker."""
    return {"execution_id": execution_id, "node_id": node_id, "payload": payload}


class WorkflowTaskQueue:
    """Publishes/consumes background workflow task work via a durable queue ("Worker Pools")."""

    def __init__(
        self, queue_manager: QueueManager, *, queue_name: str = DEFAULT_WORKFLOW_TASK_QUEUE_NAME
    ) -> None:
        self._queue_manager = queue_manager
        self._queue_name = queue_name
        self._producer = Producer(queue_manager)
        self._consumer = Consumer(queue_manager)

    async def declare(self) -> None:
        """Declare the queue (and its dead-letter queue) before first use ("Dead Letter Queue")."""
        await self._queue_manager.declare_queue_with_dlq(self._queue_name)

    async def enqueue(self, execution_id: str, node_id: str, payload: dict[str, Any]) -> None:
        """Publish one ``QUEUE`` node's work for background execution ("Queue Tasks")."""
        await self._producer.publish(
            self._queue_name, build_task_message(execution_id, node_id, payload)
        )

    async def consume(self, handler: WorkflowTaskHandler) -> None:
        """Subscribe *handler* to receive queued workflow task work ("Background Execution")."""

        async def _dispatch(message: QueueMessage) -> None:
            await handler(
                str(message["execution_id"]), str(message["node_id"]), dict(message["payload"])
            )

        await self._consumer.subscribe(self._queue_name, _dispatch)


__all__ = [
    "DEFAULT_WORKFLOW_TASK_QUEUE_NAME",
    "WorkflowTaskHandler",
    "WorkflowTaskQueue",
    "build_task_message",
]

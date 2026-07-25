"""Message consumer.

Per docs/021_Enterprise_Queue_Framework.md.txt "CONSUMER": Subscribe,
Batch Consume, Acknowledgement, Reject, Requeue, Retry, Dead Letter,
Filtering.

Acknowledgement/Reject/Requeue/Retry/Dead Letter are already owned by
:meth:`shared_core.queue.manager.QueueManager.consume` -- this module
adds the two docs/021 "CONSUMER" features that aren't already part of
the queue manager's own contract: "Filtering" (skip a message before the
handler ever sees it) and "Batch Consume" (accumulate messages before
calling the handler).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from shared_core.queue.constants import DEFAULT_BATCH_FLUSH_INTERVAL_SECONDS
from shared_core.queue.manager import QueueManager
from shared_core.queue.retry import RetryPolicy
from shared_core.types.queue import QueueMessage

MessageFilter = Callable[[QueueMessage], bool]
MessageHandler = Callable[[QueueMessage], Awaitable[None]]
BatchHandler = Callable[[list[QueueMessage]], Awaitable[None]]


class Consumer:
    """Ergonomic subscribe facade over :class:`~shared_core.queue.manager.QueueManager`."""

    def __init__(
        self, queue_manager: QueueManager, *, retry_policy: RetryPolicy | None = None
    ) -> None:
        self._queue_manager = queue_manager
        self._retry_policy = retry_policy
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def subscribe(
        self,
        queue_name: str,
        handler: MessageHandler,
        *,
        filter: MessageFilter | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Subscribe *handler* to *queue_name* ("Subscribe"), skipping messages *filter* rejects.

        A filtered-out message is acknowledged immediately (it was never
        meant for this consumer -- that's not a failure worth retrying
        or dead-lettering).
        """

        async def _dispatch(message: QueueMessage) -> None:
            if filter is not None and not filter(message):
                return
            await handler(message)

        if max_retries is not None:
            await self._queue_manager.consume(
                queue_name, _dispatch, max_retries=max_retries, retry_policy=self._retry_policy
            )
        elif self._retry_policy is not None:
            await self._queue_manager.consume(
                queue_name, _dispatch, retry_policy=self._retry_policy
            )
        else:
            await self._queue_manager.consume(queue_name, _dispatch)

    async def subscribe_batch(
        self,
        queue_name: str,
        handler: BatchHandler,
        *,
        batch_size: int,
        flush_interval_seconds: float = DEFAULT_BATCH_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        """Subscribe *handler* to receive up to *batch_size* messages at a time ("Batch Consume").

        A batch is flushed once it reaches *batch_size*, or once
        *flush_interval_seconds* passes since the first message in the
        (still-partial) batch arrived, whichever comes first -- so a slow
        trickle of messages still gets delivered promptly instead of
        waiting forever for a full batch.
        """
        pending: asyncio.Queue[QueueMessage] = asyncio.Queue()

        async def _dispatch(message: QueueMessage) -> None:
            await pending.put(message)

        async def _collect_and_flush() -> None:
            while True:
                batch = [await pending.get()]
                deadline = time.monotonic() + flush_interval_seconds
                while len(batch) < batch_size:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(pending.get(), timeout=remaining))
                    except TimeoutError:
                        break
                await handler(batch)

        # Tracked on self so the task isn't eligible for garbage collection
        # mid-flight (a bare fire-and-forget create_task() is only weakly
        # held by the event loop) and discarded from the set once it ends.
        task = asyncio.create_task(_collect_and_flush())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        await self._queue_manager.consume(queue_name, _dispatch)


__all__ = ["BatchHandler", "Consumer", "MessageFilter", "MessageHandler"]

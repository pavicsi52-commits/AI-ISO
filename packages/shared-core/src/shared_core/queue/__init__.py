"""Enterprise Queue Framework.

The reusable job-queue/background-processing backbone for AI-IOS
(docs/021_Enterprise_Queue_Framework.md.txt "OBJECTIVE"): Job Queue,
Background Processing, Task Scheduling, Retry, Priority Queue, Dead
Letter Queue, Delayed Queue, Worker Pool, Queue Monitoring, Queue
Metrics, Queue Health, Distributed Processing. RabbitMQ today, with
provider abstraction (:mod:`shared_core.queue.exchange`'s framework-local
``ExchangeType``, :mod:`shared_core.queue.serializer`'s format-agnostic
envelope) supporting future Kafka/NATS/Redis Streams backends without a
public API change.
"""

from shared_core.queue.bindings import bind_queue, unbind_queue
from shared_core.queue.compression import CompressionAlgorithm, compress, decompress
from shared_core.queue.connection import (
    create_connection,
    create_connection_pool,
    create_connection_with_retry,
    graceful_shutdown,
    wait_for_broker,
)
from shared_core.queue.constants import DEAD_LETTER_QUEUE_SUFFIX, DELAY_QUEUE_SUFFIX
from shared_core.queue.consumer import BatchHandler, Consumer, MessageFilter, MessageHandler
from shared_core.queue.dead_letter import (
    DeadLetteredMessage,
    dead_letter_queue_name_for,
    export_dead_letters,
    filter_dead_letters,
    inspect_dead_letters,
    purge_dead_letters,
    replay_dead_letters,
)
from shared_core.queue.decorators import get_job_queue_name, job, register_jobs, scheduled
from shared_core.queue.delay import declare_delay_queue, delay_queue_name_for, delay_until
from shared_core.queue.exceptions import (
    ConnectionFailedError,
    ConsumeFailedError,
    DeadLetterError,
    InvalidDelayError,
    InvalidPriorityError,
    PublishFailedError,
    RoutingError,
    SchedulingError,
    WorkerPoolError,
)
from shared_core.queue.exchange import ExchangeType, declare_exchange
from shared_core.queue.factory import QueueFramework, create_queue_framework
from shared_core.queue.health import QueueHealthReport, check_queue_health, get_queue_depth
from shared_core.queue.helpers import generate_message_id
from shared_core.queue.manager import QueueManager
from shared_core.queue.priority import declare_priority_queue, priority_level
from shared_core.queue.producer import Producer
from shared_core.queue.retry import RetryPolicy, compute_backoff_delay, is_retryable
from shared_core.queue.routing import Router, RoutingRule, build_routing_key, topic_matches
from shared_core.queue.scheduler import ScheduledTask, TaskScheduler, next_run_time, validate_cron
from shared_core.queue.serializer import SerializationFormat, deserialize_message, serialize_message
from shared_core.queue.statistics import QueueStatistics
from shared_core.queue.worker import WorkerBase, WorkerPool, WorkerStatus

__all__ = [
    "DEAD_LETTER_QUEUE_SUFFIX",
    "DELAY_QUEUE_SUFFIX",
    "BatchHandler",
    "CompressionAlgorithm",
    "ConnectionFailedError",
    "ConsumeFailedError",
    "Consumer",
    "DeadLetterError",
    "DeadLetteredMessage",
    "ExchangeType",
    "InvalidDelayError",
    "InvalidPriorityError",
    "MessageFilter",
    "MessageHandler",
    "Producer",
    "PublishFailedError",
    "QueueFramework",
    "QueueHealthReport",
    "QueueManager",
    "QueueStatistics",
    "RetryPolicy",
    "Router",
    "RoutingError",
    "RoutingRule",
    "ScheduledTask",
    "SchedulingError",
    "SerializationFormat",
    "TaskScheduler",
    "WorkerBase",
    "WorkerPool",
    "WorkerPoolError",
    "WorkerStatus",
    "bind_queue",
    "build_routing_key",
    "check_queue_health",
    "compress",
    "compute_backoff_delay",
    "create_connection",
    "create_connection_pool",
    "create_connection_with_retry",
    "create_queue_framework",
    "dead_letter_queue_name_for",
    "declare_delay_queue",
    "declare_exchange",
    "declare_priority_queue",
    "decompress",
    "delay_queue_name_for",
    "delay_until",
    "deserialize_message",
    "export_dead_letters",
    "filter_dead_letters",
    "generate_message_id",
    "get_job_queue_name",
    "get_queue_depth",
    "graceful_shutdown",
    "inspect_dead_letters",
    "is_retryable",
    "job",
    "next_run_time",
    "priority_level",
    "purge_dead_letters",
    "register_jobs",
    "replay_dead_letters",
    "scheduled",
    "serialize_message",
    "topic_matches",
    "unbind_queue",
    "validate_cron",
    "wait_for_broker",
]

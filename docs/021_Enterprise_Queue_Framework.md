# AI Infrastructure Operating System (AI-IOS)

# Prompt 021

## Enterprise Queue Framework

Reference Documents

Prompt 000
Prompt 001
Prompt 002
Prompt 003
Prompt 004
Prompt 005
Prompt 006
Prompt 007
Prompt 008
Prompt 009
Prompt 010
Prompt 011
Prompt 012
Prompt 013
Prompt 014
Prompt 015
Prompt 016
Prompt 017
Prompt 018
Prompt 019
Prompt 020

---

# ROLE

You are the Principal Distributed Systems Engineer.

Implement the Enterprise Queue Framework.

Do not redesign the architecture.

Do not implement business logic.

Implement only the reusable queue framework.

---

# OBJECTIVE

Create a reusable queue framework that every service can use.

The framework must support

Job Queue

Background Processing

Task Scheduling

Retry

Priority Queue

Dead Letter Queue

Delayed Queue

Worker Pool

Queue Monitoring

Queue Metrics

Queue Health

Distributed Processing

---

# PACKAGE

packages/shared-core/queue/

---

# DIRECTORY STRUCTURE

queue/

__init__.py

manager.py

connection.py

producer.py

consumer.py

worker.py

scheduler.py

priority.py

delay.py

retry.py

dead_letter.py

routing.py

exchange.py

bindings.py

serializer.py

compression.py

health.py

metrics.py

statistics.py

decorators.py

factory.py

constants.py

exceptions.py

helpers.py

tests/

README.md

---

# MESSAGE BROKER

RabbitMQ

Future

Kafka

NATS

Redis Streams

Implementation must support provider abstraction.

---

# CONNECTION MANAGEMENT

Implement

Connection Pool

Reconnect

Retry

Heartbeat

Health Check

Graceful Shutdown

TLS

Authentication

---

# QUEUE TYPES

Standard Queue

Priority Queue

Delayed Queue

Retry Queue

Dead Letter Queue

Broadcast Queue

Topic Queue

Fanout Queue

---

# MESSAGE FORMAT

Every message SHALL contain

message_id

correlation_id

request_id

organization_id

project_id

user_id

timestamp

producer

consumer

priority

retry_count

payload

metadata

version

---

# PRODUCER

Support

Publish

Batch Publish

Scheduled Publish

Priority Publish

Async Publish

Confirmation

Timeout

Retry

---

# CONSUMER

Support

Subscribe

Batch Consume

Acknowledgement

Reject

Requeue

Retry

Dead Letter

Filtering

---

# WORKER POOL

Dynamic Workers

Concurrency Control

Worker Health

Worker Restart

Worker Shutdown

Worker Metrics

---

# RETRY POLICY

Exponential Backoff

Maximum Attempts

Retry Delay

Retry Classification

Retry Metrics

Configurable

---

# DEAD LETTER

Store failed jobs.

Support

Replay

Inspection

Filtering

Export

Purge

---

# PRIORITY

Support

Critical

High

Normal

Low

Background

---

# DELAYED JOBS

Execute

After Time

Cron

Specific Date

Recurring

---

# JOB TYPES

Automation

Discovery

Validation

Monitoring

Notifications

Reports

AI Tasks

Imports

Exports

Backups

---

# ROUTING

Topic Exchange

Direct Exchange

Fanout Exchange

Headers Exchange

Configurable Routing

---

# SERIALIZATION

JSON

MessagePack

Compression

Encryption

Versioning

---

# HEALTH

Broker Health

Queue Depth

Worker Status

Message Rate

Latency

Consumer Health

Producer Health

---

# METRICS

Published

Consumed

Failed

Retried

Dead Letter

Processing Time

Queue Length

Worker Count

Throughput

Prometheus Metrics

---

# SECURITY

TLS

Authentication

Authorization

Encrypted Messages

Sensitive Data Masking

Audit Queue Access

---

# PERFORMANCE

Async Processing

Batch Operations

Connection Reuse

Compression

Parallel Consumers

Horizontal Scaling

---

# TESTING

Unit Tests

RabbitMQ Integration Tests

Retry Tests

Dead Letter Tests

Priority Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Queue Guide

Worker Guide

Retry Guide

Dead Letter Guide

Developer Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Producer

✓ Consumer

✓ Worker Pool

✓ Retry

✓ Dead Letter

✓ Priority Queue

✓ Delayed Queue

✓ Metrics

✓ Health

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Business Logic

REST APIs

Authentication

Inventory

Automation

Only Enterprise Queue Framework.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass Ruff, Black, MyPy and Pytest.

Do not summarize.

End Prompt 021.

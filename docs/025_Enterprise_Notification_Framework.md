# AI Infrastructure Operating System (AI-IOS)

# Prompt 025

## Enterprise Notification Framework

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
Prompt 021
Prompt 022
Prompt 023
Prompt 024

---

# ROLE

You are the Principal Communication Platform Architect.

Implement the Enterprise Notification Framework.

Do NOT redesign the platform.

Do NOT implement business logic.

Implement ONLY the reusable notification framework.

Every AI-IOS service shall use this framework.

---

# OBJECTIVE

Create a centralized notification framework capable of delivering notifications across multiple channels.

The framework shall support

Email

SMS

Push Notifications

In-App Notifications

Slack

Microsoft Teams

Discord

Webhooks

Future WhatsApp

Future Telegram

Future Microsoft Outlook

Future Mobile Applications

---

# PACKAGE

packages/shared-core/notifications/

---

# DIRECTORY STRUCTURE

notifications/

__init__.py

manager.py

router.py

dispatcher.py

channels.py

email.py

sms.py

push.py

in_app.py

slack.py

teams.py

discord.py

webhook.py

templates.py

renderer.py

preferences.py

subscriptions.py

digest.py

retry.py

scheduler.py

delivery.py

history.py

tracking.py

attachments.py

priority.py

ratelimit.py

metrics.py

analytics.py

health.py

middleware.py

decorators.py

factory.py

constants.py

exceptions.py

helpers.py

tests/

README.md

---

# NOTIFICATION TYPES

Information

Success

Warning

Error

Critical

Approval

Reminder

System

Workflow

Automation

Validation

Monitoring

Security

AI

Maintenance

---

# CHANNELS

Support

SMTP Email

SMS Provider

Push Provider

In-App

Slack

Microsoft Teams

Discord

Webhook

Every channel shall implement the same interface.

---

# MESSAGE MODEL

Every notification shall contain

notification_id

organization_id

project_id

user_id

channel

priority

subject

title

body

template

variables

attachments

status

created_at

sent_at

delivered_at

read_at

metadata

---

# TEMPLATE ENGINE

Support

HTML

Markdown

Plain Text

Subject Templates

Variable Replacement

Localization

Versioning

Preview

Validation

---

# USER PREFERENCES

Allow configuration of

Preferred Channels

Notification Categories

Quiet Hours

Language

Timezone

Digest Frequency

Mute

Unsubscribe

Channel Priority

---

# DELIVERY

Support

Immediate

Scheduled

Recurring

Delayed

Bulk Delivery

Broadcast

Multicast

---

# RETRY

Support

Retry Policy

Exponential Backoff

Maximum Attempts

Failure Classification

Dead Letter

Manual Retry

---

# PRIORITY

Critical

High

Normal

Low

Background

Priority affects delivery order.

---

# ATTACHMENTS

Support

PDF

CSV

TXT

JSON

ZIP

Images

Maximum Size Validation

Virus Scan Hook

---

# IN-APP NOTIFICATIONS

Support

Unread

Read

Archived

Pinned

Categories

Search

Filtering

Pagination

---

# WEBHOOKS

Support

REST

Authentication

Retry

Signature Verification

Custom Headers

Payload Templates

---

# ANALYTICS

Collect

Sent

Delivered

Failed

Opened

Clicked

Bounced

Retried

Latency

Channel Usage

---

# DELIVERY STATUS

Pending

Queued

Sending

Sent

Delivered

Read

Failed

Expired

Cancelled

---

# RATE LIMITING

Per User

Per Organization

Per Channel

Per Provider

Global Limits

---

# SUBSCRIPTIONS

Support

Subscribe

Unsubscribe

Topics

Categories

Projects

Organizations

Broadcast Groups

---

# DIGEST

Support

Hourly

Daily

Weekly

Monthly

Summary Generation

Duplicate Removal

Grouping

---

# HEALTH

SMTP Status

SMS Provider Status

Webhook Status

Slack Status

Teams Status

Push Status

Queue Status

---

# SECURITY

Mask Sensitive Data

Encrypt Credentials

Secure Webhooks

Audit Notifications

Prevent Duplicate Delivery

Respect User Preferences

---

# PERFORMANCE

Async Delivery

Batch Processing

Queue Integration

Connection Pooling

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

SMTP Tests

Webhook Tests

Slack Tests

Teams Tests

Retry Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Notification Guide

Template Guide

Provider Guide

Webhook Guide

Developer Guide

Operations Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Notification Manager

✓ Channel Router

✓ Template Engine

✓ User Preferences

✓ Retry Engine

✓ Analytics

✓ Delivery Tracking

✓ In-App Notifications

✓ Webhook Support

✓ Health Monitoring

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Business Logic

Authentication

Inventory

Automation

Validation

Approval Workflows

REST APIs

Only the Enterprise Notification Framework.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

Ruff

Black

MyPy

Pytest

Do not summarize.

End Prompt 025.

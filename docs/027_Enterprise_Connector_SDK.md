# AI Infrastructure Operating System (AI-IOS)

# Prompt 027

## Enterprise Connector SDK

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
Prompt 025
Prompt 026

---

# ROLE

You are the Principal Infrastructure Integration Architect.

Implement the Enterprise Connector SDK.

Do NOT redesign the platform.

Do NOT implement business modules.

Implement ONLY the reusable Connector SDK.

Every infrastructure integration in AI-IOS SHALL use this SDK.

---

# OBJECTIVE

Create a unified SDK for connecting to infrastructure, operating systems, cloud providers, virtualization platforms, industrial devices, storage systems, networking equipment, APIs and enterprise applications.

The SDK must provide

• Connection Management

• Authentication

• Session Management

• Discovery

• Command Execution

• File Transfer

• Inventory Collection

• Validation

• Health Monitoring

• Retry

• Rate Limiting

• Audit

• Telemetry

• Metrics

• Plugin Support

---

# PACKAGE

packages/shared-core/connectors/

---

# DIRECTORY STRUCTURE

connectors/

__init__.py

manager.py

registry.py

factory.py

base.py

connection.py

session.py

authentication.py

credentials.py

pool.py

discovery.py

inventory.py

validation.py

health.py

metrics.py

telemetry.py

audit.py

retry.py

ratelimit.py

timeout.py

exceptions.py

constants.py

helpers.py

middleware.py

decorators.py

tests/

README.md

providers/

ssh/

winrm/

redfish/

snmp/

ipmi/

docker/

kubernetes/

vmware/

proxmox/

hyperv/

opcua/

modbus/

bacnet/

mqtt/

rest/

graphql/

grpc/

sftp/

ftp/

smb/

ldap/

activedirectory/

dns/

ntp/

aws/

azure/

gcp/

future/

---

# SDK PRINCIPLES

Every connector inherits BaseConnector.

Every connector follows the same lifecycle.

Every connector emits telemetry.

Every connector supports retries.

Every connector supports health monitoring.

Every connector supports metrics.

---

# CONNECTOR LIFECYCLE

Register

Initialize

Authenticate

Connect

Validate

Execute

Collect

Disconnect

Cleanup

---

# BASE CONNECTOR

Provide

Connect()

Disconnect()

Reconnect()

Validate()

Execute()

Health()

Metrics()

Inventory()

Discovery()

Capabilities()

---

# CONNECTION MANAGEMENT

Support

Connection Pooling

Persistent Sessions

Session Reuse

Timeouts

Reconnect

Keep Alive

TLS

Certificate Validation

Compression

---

# AUTHENTICATION

Support

Username Password

SSH Keys

API Keys

OAuth2

JWT

Bearer Tokens

Kerberos

Certificates

Future SSO

---

# SESSION MANAGEMENT

Create

Refresh

Expire

Reconnect

Terminate

Idle Timeout

Maximum Lifetime

---

# DISCOVERY

Support

Host Discovery

Service Discovery

Port Discovery

Resource Discovery

Capability Discovery

Plugin Discovery

---

# INVENTORY

Collect

Hardware

Software

OS

CPU

Memory

Storage

Network

Services

Processes

Certificates

Packages

Applications

---

# COMMAND EXECUTION

Support

Synchronous

Asynchronous

Streaming

Batch

Timeout

Cancellation

Progress Reporting

---

# FILE TRANSFER

Upload

Download

Resume

Checksum Validation

Compression

Encryption

Temporary Files

---

# VALIDATION

Connection Validation

Credential Validation

Certificate Validation

Capability Validation

Schema Validation

---

# HEALTH

Connection Status

Latency

Availability

Authentication Status

Protocol Status

Provider Status

---

# METRICS

Connection Count

Success Rate

Failure Rate

Latency

Retry Count

Bandwidth

Transfer Size

Command Duration

Inventory Duration

Discovery Duration

---

# TELEMETRY

Trace every operation.

Include

Trace ID

Connector Name

Provider

Target

Duration

Status

Errors

Integrate with Prompt 024.

---

# AUDIT

Audit

Connection

Authentication

Commands

Transfers

Inventory

Discovery

Failures

Disconnect

---

# RETRY

Support

Immediate

Fixed Delay

Exponential Backoff

Maximum Attempts

Retry Classification

Circuit Breaker

---

# RATE LIMITING

Per Connector

Per Target

Per Organization

Per Project

Burst Control

---

# PROVIDER REQUIREMENTS

Every provider SHALL implement

BaseConnector

Authentication

Configuration

Health

Discovery

Inventory

Metrics

Telemetry

Validation

Tests

Documentation

---

# PROVIDERS

SSH

Execute shell commands

WinRM

Windows management

Redfish

Server management

SNMP

Monitoring

IPMI

Hardware management

Docker

Containers

Kubernetes

Clusters

VMware

Virtualization

Proxmox

Virtualization

Hyper-V

Virtualization

OPC UA

Industrial automation

Modbus

Industrial devices

BACnet

Building automation

MQTT

Messaging

REST

REST APIs

GraphQL

GraphQL APIs

gRPC

Remote procedure calls

SFTP

Secure file transfer

FTP

Legacy transfer

SMB

Windows file sharing

LDAP

Directory services

Active Directory

Identity

DNS

DNS management

NTP

Time synchronization

AWS

Cloud

Azure

Cloud

GCP

Cloud

---

# MIDDLEWARE

Authentication

Retry

Telemetry

Audit

Metrics

Logging

Validation

Security

---

# SECURITY

Encrypt credentials.

Never log passwords.

Mask secrets.

Validate certificates.

Support secret providers.

Enforce tenant isolation.

---

# PERFORMANCE

Async I/O

Connection Reuse

Pooling

Batch Operations

Streaming

Compression

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

Mock Providers

Performance Tests

Security Tests

Connection Tests

Coverage >=95%

---

# DOCUMENTATION

README

SDK Guide

Provider Guide

Security Guide

Developer Guide

Operations Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Base Connector

✓ Registry

✓ Factory

✓ Authentication

✓ Session Management

✓ Discovery

✓ Inventory

✓ Validation

✓ Metrics

✓ Telemetry

✓ Audit

✓ Health Monitoring

✓ Retry

✓ Rate Limiting

✓ Provider SDK

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Business Logic

Discovery Engine

Automation Engine

Inventory Service

REST APIs

Authentication Service

Workflow Engine

Only the Enterprise Connector SDK.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

- Ruff
- Black
- MyPy
- Pytest

Generate provider templates for every supported connector.

Do not summarize.

End Prompt 027.

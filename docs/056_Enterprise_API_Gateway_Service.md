# AI Infrastructure Operating System (AI-IOS)

# Prompt 056

## Enterprise API Gateway Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 055

---

# ROLE

You are the Principal Enterprise API Gateway Architect.

Implement the Enterprise API Gateway Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise API Gateway.

---

# OBJECTIVE

Build a centralized API Gateway responsible for routing, authentication, authorization, traffic management, observability, API lifecycle management, and secure access to every AI-IOS service.

The API Gateway SHALL be the single external entry point for web applications, mobile applications, SDKs, CLI tools, AI agents, automation systems, partner integrations, and third-party APIs.

---

# SERVICE LOCATION

services/api-gateway-service/

---

# DIRECTORY STRUCTURE

api-gateway-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

gateway/

routing/

proxy/

authentication/

authorization/

apikeys/

oauth/

oidc/

jwt/

ratelimits/

quotas/

load_balancing/

service_discovery/

health/

transformations/

versioning/

graphql/

websocket/

openapi/

analytics/

reports/

events/

notifications/

middleware/

validators/

workers/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

api_routes

api_services

api_versions

api_keys

api_key_permissions

api_clients

api_rate_limits

api_quotas

api_requests

api_responses

api_transformations

api_health

api_statistics

api_reports

api_audit

---

# API ROUTING

Support

Static Routing

Dynamic Routing

Path-based Routing

Host-based Routing

Header-based Routing

Method-based Routing

Version-aware Routing

Weighted Routing

Conditional Routing

Fallback Routing

---

# REVERSE PROXY

Support

HTTP

HTTPS

HTTP/2

HTTP/3

gRPC Proxy

WebSocket Proxy

Streaming Requests

Streaming Responses

Compression

Keep Alive

---

# AUTHENTICATION

Integrate Prompt 030.

Support

JWT

OAuth2

OpenID Connect

API Keys

Service Accounts

Mutual TLS

Anonymous Routes

Session Validation

Token Refresh

---

# AUTHORIZATION

Integrate Prompt 032.

Integrate Prompt 050.

Support

RBAC

ABAC

Scope Validation

Policy Evaluation

Organization Isolation

Project Isolation

Resource Permissions

---

# API KEY MANAGEMENT

Support

API Key Generation

Key Rotation

Expiration

Scopes

Permissions

IP Restrictions

Rate Limits

Revocation

Audit History

---

# RATE LIMITING

Support

Global Limits

Organization Limits

Project Limits

User Limits

API Key Limits

Endpoint Limits

Burst Limits

Sliding Window

Token Bucket

Custom Policies

---

# QUOTA MANAGEMENT

Support

Daily Quotas

Monthly Quotas

Request Quotas

Bandwidth Quotas

Storage Quotas

Organization Quotas

Project Quotas

Custom Quotas

---

# LOAD BALANCING

Support

Round Robin

Least Connections

Weighted Routing

Health-aware Routing

Sticky Sessions

Failover

Automatic Recovery

---

# SERVICE DISCOVERY

Support

Static Registration

Dynamic Registration

Health Registration

Version Discovery

Metadata Discovery

Endpoint Discovery

---

# HEALTH MANAGEMENT

Support

Health Checks

Readiness Checks

Liveness Checks

Dependency Health

Circuit Breakers

Automatic Failover

Degraded Mode

---

# REQUEST TRANSFORMATION

Support

Header Manipulation

URL Rewriting

Request Enrichment

Request Validation

Body Transformation

Schema Validation

Metadata Injection

Correlation IDs

---

# RESPONSE TRANSFORMATION

Support

Header Injection

Response Mapping

Compression

Caching Headers

Error Normalization

Response Filtering

Metadata Injection

---

# API VERSIONING

Support

URI Versioning

Header Versioning

Media Type Versioning

Default Versions

Version Deprecation

Compatibility Rules

Migration Guidance

---

# GRAPHQL

Support

GraphQL Gateway

Schema Stitching

Federation

Resolver Routing

Query Validation

Depth Limits

Complexity Analysis

Persisted Queries

---

# WEBSOCKET GATEWAY

Support

Authentication

Authorization

Connection Management

Subscriptions

Broadcast

Heartbeat

Reconnect

Connection Metrics

---

# OPENAPI MANAGEMENT

Support

OpenAPI Aggregation

Schema Validation

API Catalog

Version Catalog

Interactive Documentation

Download Specifications

---

# CACHING

Support

Response Cache

Route Cache

Metadata Cache

JWT Cache

Service Discovery Cache

Config Cache

TTL Policies

Invalidation

---

# PLATFORM INTEGRATIONS

Integrate

Authentication (030)

RBAC (032)

Secrets (035)

Automation (040)

Workflow Runtime (042)

Monitoring (044)

Reporting (047)

Policy Engine (050)

Notification Center (055)

---

# ANALYTICS

Collect

Request Count

Response Time

Error Rate

Success Rate

Latency

Traffic Volume

API Usage

Endpoint Popularity

Client Usage

Gateway Throughput

---

# REPORTING

Generate

API Usage Reports

Latency Reports

Traffic Reports

Quota Reports

Security Reports

Gateway Health Reports

Audit Reports

---

# EVENTS

Publish

ApiRequestReceived

ApiRequestCompleted

ApiAuthenticationFailed

ApiAuthorizationDenied

RateLimitExceeded

QuotaExceeded

CircuitBreakerOpened

GatewayHealthChanged

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Gateway Failure

Service Unavailable

Certificate Expiring

Rate Limit Exceeded

Quota Exceeded

Security Event

---

# TELEMETRY

Integrate Prompt 024.

Trace

Request Lifecycle

Routing

Authentication

Authorization

Proxy Processing

Load Balancing

Transformation

Response Delivery

---

# AUDIT

Audit

Route Changes

API Key Changes

Authentication Events

Authorization Decisions

Gateway Configuration

Administrative Operations

---

# REST APIs

Implement

GET /gateway/routes

POST /gateway/routes

PUT /gateway/routes/{id}

DELETE /gateway/routes/{id}

GET /gateway/services

POST /gateway/services

GET /gateway/apikeys

POST /gateway/apikeys

PUT /gateway/apikeys/{id}

DELETE /gateway/apikeys/{id}

GET /gateway/statistics

GET /gateway/reports

GET /gateway/openapi

GET /gateway/health

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Integrate Prompt 050.

Enforce

Organization isolation

Project isolation

RBAC authorization

API key encryption

JWT validation

mTLS support

Immutable audit history

Protection against request smuggling

Protection against HTTP desynchronization

Protection against SSRF

Protection against header injection

Protection against API abuse

---

# PERFORMANCE

Horizontal Scaling

Stateless Gateway Nodes

Connection Pooling

Async Proxying

HTTP Keep Alive

Compression

Response Caching

High Availability

Automatic Failover

---

# TESTING

Unit Tests

Integration Tests

Routing Tests

Authentication Tests

Authorization Tests

Rate Limit Tests

Load Balancer Tests

WebSocket Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Gateway Guide

API Management Guide

Routing Guide

Authentication Guide

Versioning Guide

OpenAPI Guide

WebSocket Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ API Gateway

✓ Reverse Proxy

✓ Authentication

✓ Authorization

✓ API Key Management

✓ Rate Limiting

✓ Quota Management

✓ Load Balancing

✓ Service Discovery

✓ Health-aware Routing

✓ Request/Response Transformation

✓ API Versioning

✓ GraphQL Gateway

✓ WebSocket Gateway

✓ OpenAPI Aggregation

✓ Analytics

✓ Reports

✓ Events

✓ Notifications

✓ Audit

✓ REST APIs

✓ Database Migrations

✓ OpenAPI Documentation

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

External API Management Products

Developer Billing

Customer API Monetization

Business-specific Gateway Rules

Only implement the Enterprise API Gateway Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate gateway routing engine.

Generate authentication middleware.

Generate authorization engine.

Generate rate limiting engine.

Generate service discovery.

Generate WebSocket gateway.

Generate unit and integration tests.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

- Ruff
- Black
- MyPy
- Pytest

Do not summarize.

End Prompt 056.

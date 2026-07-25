# AI Infrastructure Operating System (AI-IOS)

# Prompt 049

## Enterprise Knowledge Graph Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 048

---

# ROLE

You are the Principal Enterprise Graph Architect.

Implement the Enterprise Knowledge Graph Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise knowledge graph built on Neo4j.

---

# OBJECTIVE

Build a centralized Knowledge Graph Service responsible for modeling enterprise infrastructure, services, applications, automation, workflows, monitoring, validation, configuration, compliance, and operational relationships.

The Knowledge Graph SHALL become the authoritative topology and relationship engine for AI-IOS.

The graph SHALL support graph traversal, dependency analysis, impact analysis, blast-radius analysis, digital twins, AI reasoning, and graph analytics.

---

# SERVICE LOCATION

services/knowledge-graph-service/

---

# DIRECTORY STRUCTURE

knowledge-graph-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

graph/

neo4j/

cypher/

topology/

relationships/

dependencies/

digital_twin/

analytics/

algorithms/

synchronization/

versioning/

import/

export/

queries/

search/

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

# DATABASES

Neo4j

PostgreSQL

PostgreSQL SHALL store metadata, synchronization state, audit, version history, and job status.

Neo4j SHALL store graph entities and relationships.

---

# DATABASE TABLES

Create

graph_sync_jobs

graph_versions

graph_import_jobs

graph_export_jobs

graph_queries

graph_saved_queries

graph_statistics

graph_snapshots

graph_change_history

graph_metadata

graph_reports

graph_audit

---

# GRAPH NODE TYPES

Support

Organization

Project

Site

Region

Data Center

Rack

Physical Server

Virtual Machine

Hypervisor

Container

Kubernetes Cluster

Namespace

Pod

Service

Deployment

Application

Database

Storage

Switch

Router

Firewall

Load Balancer

Network Interface

Cloud Account

Cloud Resource

Edge Device

Industrial Controller

PLC

Sensor

OPC UA Server

Workflow

Automation Job

Playbook

Validation Profile

Configuration Profile

Alert

Incident

Report

User

Team

Role

Custom Node

---

# RELATIONSHIP TYPES

Support

HOSTS

RUNS_ON

CONTAINS

DEPENDS_ON

CONNECTED_TO

COMMUNICATES_WITH

OWNS

BELONGS_TO

PART_OF

PROTECTS

MONITORS

VALIDATES

CONFIGURES

EXECUTES

GENERATES

USES

MANAGES

REPLICATES_TO

BACKS_UP

CUSTOM_RELATIONSHIP

---

# DIGITAL TWIN

Support

Infrastructure Twin

Application Twin

Cloud Twin

Industrial Twin

Service Twin

Configuration Twin

Lifecycle Tracking

Health Synchronization

---

# GRAPH SYNCHRONIZATION

Synchronize

Inventory

Discovery

Configuration

Automation

Workflow

Validation

Monitoring

Alerting

Reporting

Administration

Incremental Updates

Full Synchronization

Conflict Resolution

Bidirectional Metadata Sync

---

# GRAPH QUERIES

Support

Dependency Lookup

Impact Analysis

Blast Radius

Shortest Path

Relationship Traversal

Neighbor Discovery

Topology Queries

Ownership Queries

Service Dependency Queries

Configuration Dependency Queries

Automation Dependency Queries

Workflow Dependency Queries

Custom Cypher

Saved Queries

Parameterized Queries

---

# GRAPH ANALYTICS

Support

Degree Centrality

Betweenness Centrality

PageRank

Community Detection

Connected Components

Shortest Path

Critical Asset Identification

Risk Propagation

Dependency Scoring

Relationship Density

Custom Algorithms

---

# IMPACT ANALYSIS

Support

Infrastructure Impact

Application Impact

Configuration Impact

Automation Impact

Workflow Impact

Service Impact

Dependency Chain Analysis

Risk Propagation

---

# BLAST RADIUS

Support

Failure Propagation

Service Impact

Dependency Expansion

Risk Visualization

Affected Assets

Affected Applications

Affected Workflows

Affected Automations

---

# VERSIONING

Support

Graph Snapshots

Version History

Graph Comparison

Rollback Metadata

Change Tracking

---

# IMPORT / EXPORT

Support

Cypher

GraphML

CSV

JSON

Bulk Import

Bulk Export

Scheduled Export

Snapshot Restore

---

# SEARCH

Support

Full Graph Search

Node Search

Relationship Search

Property Search

Metadata Search

Saved Searches

Filtering

Sorting

Pagination

---

# AI INTEGRATION

Integrate Prompt 046.

Support

Graph RAG

Graph Traversal

Context Expansion

Knowledge Reasoning

Semantic Graph Search

Relationship-aware Retrieval

---

# TOPOLOGY

Provide APIs for

Dashboard Service

Monitoring Service

Automation Service

Validation Service

Workflow Runtime

AI Assistant

---

# EVENTS

Publish

GraphNodeCreated

GraphNodeUpdated

GraphRelationshipCreated

GraphRelationshipRemoved

GraphSynchronized

GraphVersionCreated

ImpactAnalysisCompleted

BlastRadiusCalculated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Synchronization Failed

Graph Import Failed

Graph Export Completed

Snapshot Completed

Critical Relationship Change

---

# TELEMETRY

Integrate Prompt 024.

Trace

Graph Queries

Synchronization

Cypher Execution

Analytics

Traversal

Import

Export

---

# AUDIT

Audit

Node Changes

Relationship Changes

Synchronization

Imports

Exports

Graph Queries

Administrative Operations

---

# REST APIs

Implement

GET /graph/nodes

GET /graph/nodes/{id}

POST /graph/nodes

PUT /graph/nodes/{id}

DELETE /graph/nodes/{id}

GET /graph/relationships

POST /graph/relationships

DELETE /graph/relationships/{id}

POST /graph/query

POST /graph/cypher

GET /graph/topology

GET /graph/dependencies

GET /graph/impact

GET /graph/blast-radius

GET /graph/statistics

GET /graph/analytics

POST /graph/import

POST /graph/export

GET /graph/snapshots

POST /graph/snapshots

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Enforce

Organization isolation

Project isolation

RBAC authorization

Cypher query validation

Parameterized queries only

Graph access auditing

Protection against Cypher injection

---

# PERFORMANCE

Neo4j Index Optimization

Relationship Caching

Query Optimization

Parallel Traversals

Incremental Synchronization

Horizontal API Scaling

Connection Pooling

---

# TESTING

Unit Tests

Integration Tests

Neo4j Tests

Synchronization Tests

Cypher Tests

Analytics Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Knowledge Graph Guide

Neo4j Guide

Cypher Guide

Topology Guide

Graph Analytics Guide

Synchronization Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Neo4j Graph Model

✓ Digital Twin

✓ Relationship Engine

✓ Graph Synchronization

✓ Graph Analytics

✓ Dependency Analysis

✓ Impact Analysis

✓ Blast Radius Analysis

✓ AI Integration

✓ Topology APIs

✓ Import/Export

✓ Snapshots

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

Dashboard Visualization

Business-specific Graph Models

Machine Learning Algorithms

External Graph Databases

Only implement the Enterprise Knowledge Graph Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate Neo4j schema.

Generate PostgreSQL migrations.

Generate OpenAPI documentation.

Generate synchronization engine.

Generate graph analytics engine.

Generate dependency analysis engine.

Generate impact analysis engine.

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

End Prompt 049.

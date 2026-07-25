# Enterprise Workflow SDK

A DAG-based workflow engine (docs/028_Enterprise_Workflow_SDK.md.txt
"OBJECTIVE"): versioned workflow definitions (YAML/JSON/Python DSL),
validation, compilation, a state machine, checkpointing,
rollback/compensation (Saga pattern), human approval, conditional/
parallel/loop-capable execution, retry and circuit breaking, and
integration with this codebase's event, queue, scheduler, telemetry,
metrics, and audit frameworks (Prompts 020, 021, 024, 026).

**Scope note**: business-specific node types (`TASK`, `CONNECTOR`,
`PLUGIN`, `AI`, `WEBHOOK`, `QUEUE`, `EVENT`, `HUMAN_TASK`, `APPROVAL`,
`LOOP`, `SUB_WORKFLOW`) are never implemented by this SDK itself, per
docs/028 "DO NOT IMPLEMENT". A caller registers whatever handlers it
needs into a `NodeHandlerRegistry` (directly, or via
`@node_handler(node_type)`) and this SDK handles graph execution,
state, retry, rollback, and observability identically regardless of
what those handlers actually do. `START`/`END`/`PARALLEL`/`MERGE`/
`DELAY`/`TIMER`/`CONDITION`/`SWITCH`/`SCRIPT` are the only node types
this SDK's own logic fully defines.

## Developer Guide

```python
from shared_core.workflow import (
    WorkflowBuilder, NodeDefinition, NodeType, EdgeDefinition,
    NodeHandlerRegistry, create_workflow_framework, WorkflowContext,
)

# 1. Define a workflow (YAML/JSON also supported via parse_yaml/parse_dict)
definition = (
    WorkflowBuilder("order-fulfillment", "Order Fulfillment", version="1.0.0")
    .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
    .node(NodeDefinition(node_id="charge", node_type=NodeType.TASK, name="Charge card"))
    .node(NodeDefinition(node_id="ship", node_type=NodeType.TASK, name="Ship order"))
    .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
    .edge(EdgeDefinition(from_node_id="start", to_node_id="charge"))
    .edge(EdgeDefinition(from_node_id="charge", to_node_id="ship"))
    .edge(EdgeDefinition(from_node_id="ship", to_node_id="end"))
    .build()
)

# 2. Register handlers for every business-specific node type you use
handlers = NodeHandlerRegistry()

async def charge_card(node, context):
    return {"charged": True}

handlers.register(NodeType.TASK, charge_card)

# 3. Wire the framework and run
manager = create_workflow_framework(handlers)
manager.register_workflow(definition)

context = WorkflowContext(workflow_id="order-fulfillment")
execution_id = await manager.start_execution("order-fulfillment", context)
execution = await manager.wait_execution(execution_id)
execution.status  # WorkflowState.COMPLETED or FAILED -- never raises
```

`WorkflowEngine.run()` never raises for a normal node failure -- it
always returns a `WorkflowExecution` with `status=FAILED` and the
failing node's error recorded in `node_results`, the same
"traceable, not exceptional" contract as
`shared_core.scheduler.executor.JobExecutor.execute`.

### DAG execution model

`PARALLEL`/`MERGE` need no special engine coordination: `dag.execution_plan()`
groups mutually-independent nodes into the same topological "level," and
`WorkflowEngine` runs every node in a level concurrently via `run_parallel()`
regardless of its declared type. A `MERGE` node's readiness check requires
*every* predecessor to have completed; every other node type requires just
*one*.

### Conditions and expressions

```python
from shared_core.workflow import evaluate_if_else, evaluate_switch

evaluate_if_else("amount > 1000", {"amount": 1500})  # True
evaluate_switch({"low": "amount < 100", "high": "amount >= 100"}, {"amount": 500})  # "high"
```

Expressions run inside a `jinja2.sandbox.SandboxedEnvironment` (the same
sandboxing already vetted in Prompt 025's notification templates) --
never `eval()`/arbitrary code, even for `SCRIPT` nodes.

### Rollback and compensation (Saga pattern)

```python
from shared_core.workflow import CompensationRegistry

compensations = CompensationRegistry()

async def refund_card(node_id, output, context):
    ...

compensations.register("charge", refund_card)
```

On failure, `WorkflowEngine` compensates every completed node in
reverse order automatically, transitioning the execution to
`ROLLED_BACK` and auditing which nodes were compensated.

### Human approval

```python
from shared_core.workflow import ApprovalRequest

request = ApprovalRequest(request_id="r1", node_id="approve-refund", approver_id="manager-1")
request.approve(approver="manager-1")  # or .reject(...), .escalate(...), .delegate(...)
```

### Retry and circuit breaking

```python
from shared_core.queue.retry import RetryPolicy
from shared_core.workflow import WorkflowEngine, CircuitBreaker

engine = WorkflowEngine(executor, retry_policy=RetryPolicy(max_attempts=5))
```

`workflow_retry_policy()`/`CircuitBreaker` reuse
`shared_core.queue.retry.RetryPolicy` and
`shared_core.connectors.retry.CircuitBreaker` (Prompt 027) directly --
no third/fourth reimplementation of either.

### Security middleware (RBAC, tenant isolation, privileged audit)

```python
from shared_core.workflow import (
    apply_middleware, build_rbac_middleware, build_tenant_isolation_middleware,
    audit_privileged_middleware, WorkflowOperationContext,
)

handler = apply_middleware(some_handler, [
    build_rbac_middleware(my_permission_checker),
    build_tenant_isolation_middleware("org-123"),
    audit_privileged_middleware,
])
```

Secret Handling/Secure Variables (also under docs/028 "SECURITY") are
enforced separately, by `VariableStore` masking any `VariableScope.SECRET`
variable in its `repr()`.

### Integrations

```python
from shared_core.workflow import (
    WorkflowTaskQueue, build_scheduled_workflow_job, cron_schedule,
    trace_workflow_execution, build_health_report,
)
```

- `queue.py` -- background task dispatch over `shared_core.queue` (Prompt 021).
- `scheduler.py` -- cron/recurring/delayed workflow triggers over `shared_core.scheduler` (Prompt 026).
- `telemetry.py` -- re-exports `trace_workflow_execution`/`trace_workflow_step`/
  `trace_connector_execution`/`trace_ai_request` from `shared_core.telemetry` (Prompt 024).
- `events.py` -- `WorkflowStartedEvent`/`TaskFailedEvent`/etc. over `shared_core.events` (Prompt 020).

## Architecture Notes

- **DAG model chosen over the spec's Stage/Task/Step/Action hierarchy**:
  docs/028 "WORKFLOW MODEL" sketches `Workflow -> Stages -> Tasks ->
  Steps -> Actions -> Result`, while "NODE TYPES" concretely specifies
  a flat DAG of 20 typed nodes with conditional edges. The DAG model
  won because it's the one with an actual specified vocabulary
  (`NodeType`, `EdgeDefinition`, execution planning); "Stages" is left
  as an unimplemented conceptual grouping rather than invented as a
  second, redundant nesting structure.
- **LOOP/SUB_WORKFLOW/APPROVAL delegate to caller handlers, same as
  TASK/CONNECTOR/PLUGIN/AI**: rather than inventing a specific
  loop-body or sub-workflow config schema this SDK would have to
  guess at, these route through `NodeHandlerRegistry` identically to
  every other business-specific node type, per "DO NOT IMPLEMENT" and
  this codebase's "no half-finished implementations" discipline.
- **Configurable `retry_policy` on `WorkflowEngine`**: initially
  hardcoded to `workflow_retry_policy()`'s real ~1s backoff base,
  which made the engine/runtime test suite take ~10s. Added a
  `retry_policy: RetryPolicy | None = None` constructor parameter
  (still defaulting to `workflow_retry_policy()` in production) so
  tests can inject a fast policy -- the same pattern already used by
  `test_scheduler_executor.py`'s `_FAST_RETRY_POLICY`. Brought the
  affected suite down to well under a second.
- **`WorkflowManager` caches `CompiledWorkflow` per (workflow_id,
  version)**: `compile_workflow()` validates and precomputes the
  execution plan, work that shouldn't repeat on every single execution
  of the same registered version -- mirrors
  `ConnectorManager` caching one `ConnectorPool` per (provider, target).
- **New `audit_privileged_access` function, not a new exception
  domain**: docs/028 "SECURITY" lists "Audit Privileged Workflows"
  alongside RBAC/Tenant Isolation/Permission Validation (implemented as
  `middleware.py`'s `build_rbac_middleware`/
  `build_tenant_isolation_middleware`/`audit_privileged_middleware`).
  Unlike Prompt 027, `WorkflowError` already existed in
  `shared_core.exceptions.workflow` (pre-seeded by Prompt 012's
  baseline), so no new exception domain registration was needed here.
- **No naming collisions**: verified via `len(__all__) ==
  len(set(__all__))` across all 41 submodules plus a `hasattr`
  resolution check on every exported name before finalizing
  `__init__.py`.
- **No circular imports**: `workflow -> connectors` (`CircuitBreaker`
  reuse, `AuthorizationError`), `workflow -> queue` (`RetryPolicy`,
  task dispatch), `workflow -> scheduler` (job/schedule wrapping),
  `workflow -> telemetry` (tracing), `workflow -> events` (`EventType.WORKFLOW`),
  `workflow -> metrics`/`monitoring` (Prometheus, health), and
  `workflow -> logging` (audit) are all safe and one-directional --
  none of those packages depend on `workflow`.
- **No new dependencies**: `pyyaml`/`types-pyyaml` (YAML definition
  parsing) were the only additions, and `pyyaml` was already present
  transitively; sandboxed expression evaluation reuses `jinja2.sandbox`
  (already a dependency via Prompt 025's notification templates).

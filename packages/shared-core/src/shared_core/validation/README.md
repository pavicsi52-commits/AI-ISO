# Enterprise Validation Framework

Every API, DTO, configuration, business rule, database request, workflow,
and connector uses this framework. No service duplicates validation logic.

## Validation Guide

Nine layers, always executed in this order (a caller may run any subset,
never out of order):

```
Environment -> Configuration -> API -> Schema -> Business ->
Database -> Permission -> Workflow -> Response
```

Run them through a pipeline:

```python
from shared_core.validation import LayerStep, ValidationLayer, build_pipeline

pipeline = build_pipeline()  # pre-registered with every field/request/response rule
result = pipeline.run([
    LayerStep(ValidationLayer.API, "validate_headers", kwargs={"headers": dict(request.headers), "required": ["x-api-version"]}),
    LayerStep(ValidationLayer.SCHEMA, "validate_email", args=(payload.email,)),
])

if not result.valid:
    raise ValidationError("Validation failed.", details=result.errors)
```

The pipeline stops at the first failing layer and reports which layer
failed (`result.failed_layer`), the accumulated errors/warnings from every
layer that *did* run, and total execution time.

### Field validators

```python
from shared_core.validation.rules import field

field.validate_email("user@example.com")
field.validate_cidr("10.0.0.0/8")
field.validate_semantic_version("1.2.3-rc.1")
field.validate_cron_expression("*/5 * * * *")
field.validate_license_key("ABCDE-12345-FGHIJ-67890")
```

Every field validator returns a
`shared_core.validation.results.ValidationResult` (`valid`, `errors`,
`warnings`, `suggestions`, `execution_time_ms`, `validator_name`,
`severity`) -- call them directly, or run them through the pipeline for
automatic timing/naming.

### Business, database, security, workflow, and connector rules

These take the already-computed fact as a parameter, not a database
connection or an auth token -- this framework validates *shapes and
facts*, not business logic:

```python
from shared_core.validation.rules import business

business.check_quota(current=existing_count, limit=org.project_limit, resource_type="project")
business.check_unique_name("acme", exists=await project_repo.exists_by_name("acme"))
```

## Developer Guide

- **Decorators** (`shared_core.validation.decorators`) run a rule before a
  handler and raise the matching `shared_core.exceptions` type on failure
  -- never a custom response shape:

  ```python
  from shared_core.validation.decorators import validate_permission
  from shared_core.validation.rules.security import validate_permission as check_permission

  @validate_permission(check_permission, role=caller_role, permission=Permission.DELETE)
  async def delete_project(project_id: UUID) -> None: ...
  ```

- **Middleware** (`shared_core.validation.middleware.RequestValidationMiddleware`)
  enforces required headers and a body-size cap automatically for every
  request -- add it alongside `shared_core.exceptions.register_exception_handlers`
  so a failed check becomes a proper Prompt 006 response, not a raw 500.

- **`ValidationManager`**/**`ValidationPipeline`** are the rule engine: a
  manager is a `(layer, name) -> Validator` registry;
  `create_manager_with_defaults()` pre-registers every field/request/
  response rule (they take a single, uniform kind of input). Business/
  database/security/workflow/connector rules are registered per-service,
  since their arguments are use-case-specific.

- **`ValidationContext`** carries identity/tenant scope (organization,
  project, user, locale) through a pipeline run, when a rule needs it.

## Rule Catalog

| Category | Module | Examples |
|---|---|---|
| Field | `rules.field` | uuid, email, hostname, ipv4/ipv6, mac, port, url, password, username, phone, secret name, license key, cron, CIDR, semver, + resource-name family (project/org/asset/playbook/team/job/workflow) |
| Request | `rules.request` | headers, query params, body size, path params, cookies, file upload, multipart, JSON |
| Response | `rules.response` | Prompt 006 envelope compliance |
| Business | `rules.business` | unique name, ownership, org/project isolation, license, dependency, duplicate prevention, quota, approval, maintenance window |
| Database | `rules.database` | foreign key, duplicate records, referential integrity, version, soft delete, tenant isolation |
| Security | `rules.security` | JWT, RBAC/permission, API key, session, secret access, rate limit, CSRF, origin |
| Workflow | `rules.workflow` | circular dependency, infinite loop, missing node, invalid transition, permission, required inputs, timeout, rollback support |
| Connectors | `rules.connectors` | SSH, WinRM, Redfish, SNMP, Docker, Kubernetes, VMware, cloud API -- credentials/timeout/certificate/version/capabilities |

## Examples

See `tests/unit/test_validation_*.py` in this package for a runnable
example of every rule and every framework component.

## Performance

Field validation and the overall pipeline are both well under
docs/016's budgets (<1ms and <10ms respectively) in practice -- every
rule is pure computation (regex, comparisons, small graph traversals),
no I/O.

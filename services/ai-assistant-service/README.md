# AI Assistant Service

The AI-IOS operations copilot (Prompt 046). It answers questions about the
platform's own infrastructure, grounded in retrieved documentation, and can act
through a permission-gated tool layer.

- **Port** `8017` · **Database** `aiios_ai_assistant` · **Redis db** `19`
- **Routes** 32 · **Tests** 349 · **Coverage** 97.84%

## What it does

| Capability | Where |
|---|---|
| Multi-provider chat (8 providers, explicit fallback chain) | `app/clients/`, `app/services/chat.py` |
| Retrieval-augmented generation over real `pgvector` | `app/rag/` |
| Prompt-injection, context, and output guardrails | `app/guardrails/` |
| Permission-aware tool calling with full audit | `app/tool_calling/` |
| Multi-agent decomposition and aggregation | `app/agents/orchestrator.py` |
| Prompt templates with versioning, approval, rollback | `app/prompts/` |
| Durable scoped memory | `app/memory/` |
| Recommendations, AI reports, feedback, analytics | `app/services/` |

## Design decisions worth knowing

**Every platform read uses the caller's own bearer token.** `PlatformClient`
never holds a service credential, so the assistant can never read anything the
asking user could not read themselves. RBAC stays enforced by the owning
service instead of being reimplemented here — a 403 from inventory-service is
the correct, desired outcome.

**Retrieval is hybrid, fused by Reciprocal Rank Fusion** (`RRF_K = 60`). RRF
combines *ranks*, not raw scores, because cosine distance and `ILIKE` matches
are not on comparable scales; averaging them directly would let whichever
metric happens to have the larger range dominate.

**Guardrails neutralise retrieved context rather than dropping it.** A poisoned
wiki page gets its injection markers defanged but still contributes its real
content — dropping it would let an attacker delete arbitrary documents from the
corpus simply by embedding an injection string in them.

**Denied tool calls are recorded and reported.** A refusal is a first-class
audit row and is fed back to the model in plain language, so the assistant can
say "I could not check that because you lack permission" instead of leaving an
unexplained gap. `GET /ai/conversations/{id}/tool-calls` exposes the whole
history, denials included.

**Tool arguments are validated with a bool-is-not-int guard.** In Python `bool`
subclasses `int`, so a naive integer check accepts `True`; the validator
rejects it.

**Agent routing picks the longest matched keyword, not the first.** Keyword
length is a good proxy for specificity: *"check for vulnerability exposure"*
contains both the generic `check` (validation) and the specific `vulnerability`
(security), and must route to security. Table order only breaks ties.

**Embeddings: `builtin` ≠ `local`.** `builtin` is the in-process
`HashingEncoder` (offline, deterministic, **lexical not semantic**); `local` is
a self-hosted OpenAI-compatible endpoint. These once shared the string
`"local"`, which silently downgraded real embedding servers to keyword hashing
— see `app/embeddings/encoder.py` for the full note.

**No scheduler.** Every operation is request-driven, so registering an idle
scheduler would add leader election and heartbeats for no behaviour.

### Enum columns return `str`, so never compare with `is`

Every enum-typed column here is annotated `Mapped[SomeEnum]` but stored in a
plain `String` column — the platform-wide convention. SQLAlchemy therefore
returns a **raw `str`** for any row loaded from Postgres; the annotation is a
lie MyPy cannot catch.

An `is` comparison against an enum member is consequently `False` for *every*
stored row, while passing in a test that keeps the just-assigned enum in the
session identity map. This shipped as a live bug: `PromptService.render` and
`.rollback` rejected every approved prompt in production, and the archive gate
failed open. `_status_of()` normalises once; the regression tests in
`tests/test_services.py` deliberately read back through a **second session**,
which is what makes the failure visible at all.

## Honest limits

- **`POST /ai/chat/stream` is not token-by-token.** It emits a correct SSE
  stream (`meta` → `delta`… → `done`), but the answer is produced first and
  then framed. Closing the gap means adding streaming support to each provider
  client, which is a per-provider change rather than a change to the route.
- **The `builtin` encoder has no semantics.** "server is down" and "host is
  unreachable" share no tokens and score as unrelated. Any deployment that
  cares about answer quality should configure a real embedding provider.
- **`MONTHLY`-style calendar arithmetic is not used here**, but note the
  `chunk_size`/`overlap` defaults (1200/200 characters) are tuned for prose
  runbooks, not code.

## Running it

```bash
# Migrations are a separate step, never baked into CMD, so a multi-replica
# rollout cannot race two containers running the same migration.
uv run alembic upgrade head
uv run uvicorn main:app --host 0.0.0.0 --port 8017
```

```bash
docker build -f services/ai-assistant-service/Dockerfile -t aiios/ai-assistant-service .
```

The build context **must** be the repository root — this service is a member of
the root `uv` workspace and depends on `packages/shared-core` as a path
dependency.

## Configuration

All variables use the `AIIOS_AI_ASSISTANT_SERVICE_` prefix (shared
infrastructure uses plain `AIIOS_`).

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8017` | |
| `JWT_PUBLIC_KEY_PATH` | `keys/jwt_public_key.pem` | Verification key only; no private key ever ships |
| `DEFAULT_PROVIDER` / `DEFAULT_MODEL` | `ollama` / `llama3` | |
| `DEFAULT_EMBEDDING_PROVIDER` | `builtin` | `builtin` \| `ollama` \| `openai` \| `vllm` \| `local` |
| `EMBEDDING_DIMENSIONS` | `1536` | Must match the `vector(n)` column |
| `RAG_TOP_K` | `5` | |
| `CHUNK_SIZE_CHARACTERS` / `CHUNK_OVERLAP_CHARACTERS` | `1200` / `200` | |
| `CONVERSATION_MEMORY_TURNS` | `20` | Recent-window size |
| `MAX_TOOL_CALLS_PER_TURN` | `8` | Bounds the tool loop |
| `MAX_PARALLEL_AGENTS` | `5` | Provider I/O only; never concurrent DB |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AZURE_OPENAI_*` | *(empty)* | A provider with no credential is **not registered**, so asking for it fails with a clear "not configured" instead of a vendor 401 |

## Testing

```bash
uv run python -m pytest --cov=app --cov-report=term-missing
```

Tests run against the repository's real Postgres (with `pgvector`), Redis, and
RabbitMQ, using per-test `SAVEPOINT` isolation.

**Only the model's creativity is stubbed.** `StubModelClient` is a genuine
`ModelClient` implementation returning scripted completions, so orchestration
stays deterministic; each provider's *wire format* is verified separately
against that vendor's own documented response shape via `pytest-httpx`.

**Test hosts must be `127.0.0.1`, never `localhost`.** On Windows `localhost`
resolves to `::1` first and Docker Desktop's IPv6 forwarding hangs rather than
refusing, so every connection burns its full timeout. Diagnosed during Prompt
045; it took the suite from ~5 minutes to ~2.6 seconds.

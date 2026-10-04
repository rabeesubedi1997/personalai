# Changelog

## Phase 3 — Universal Request Engine (2026-10-04)

### Added
- `Request` model + `RequestStatus` lifecycle enum, open-ended
  `request_type`, free-form `customer`/`requirements`/`result` JSON,
  in-row `status_history` audit trail.
- `RequestEngine` (`app/services/request_engine.py`) — sole authority on
  status transitions; enforces the spec's lifecycle graph, raises
  `InvalidTransitionError` on an illegal jump.
- `POST/GET /api/v1/requests`, `GET /api/v1/requests/{id}`,
  `PATCH /api/v1/requests/{id}/status` — tenant-scoped (a request outside
  the caller's tenant 404s, never 403, so existence never leaks).
- 12 new tests (23 → 35 total).

### Verified
- `pytest -q` → 35 passed.
- Live smoke test: created a request, transitioned RECEIVED→UNDERSTANDING
  (200, history recorded), then attempted UNDERSTANDING→COMPLETED directly
  (correctly rejected, 409).

### Caught and fixed during test-writing (reported honestly)
`test_tenant_cannot_access_another_tenants_request` failed on first run.
Root cause was **not** a tenant-isolation bug in the new request code — it
was the Phase 1 dev `/auth/bootstrap` endpoint hard-coding `slug="dev"` for
every tenant it created, so bootstrapping a second user (needed to get a
second tenant for the isolation test) crashed on a unique-constraint
violation before isolation logic ever ran. Fixed by generating a unique
slug per bootstrap call (`dev-<random-hex>`). This is exactly the kind of
thing a real cross-tenant test is for, even this early.

## Phase 2 — AI Core (2026-10-04)

### Added
- `app/tools/`: `Tool` base class, `ToolRegistry` (allow-list enforcement +
  per-tool timeout), 3 mock tools (`get_current_time`,
  `search_knowledge_base`, `create_task`).
- `app/agents/`: `BaseAgent`, `GeneralAssistantAgent` (the Phase 2 demo
  agent), agent registry.
- `app/orchestrator/engine.py`: `AgentOrchestrator` — the controlled agent
  loop, hard-capped by `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` /
  per-tool timeout; returns an explicit status
  (`completed`/`failed`/`max_iterations_reached`/`escalated`), never
  reports success for a run that was cut off.
- `AgentRun` model — persists every run's full tool trace for auditability.
- `GET /api/v1/agents`, `GET /api/v1/tools`, `POST /api/v1/agents/run`.
- 14 new tests (9 → 23 total): orchestrator loop-limit and tool-call-limit
  enforcement, unauthorized-tool denial, tool registry behavior, agent API
  flow (all against a deterministic fake provider for CI reliability).

### Verified
- `pytest -q` → 23 passed.
- Live, real end-to-end runs against **Ollama + qwen2.5:3b-instruct** via
  `POST /api/v1/agents/run`: time lookup, knowledge-base lookup, and task
  creation all correctly selected and executed the right tool
  (~9–40s/run on CPU depending on how many tool round-trips were needed).

### Caught and fixed during live verification (reported honestly, not glossed over)
With the initial system prompt ("use tools when needed"), Qwen2.5 3B
answered "What are your support hours?" by **inventing** an answer ("9 AM
to 5 PM UTC") instead of calling `search_knowledge_base` — a direct
violation of the spec's "never invent business data" rule. Root cause: a
3B model doesn't reliably infer *when* a question needs a tool from a soft
instruction. Fix: rewrote `GeneralAssistantAgent.system_prompt` to mandate
tool use per fact category explicitly. Re-verified live: the model now
calls the tool every time for this class of question, and for a query the
mock knowledge base has no answer for ("Do you offer a student discount?"),
it honestly reports the information is unavailable instead of fabricating
one. Documented in `docs/AGENTS.md` as a standing requirement for every
future agent's system prompt, not a one-off fix.

## Phase 1 — Platform Foundation (2026-10-04)

### Added
- Repository scaffold per `docs/ARCHITECTURE.md`.
- FastAPI backend: config (`pydantic-settings`), structured logging
  (`structlog`), async SQLAlchemy + Alembic (SQLite dev default /
  PostgreSQL-ready via `DATABASE_URL`), Redis client with graceful
  degradation, `/api/v1/health`.
- `Tenant`, `User`, `Role` models; JWT auth (`/auth/login`, `/auth/me`,
  dev-only `/auth/bootstrap`); bcrypt password hashing.
- `AIProvider` abstraction (`generate` / `chat` / `generate_with_tools` /
  `health_check`) with `OllamaProvider` implementation and a provider
  factory switched by `AI_PROVIDER`.
- `/api/v1/ai/smoke-test` endpoint to verify the AI layer live (not part of
  the future agent orchestrator).
- Next.js (App Router, TS) dashboard: live health panel + login form.
- `docker-compose.yml` (Postgres+pgvector / Redis / Ollama / backend /
  frontend) for Linux/production parity.
- `.env.example`, `.gitignore`.
- 9 backend tests (health, auth flow, AI provider unit tests with a mocked
  transport).
- Full docs set: README, ARCHITECTURE, DEVELOPMENT_ROADMAP, DATABASE_SCHEMA,
  API_DOCUMENTATION, SECURITY, AGENTS, TOOLS, CONNECTORS.

### Verified
- `pytest -q` → 9 passed.
- `next build` → compiles and type-checks cleanly.
- Live end-to-end smoke test against **Ollama + qwen2.5:3b-instruct**:
  - `chat()`: correct, concise response in ~8.3s on the i5-10500 CPU (no GPU).
  - `generate_with_tools()`: model correctly selected a mock
    `search_electrician` tool and extracted structured arguments
    (`{"location": "Lalitpur", "date": "tomorrow afternoon"}`) from a
    natural-language request — confirming Qwen2.5 3B is viable for the
    planned agent/tool-calling architecture on this hardware.
- `/api/v1/health` correctly reports Redis as `unavailable` (not installed
  yet) without failing the overall health check or crashing the app.

### Known follow-ups (not blockers, documented honestly)
- Native PostgreSQL + pgvector and a Windows Redis-compatible service
  (Memurai) are not yet installed — both require an elevated shell this
  environment doesn't have. Commands are documented in
  `docs/DEVELOPMENT_ROADMAP.md` for the user to run once needed (Phase 4
  for pgvector specifically).
- `deepseek-r1:1.5b` (pre-existing on this machine) is kept but is not the
  default model, per ENVIRONMENT_REPORT.md reasoning.

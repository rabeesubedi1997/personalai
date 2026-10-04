# Development Roadmap

Phases follow the master spec exactly. Each phase is built, tested, and
documented before the next begins.

## Phase 0 — Environment Discovery ✅ DONE
See [ENVIRONMENT_REPORT.md](../ENVIRONMENT_REPORT.md).

## Phase 1 — Platform Foundation ✅ DONE (this commit)
- FastAPI project structure, config (`pydantic-settings`), structured
  logging (`structlog`), health endpoint (DB + Redis + AI provider checks).
- SQLAlchemy async + Alembic migration scaffold.
- Redis client wrapper (graceful no-op when unavailable).
- Tenant / User / Role models, JWT auth, bcrypt password hashing.
- Next.js dashboard: health status + login form, talking to the real API.
- `docker-compose.yml` + native-dev alternative documented.
- `AIProvider` abstraction + `OllamaProvider`, verified live against
  Ollama + `qwen2.5:3b-instruct` (chat + tool-calling both confirmed working).
- 9 backend tests passing (health, auth, AI provider unit tests).

**Not built yet (by design):** agents, tool registry, workflows, memory,
connectors, approvals, marketplace. The AI provider work above is strictly
infrastructure verification, not Phase 2's orchestrator.

## Phase 2 — AI Core ✅ DONE
- `ToolRegistry` + `Tool` base class (JSON-schema params, permission level,
  timeout) with 3 mock tools (`get_current_time`, `search_knowledge_base`,
  `create_task`).
- `BaseAgent` + one demonstration agent, **General Assistant Agent**, with
  an explicit `allowed_tools` list.
- `AgentOrchestrator`: controlled loop (classify→plan→select tool→validate→
  execute→decide next step→respond), hard-capped by
  `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` / per-tool timeout —
  verified with tests that force endless tool-call requests and confirm the
  loop actually stops.
- `AgentRun` DB model — every run logged (agent, model, request, full tool
  trace, status, error).
- `GET /api/v1/agents`, `GET /api/v1/tools`, `POST /api/v1/agents/run`.
- 14 new tests (9 → 23 total) covering orchestrator limits, unauthorized-tool
  denial, tool registry, and the API.
- **Live-verified against real Ollama + qwen2.5:3b-instruct**, including a
  caught-and-fixed issue: the model initially fabricated a business answer
  instead of calling a tool — fixed by making tool-use mandatory per fact
  category in the system prompt (see `docs/AGENTS.md` for the full
  before/after). This is now a standing rule for every future agent prompt.

## Phase 3 — Universal Request Engine ✅ DONE
- `Request` model: open-ended `request_type` (no enum/schema change needed
  per new business), free-form `customer`/`requirements`/`result` JSON,
  in-row `status_history` audit trail.
- `RequestEngine` state machine (`app/services/request_engine.py`) — the
  sole writer of `request.status`; enforces the spec's lifecycle graph
  (RECEIVED → UNDERSTANDING ⇄ NEEDS_INFORMATION → VALIDATING → SEARCHING →
  MATCHING → WAITING_FOR_CONFIRMATION → EXECUTING → VERIFYING → COMPLETED,
  with CANCELLED/FAILED/ESCALATED reachable as terminal states from
  anywhere non-terminal); illegal jumps raise `InvalidTransitionError`.
- `POST/GET /api/v1/requests`, `GET /api/v1/requests/{id}`,
  `PATCH /api/v1/requests/{id}/status` — all tenant-scoped.
- 12 new tests (23 → 35 total): state machine unit tests (happy path,
  rejected skip-ahead, terminal-state lockout, info-gathering loop-back)
  and API tests (CRUD, filtering, invalid-transition 409, and — the
  important one — cross-tenant access denial).

### Bug caught and fixed by the tenant-isolation test
`test_tenant_cannot_access_another_tenants_request` failed on first run —
not because isolation logic was broken, but because the Phase 1 dev
`/auth/bootstrap` endpoint hard-coded `slug="dev"` for every new tenant, so
creating a second dev user crashed on a unique constraint before isolation
was even exercised. Fixed by generating a unique slug per bootstrap call.
Kept in the record as a concrete example of why this test needs to exist
even with one developer — it caught a real latent bug, not a theoretical
one.

## Phase 4 — Memory ✅ DONE (on SQLite; pgvector migration documented, not yet done)
- `AIProvider.embed(text) -> list[float]` added to the provider interface;
  `OllamaProvider` implements it via `nomic-embed-text` (274MB, CPU-fast —
  verified live at ~0.36s per search including the embedding call).
- `MemoryRecord` model covering all 5 memory kinds from the spec
  (conversation/customer/business/agent/knowledge) in one table,
  distinguished by `memory_type` + free-form `subject_id`.
- `MemoryStore` service: `add()`, `list()`, `search()` (cosine similarity),
  always tenant-scoped.
- `POST/GET /api/v1/memory`, `POST /api/v1/memory/search`.
- 8 new tests (35 → 43 total) covering ranking correctness and tenant
  isolation.
- **Deliberately NOT done, and documented as such** (spec Section 51: make
  the assumption, document it, don't silently under-deliver): this runs on
  SQLite with embeddings stored as JSON and similarity computed in Python —
  fine for dev-scale, not production-scale. The migration to PostgreSQL +
  pgvector's native `Vector` type and indexed `<->` search is specified in
  `docs/DATABASE_SCHEMA.md` but not implemented, since native Postgres isn't
  installed on this dev machine yet (needs the elevated-shell install still
  pending from Phase 0/1).
- Memory is **not yet wired into any agent's tool list** — `general_assistant`
  still uses its Phase 2 hard-coded mock knowledge base, deliberately, so
  as not to touch already-tested Phase 2 behavior. Wiring a real
  memory-backed `search_knowledge_base` tool is a natural Phase 6+ task
  once a real business agent needs it.

## Phase 5 — Security + Approvals
Tool permission levels (READ/SAFE_WRITE/SENSITIVE/CRITICAL), human approval
engine, audit logging, tenant isolation enforcement, prompt-injection
defenses.

## Phase 6 — Tolemate (first real business integration)
Mock connector first; service/provider search, availability, booking,
notifications, follow-up.

## Phase 7 — Ghar Nepal
Property search, enquiries, lead qualification, viewing workflow.

## Phase 8 — Paradise Nepal
Production enquiries, locations, crew, equipment, estimation.

## Phase 9 — Communication
Notification abstraction: email, web, SMS, WhatsApp.

## Phase 10 — Proactive Automation
Scheduler-triggered agents, monitoring, follow-ups, escalation.

## Phase 11 — SaaS
Multi-tenant admin, subscriptions, usage limits, billing.

## Phase 12 — Agent Marketplace
Agent templates, install/configure flow, versioning.

---

## Native local setup vs. Docker (Windows dev machine)

Per `ENVIRONMENT_REPORT.md`, this machine currently has very little free RAM
and no WSL2/Hyper-V active. The recommended Phase 1–4 local setup is:

| Service | Local dev (this machine) | Why |
|---|---|---|
| Database | SQLite file (default) now; native PostgreSQL+pgvector once installed with admin rights | No WSL2/Docker VM overhead; native Postgres install needs an elevated shell this environment doesn't have — **run `choco install postgresql16 -y` yourself in an elevated PowerShell when ready for Phase 4** |
| Redis | Skipped (app degrades gracefully) or native via Memurai Developer (`choco install memurai-developer -y`, elevated) | Redis has no first-class Windows build; Memurai is Redis-API compatible and lightweight |
| Ollama | Native Windows app (already installed) | Already the right choice; no change |
| Backend/Frontend | Run directly with `uvicorn`/`npm run dev` | No containerization overhead needed for a single dev |

Docker Compose remains fully defined in `docker-compose.yml` for: CI, a
teammate's machine with more RAM, or the eventual Linux production server.

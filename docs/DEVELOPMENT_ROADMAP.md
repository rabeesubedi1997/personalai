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

## Phase 2 — AI Core (next)
- `AIProvider` interface is already done; add: `BaseAgent` class, a minimal
  orchestrator loop with iteration/tool-call/timeout limits, a `ToolRegistry`
  with JSON-schema validated tool definitions, agent execution logs.
- One demonstration agent ("General Assistant Agent") using 2-3 mock tools.

## Phase 3 — Universal Request Engine
Generic `Request` lifecycle (RECEIVED → ... → COMPLETED/CANCELLED/FAILED/
ESCALATED), not hard-coded to any one business.

## Phase 4 — Memory
Conversation / customer / business / agent memory + pgvector-backed
knowledge retrieval. Requires switching `DATABASE_URL` to Postgres (pgvector
extension is Postgres-only — not available on the Phase 1 SQLite default).

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

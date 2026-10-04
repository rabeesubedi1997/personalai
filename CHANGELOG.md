# Changelog

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

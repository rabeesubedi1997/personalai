# API Documentation (Phase 1)

Base path: `/api/v1`. Interactive OpenAPI docs are auto-served by FastAPI at
`http://localhost:8000/docs` whenever the backend is running.

## Health
`GET /api/v1/health` — no auth required.
```json
{ "status": "ok", "database": "ok", "redis": "unavailable", "ai_provider": "ok" }
```
`status` is `"ok"` iff the database is reachable; `redis`/`ai_provider` are
reported independently since both are allowed to degrade without taking the
whole app down.

## Auth
- `POST /api/v1/auth/login` — `{ email, password }` → `{ access_token, token_type }`
- `GET /api/v1/auth/me` — Bearer token required → current user
- `POST /api/v1/auth/bootstrap` — dev-only (404s when `APP_ENV=production`);
  creates a fresh tenant + the first `platform_admin` user. One-time use per
  email; returns 409 if the email already exists.

## AI (smoke test only — not the agent system)
- `POST /api/v1/ai/smoke-test` — Bearer token required, `{ prompt }` →
  `{ model, content }`. Calls the configured `AIProvider` directly
  (`AI_PROVIDER=ollama` by default). This exists purely to prove the
  provider wiring works; it is **not** where agent/tool logic will live —
  that begins in Phase 2's orchestrator, exposed at a different endpoint.

## Planned endpoints (future phases)
- `POST /api/v1/agents/run`, `GET /api/v1/agents` — Phase 2
- `GET /api/v1/tools` — Phase 2
- `POST /api/v1/requests`, `GET /api/v1/requests/{id}` — Phase 3
- `POST /api/v1/approvals/{id}/approve|reject` — Phase 5

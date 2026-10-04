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

## Agents & Tools (Phase 2)
- `GET /api/v1/agents` — Bearer token required → list of registered agents
  (`name`, `description`, `allowed_tools`).
- `GET /api/v1/tools` — Bearer token required → list of registered tools
  (`name`, `description`, `permission_level`, `requires_approval`).
- `POST /api/v1/agents/run` — Bearer token required, `{ agent, message }` →
  runs the AI Orchestrator for the named agent and persists an `AgentRun`
  row. Response:
  ```json
  {
    "run_id": "...", "agent": "general_assistant",
    "status": "completed",
    "final_response": "...",
    "iterations": 2,
    "tool_trace": [{"tool": "get_current_time", "arguments": {}, "result": "...", "is_error": false}],
    "model": "qwen2.5:3b-instruct",
    "error": null
  }
  ```
  `status` is one of `completed` / `failed` / `max_iterations_reached` /
  `escalated` — the orchestrator never reports `completed` for a run that
  was actually cut off by a limit or failed. 404s for an unknown `agent`.

## Requests — Universal Request Engine (Phase 3)
All endpoints require a Bearer token and are strictly tenant-scoped: a
request belonging to another tenant 404s exactly like one that doesn't
exist (never a 403 that would confirm it exists).

- `POST /api/v1/requests` — `{ request_type, customer?, requirements?, assigned_agent? }` → 201, status starts at `received`.
- `GET /api/v1/requests` — optional `?status=` / `?request_type=` filters, newest first.
- `GET /api/v1/requests/{id}`
- `PATCH /api/v1/requests/{id}/status` — `{ status, note? }`. Validated
  against the lifecycle state machine (`docs/DATABASE_SCHEMA.md`); an
  illegal jump returns **409**, not 200 — the engine never silently accepts
  an invalid state change.

## Memory (Phase 4)
All tenant-scoped, Bearer token required.
- `POST /api/v1/memory` — `{ memory_type, content, subject_id?, metadata? }` → 201. Embeds `content` via the configured AI provider's `embed()` and stores the vector alongside it.
- `GET /api/v1/memory` — optional `?memory_type=` / `?subject_id=` filters.
- `POST /api/v1/memory/search` — `{ query, memory_type?, top_k? }` → ranked
  `[{ memory, score }]` by cosine similarity against the query's embedding.
  A tenant with no matching memories gets `[]`, never another tenant's data.

## Planned endpoints (future phases)
- `POST /api/v1/approvals/{id}/approve|reject` — Phase 5

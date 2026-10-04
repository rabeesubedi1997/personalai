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

## Agents (continued) — `POST /api/v1/agents/run` response note
As of Phase 5, `status` can also be `awaiting_approval` — the run paused
because it tried to use a `SENSITIVE`/`CRITICAL` tool (e.g. `cancel_booking`).
`tool_trace` will NOT include that tool call (it never executed);
`approval_id` is set so the caller can act on it via the Approvals endpoints
below.

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

## Agent runs — audit query surface (Phase 5)
- `GET /api/v1/agents/runs` — list this tenant's agent runs, newest first.
- `GET /api/v1/agents/runs/{id}` — a single run.
Both return the same shape as `POST /api/v1/agents/run`'s response.

## Approvals — Human Approval Engine (Phase 5)
All tenant-scoped, Bearer token required.
- `GET /api/v1/approvals` — optional `?status=pending|rejected|executed|failed`.
- `GET /api/v1/approvals/{id}`
- `POST /api/v1/approvals/{id}/approve` — `{ note? }`. Actually executes the
  underlying tool now (synchronously) and records the real result —
  status becomes `executed` on success or `failed` on a tool error, never
  a false `executed`. 409 if already decided.
- `POST /api/v1/approvals/{id}/reject` — `{ note? }`. The tool never runs.
  409 if already decided.

When an agent run status is `awaiting_approval` (see Agents below), the
response includes `approval_id` to act on.

## Audit Logs (Phase 5)
- `GET /api/v1/audit-logs` — optional `?event_type=` filter
  (`tool_call_denied`, `approval_approved`, `approval_rejected`,
  `approval_executed`, `approval_execution_failed`). Tenant-scoped.

## Business agents (Phase 6+)
No new endpoints — business agents (e.g. `tolemate_service_booking_agent`)
appear automatically in `GET /api/v1/agents` and their tools in
`GET /api/v1/tools` the moment their `BusinessModule` is registered (see
`docs/CONNECTORS.md`), and run through the exact same
`POST /api/v1/agents/run` as `general_assistant`. This is deliberate: a new
business should never need a new endpoint.

## Planned endpoints (future phases)
None currently — Phase 7+ adds more business modules the same way Phase 6
added Tolemate, not changes to this core API surface.

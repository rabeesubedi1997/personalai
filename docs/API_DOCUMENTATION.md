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

### Multi-turn conversations
`AgentRunRequest` accepts an optional `conversation_id`; the response
always returns one (freshly generated if you didn't send one). Omit it to
start a new conversation; pass the previous response's `conversation_id`
back in to continue it — e.g. the customer replying "yes, book it" to a
prior turn. History is loaded and replayed automatically
(`app/services/conversation_store.py`); you never resend prior messages
yourself. This was added after live-testing Phase 6 showed every call
starting a fresh context with no way to continue — see
`docs/DEVELOPMENT_ROADMAP.md` Phase 6 for the full account and
`tests/test_conversation_continuity.py` for the proof, including that a
turn paused on `awaiting_approval` still replays correctly afterward.

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

## Marketplace (Phase 12)
- `GET /api/v1/marketplace/agents` — the full catalog (every
  code-registered agent), each with `installed: bool` for the caller's
  tenant.
- `GET /api/v1/marketplace/installed` — only the caller's tenant's
  installations.
- `POST /api/v1/marketplace/agents/{slug}/install` — idempotent; 404 for
  an unknown slug.
- `POST /api/v1/marketplace/agents/{slug}/uninstall` — soft-disables (not
  delete); 404 if that agent was never installed for this tenant.

`GET /api/v1/agents` now only lists installed agents, and
`POST /api/v1/agents/run` 404s for an uninstalled one — every tenant gets
the full catalog pre-installed at bootstrap, so this only matters once a
tenant has explicitly uninstalled something.

## Billing (Phase 11)
No real payment processor — plan "selection" is self-service, not a charge.
- `GET /api/v1/billing/plans` — the platform's 3 tiers (free/starter/pro).
- `GET /api/v1/billing/subscription` — caller's tenant: current plan,
  status, and `current_period_agent_runs` (computed from real `AgentRun`
  rows this calendar month, not a separate counter).
- `POST /api/v1/billing/subscription` — `{ plan_slug }`, platform-admin
  only (403 otherwise). 404 for an unknown slug.

`POST /api/v1/agents/run` now also returns **402 Payment Required** if the
tenant's plan's `max_agent_runs_per_month` has been reached, with the
current usage and limit in the error detail.

## Admin (Phase 11)
- `GET /api/v1/admin/tenants` — platform-admin only (403 otherwise). The
  **one intentionally cross-tenant** endpoint in this entire API: lists
  every tenant with its user count, plan, and current usage. Everywhere
  else in this API is strictly tenant-scoped; this one is multi-tenant
  administration by design, gated by role instead of `tenant_id`.

## Scheduler (Phase 10)
- `POST /api/v1/scheduler/run` — platform-admin only (403 otherwise).
  Runs all proactive-automation tasks once, immediately, across every
  tenant (this is an ops/global action, unlike every other endpoint in
  this API, which is tenant-scoped). Returns a per-task summary, e.g.
  `{"failed_agent_run_follow_up": {"checked": 1, "notified": 1}, ...}`.
  The same tasks also run automatically every `SCHEDULER_INTERVAL_SECONDS`
  in the background — this endpoint is for forcing a check now or for
  verification.

## Notifications (Phase 9)
All tenant-scoped, Bearer token required, scoped to the caller's own
notifications (there's no "view another user's notifications" endpoint).
- `GET /api/v1/notifications` — optional `?unread_only=true`. Newest first.
- `POST /api/v1/notifications/{id}/read`
Notifications are created automatically by the platform (e.g. an approval
being requested or decided) — there's no manual "send a notification"
endpoint yet; that's reserved for whenever a real outbound need (e.g. a
scheduled follow-up in Phase 10) requires it.

## Business agents (Phase 6+)
No new endpoints — business agents (e.g. `tolemate_service_booking_agent`)
appear automatically in `GET /api/v1/agents` and their tools in
`GET /api/v1/tools` the moment their `BusinessModule` is registered (see
`docs/CONNECTORS.md`), and run through the exact same
`POST /api/v1/agents/run` as `general_assistant`. This is deliberate: a new
business should never need a new endpoint.

## Integrations — Connect AI Agent (post-roadmap)
Lets a tenant embed one of its installed agents into an **external** site or
app (e.g. the tenant's own ToleMate frontend) as a chat widget, without that
site's visitors ever needing a PersonalOps login.

- `POST /api/v1/integrations/api-keys` — Bearer token, platform-admin only
  (403 otherwise). `{ agent_slug, label }` → 201 with the raw key in
  `api_key`, shown **exactly once**:
  ```json
  { "id": "...", "agent_slug": "tolemate_service_booking_agent", "label": "My website widget",
    "key_prefix": "pak_ab12", "is_active": true, "last_used_at": null, "created_at": "...",
    "api_key": "pak_ab12...<rest only shown here>" }
  ```
  404 for an unknown `agent_slug`; 409 if that agent isn't installed for the
  tenant (install it first via Marketplace).
- `GET /api/v1/integrations/api-keys` — Bearer token, platform-admin only.
  Lists this tenant's keys; never includes the raw key again, only
  `key_prefix`.
- `DELETE /api/v1/integrations/api-keys/{id}` — revokes (`is_active: false`);
  a revoked key's `pak_...` value is rejected by the public endpoint below
  immediately.

### `POST /api/v1/public/chat` — the endpoint the embedded widget calls
No Bearer token. Auth is the `X-API-Key` header instead:
```
POST /api/v1/public/chat
X-API-Key: pak_ab12...
Content-Type: application/json

{ "message": "I need a plumber in Kathmandu", "conversation_id": null }
```
→ the same response shape as `POST /api/v1/agents/run`. 401 if the key is
missing, unrecognized, or revoked. The run always uses the agent the key was
created for — there is no way to pass a different `agent` in the request
body to redirect a key to another agent. Usage counts toward the owning
tenant's plan limits exactly like a dashboard-triggered run (402 if the
tenant is over its plan's `max_agent_runs_per_month`). `conversation_id`
round-trips the same way as `POST /api/v1/agents/run`, so a widget can
maintain a multi-turn chat with its visitor.

This endpoint has its own, separately-configured CORS policy
(`Access-Control-Allow-Origin: *`, see `app/core/public_cors.py`) so it can
be called from any origin — the external site embedding the widget is, by
definition, a different origin than the PersonalOps API. Every other
endpoint in this API keeps the normal, credentialed CORS policy.

## Business Connectors — point a business module at its real API (post-roadmap)
The other direction of "connect": not embedding an agent elsewhere, but
telling an existing business module (Tolemate, Ghar Nepal, Paradise Nepal)
to use its real API instead of the mock data it ships with. See
`docs/CONNECTORS.md` for the full mechanism and what had to be worked
around for Tolemate's real connector specifically.

- `GET /api/v1/business-connectors` — Bearer token, platform-admin only.
  Lists every registered `BusinessModule`, each with its current connector
  config (`null` if unconfigured, i.e. still using the mock):
  ```json
  [{ "business_slug": "tolemate", "name": "tolemate",
     "description": "Tolemate service marketplace...",
     "connector": { "id": "...", "base_url": "http://tolemate.test",
                     "is_enabled": true, "extra_config": null,
                     "created_at": "...", "updated_at": "..." } },
   { "business_slug": "ghar_nepal", "name": "ghar_nepal", "description": "...", "connector": null }]
  ```
- `PUT /api/v1/business-connectors/{business_slug}` — Bearer token,
  platform-admin only. `{ base_url, extra_config? }` → upserts the config
  for this tenant and switches that business to real data immediately (the
  very next tool call). 404 for a `business_slug` that doesn't match any
  registered module; 422 for an empty `base_url`.
- `DELETE /api/v1/business-connectors/{business_slug}` — removes the
  config; the business reverts to its mock connector on the next tool
  call. 404 if nothing was configured.

Tenant-scoped like everything else: one tenant configuring Tolemate's real
URL has no effect on any other tenant, who keep getting the mock until they
configure their own.

## Planned endpoints (future phases)
None currently — Phase 7+ adds more business modules the same way Phase 6
added Tolemate, not changes to this core API surface.

# Database Schema (Phase 1)

Only the foundation tables exist so far. All tenant-owned tables carry a
`tenant_id` column (via `TenantScopedMixin`) — tenant isolation is a day-one
requirement (spec Section 23), enforced at the query layer from Phase 5
onward.

## `tenants`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | |
| slug | string | unique |
| is_active | bool | |
| created_at / updated_at | timestamptz | |

## `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | FK-like, indexed (TenantScopedMixin) |
| email | string | indexed |
| hashed_password | string | bcrypt, never plaintext |
| full_name | string | |
| role | enum | platform_admin / tenant_owner / business_admin / manager / staff / agent_operator / viewer |
| is_active | bool | |
| created_at / updated_at | timestamptz | |

## `agent_runs` (Phase 2)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed (TenantScopedMixin) |
| user_id | UUID | who triggered the run |
| agent_name | string | |
| model | string | which AI model actually handled it |
| request_text | text | |
| final_response | text | |
| status | enum | completed / failed / max_iterations_reached / escalated |
| iterations | int | |
| tool_call_count | int | |
| tool_trace | JSON | ordered list of `{tool, arguments, result, is_error}` |
| error | text, nullable | |
| created_at / updated_at | timestamptz | |

This is the audit trail spec Section 25/31 asks for: every agent run
answers "what did it do, with which tool, what came back, how did it end."
Agents/tools themselves are code-defined (`app/agents/`, `app/tools/`), not
DB-registered yet — a `tools`/`agents` metadata table is deferred until
there's a real need to configure them without a deploy (e.g. the Phase 12
marketplace).

## `requests` (Phase 3)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed (TenantScopedMixin) |
| request_type | string | open-ended (`service_booking`, `property_search`, ...) — not an enum, so a new business never needs a schema change |
| status | enum | see lifecycle below, indexed |
| assigned_agent | string, nullable | |
| customer | JSON | free-form, e.g. `{"name": "John", "location": "Lalitpur"}` |
| requirements | JSON | free-form, business-specific |
| result | JSON, nullable | final outcome data once completed |
| error | text, nullable | |
| status_history | JSON | ordered list of `{from, to, note, at}` — lightweight in-row audit trail |
| created_at / updated_at | timestamptz | |

### Lifecycle (spec Section 13)
```
RECEIVED → UNDERSTANDING ⇄ NEEDS_INFORMATION → VALIDATING → SEARCHING
  → MATCHING → WAITING_FOR_CONFIRMATION → EXECUTING → VERIFYING → COMPLETED
```
Any non-terminal state can also move to `CANCELLED`, `FAILED`, or
`ESCALATED` (all terminal). All of this is enforced by
`app/services/request_engine.py::RequestEngine` — the only code path
allowed to write `request.status`; invalid jumps (e.g. `RECEIVED` straight
to `COMPLETED`) raise `InvalidTransitionError` (→ HTTP 409), and nothing
about this is business-specific — a Tolemate booking and a Ghar Nepal
enquiry use the exact same state machine.

## `memory_records` (Phase 4)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed (TenantScopedMixin) |
| memory_type | enum | `conversation` / `customer` / `business` / `agent` / `knowledge` |
| subject_id | string, nullable, indexed | e.g. a customer id or conversation id; null for business-wide/knowledge entries |
| content | text | |
| record_metadata | JSON | free-form |
| embedding | JSON (list of floats) | **see storage note below** |
| created_at / updated_at | timestamptz | |

**Storage note / documented assumption:** `embedding` is plain JSON, not a
native vector type, because Phase 1–4's default `DATABASE_URL` is SQLite
(no vector extension). `MemoryStore.search()` (`app/memory/store.py`) does
brute-force cosine similarity in Python over tenant-scoped rows — fine at
dev/demo record counts, **not** what should run in production. Once
`DATABASE_URL` points at PostgreSQL, migrate this column to pgvector's
`Vector` type and switch the search query to its indexed `<->` operator
instead of loading every row into Python. This is called out explicitly
rather than left to be discovered later.

## `approvals` (Phase 5)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed |
| agent_run_id | UUID, nullable, indexed | which run triggered this |
| agent_name | string | |
| tool_name | string | |
| arguments | JSON | the tool call's arguments, snapshotted at request time |
| allowed_tool_names | JSON (list) | snapshot of the requesting agent's allow-list, re-checked at approve-time |
| status | enum | `pending` / `rejected` / `executed` / `failed` |
| decided_by_user_id | UUID, nullable | |
| decision_note | text, nullable | |
| result | JSON, nullable | set only if `executed` |
| error | text, nullable | set only if `failed` |
| created_at / updated_at | timestamptz | |

Deliberately business-agnostic: a Tolemate booking cancellation and a Ghar
Nepal viewing cancellation are both just `tool_name="cancel_booking"` with
a different `booking_id` in `arguments` — see
`tests/test_multi_business_generality.py` for the concrete proof.

## `audit_logs` (Phase 5)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed |
| event_type | string, indexed | `tool_call_denied` / `approval_approved` / `approval_rejected` / `approval_executed` / `approval_execution_failed` |
| actor | string | user id, or `"agent"` for an automatic denial |
| tool_name | string, nullable | |
| agent_run_id | UUID, nullable, indexed | |
| approval_id | UUID, nullable, indexed | |
| status | string | |
| detail | JSON | event-specific payload (arguments, result, error, note) — never secrets |
| created_at | timestamptz | |

Focused on security-relevant and human-decision events, not a duplicate of
`AgentRun.tool_trace` (which already captures the full turn-by-turn trace
for successful/failed tool calls within a run).

## `conversation_messages` (Phase 6 follow-up)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed |
| conversation_id | UUID, indexed | groups messages into one thread |
| turn_index | int | authoritative ordering within a conversation (not timestamp-based — avoids SQLite timestamp-collision issues on rapid inserts) |
| role | string | `user` / `assistant` / `tool` |
| content | text | |
| tool_call_id | string, nullable | |
| tool_calls | JSON | serialized `ToolCall` list, for assistant messages that requested tools |
| created_at / updated_at | timestamptz | |

Deliberately separate from `memory_records` (Phase 4): this is an ordered
replay log, not a semantically-searchable store, so writing a turn never
triggers an embedding call. See `app/services/conversation_store.py`.

## `notifications` (Phase 9)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID | indexed |
| user_id | UUID | indexed — the recipient |
| channel | enum | `web` / `email` / `sms` / `whatsapp` |
| subject | string | |
| message | text | |
| status | enum | `sent` / `failed` |
| is_read | bool | web-channel read state |
| notification_metadata | JSON | e.g. `{approval_id, agent_run_id, provider_message_id}` |
| error | text, nullable | set only if `failed` |
| created_at / updated_at | timestamptz | |

For `web`, this row IS the delivery (there's nothing external to fail —
`status` is always `sent`). For `email`/`sms`/`whatsapp`, `status` and
`error` reflect the configured provider's real outcome once one exists;
today's dev-stub providers (`app/services/notifications/channels.py`)
always report success and log what would have been sent.

### Phase 10 additions to existing tables
- `agent_runs.escalation_notified` (bool, default `False`) — set once
  `FailedAgentRunFollowUpTask` has notified the triggering user, so it's
  never re-notified on a later scheduler tick.
- `approvals.reminder_sent` (bool, default `False`) — same idea, for
  `StalePendingApprovalReminderTask`.

No new tables were needed for Phase 10 — the scheduler operates entirely
on the existing `agent_runs`/`approvals`/`requests` tables, which is the
point: proactive automation didn't require any business-specific schema.

## `plans` (Phase 11)
Platform-wide, not tenant-scoped — every tenant sees the same catalog.
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| slug | string, unique | `free` / `starter` / `pro` |
| name | string | |
| price_usd_per_month | float | this platform's own pricing, not a fact about an external business |
| max_agent_runs_per_month | int | the only limit actually enforced today |
| max_tool_calls_per_month | int | stored, not yet enforced — finer-grained billing is a future refinement |
| max_users | int | stored, not yet enforced — no user-invite flow exists yet to check against |
| created_at / updated_at | timestamptz | |

Seeded idempotently on startup (`seed_default_plans`) and defensively
re-seeded on first API use (covers the test client, which never runs
`app.main`'s lifespan).

## `tenant_subscriptions` (Phase 11)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID, unique, indexed | one row per tenant — not `TenantScopedMixin`, since this IS the tenant-to-plan link, not tenant-owned data |
| plan_id | UUID, indexed | |
| status | enum | `active` / `trial` / `cancelled` |
| created_at / updated_at | timestamptz | |

Lazily created on first need (`ensure_subscription`) — defaults to the
`free` plan, so every tenant created before this feature existed (every
tenant from Phases 1-10) gets a sensible default the first time its usage
is checked, with no backfill migration required.

## `agent_installations` (Phase 12)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID, indexed | |
| agent_slug | string, indexed | matches an agent's `name` in the code registry |
| version_installed | string | snapshot of `agent.version` at install time |
| is_enabled | bool | uninstall soft-disables rather than deletes, for auditability |
| created_at / updated_at | timestamptz | |

Unique constraint on `(tenant_id, agent_slug)` — one row per tenant per
agent. The agent *catalog* itself is not a table: it's derived live from
`app.agents.registry.list_agents()`, the same registry every other part of
the platform reads from, so there's exactly one source of truth for "what
agents exist."

## `agent_api_keys` (post-roadmap — Connect AI Agent)
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| tenant_id | UUID, indexed | |
| agent_slug | string | which agent this key is allowed to run — never overridable by the caller |
| label | string | human-readable, e.g. "My ToleMate website widget" |
| key_prefix | string(20) | short, safe-to-display fragment of the raw key (e.g. `pak_ab12`) |
| key_hash | string(64), unique, indexed | SHA-256 of the raw key; the raw key itself is never stored |
| is_active | bool | revoke soft-disables rather than deletes |
| last_used_at | timestamptz, nullable | updated on every successful `POST /api/v1/public/chat` call |
| created_at / updated_at | timestamptz | |

The raw `pak_`-prefixed key is generated with `secrets.token_urlsafe(32)` and
shown to the caller exactly once, at creation — it cannot be retrieved again,
only revoked and replaced. Requests using it hit a system "widget user"
(one lazily-created `viewer`-role `User` per tenant, `app/services/
widget_users.py`) rather than a real human user, so widget-originated runs
still have a valid `user_id` for `AgentRun`/audit purposes without needing a
real login.

## Planned, not yet created (future phases)
- `roles`, `permissions` (fine-grained, beyond the Role enum) — Phase 6+
- `workflows`, `workflow_steps` (if the Request/status_history model proves
  insufficient for multi-step business workflows) — reassessed before Phase 6

## Migrations
Alembic is configured (`backend/alembic/`) against `settings.database_url`.
Phase 1 auto-creates tables on startup for the SQLite dev default
(`app/main.py` lifespan, gated to `APP_ENV in (development, test)`) so
there's no manual step to get running. Once Postgres is the target,
generate and apply real migrations instead of relying on
`create_all`:
```
cd backend
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```
Never hand-edit a production schema directly (spec Section 27).

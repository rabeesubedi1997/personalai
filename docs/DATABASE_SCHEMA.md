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

## Planned, not yet created (future phases)
- `roles`, `permissions` (fine-grained, beyond the Role enum) — Phase 5
- `workflows`, `workflow_steps` (if the Request/status_history model proves
  insufficient for multi-step business workflows) — reassessed before Phase 6
- `conversations`, `messages`, `memories` — Phase 4
- `approvals` — Phase 5
- `notifications` — Phase 9
- `audit_logs` — Phase 5
- `integrations` — Phase 6+

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

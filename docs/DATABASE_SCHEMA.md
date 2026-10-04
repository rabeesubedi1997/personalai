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

## Planned, not yet created (future phases)
- `roles`, `permissions` (fine-grained, beyond the Role enum) — Phase 5
- `agents`, `tools` (registry metadata) — Phase 2
- `requests`, `workflows`, `workflow_steps` — Phase 3
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

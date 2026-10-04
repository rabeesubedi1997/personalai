# Security

## Implemented (Phase 1)
- **Authentication**: JWT bearer tokens (`python-jose`), configurable
  secret/algorithm/expiry via env vars — never hard-coded.
- **Password storage**: bcrypt via passlib; plaintext passwords are never
  logged or persisted.
- **Tenant awareness**: every user row carries `tenant_id`; the schema is
  built so no table can omit it going forward (`TenantScopedMixin`).
- **Secrets**: `.env` is gitignored; `.env.example` has no real values;
  `JWT_SECRET`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` are read only from env.
- **Dev-only endpoints locked down**: `/api/v1/auth/bootstrap` 404s when
  `APP_ENV=production`.
- **CORS**: restricted to the local frontend origin, not `*`.

## Explicitly NOT implemented yet (by phase)
| Control | Target phase |
|---|---|
| Tool permission levels (READ/SAFE_WRITE/SENSITIVE/CRITICAL) | 5 |
| Human approval engine | 5 |
| Audit logging | 5 |
| Enforced tenant isolation at the query layer (beyond schema presence) | 5 |
| Rate limiting | 5 |
| Prompt-injection defenses for untrusted tool/connector content | 5–6 |
| Fine-grained RBAC beyond the `Role` enum | 5 |

## Standing rules (apply from Phase 1 onward, not deferred)
- Never place credentials or secrets inside a prompt sent to any AI
  provider.
- Never log secrets, tokens, or plaintext passwords.
- Treat all external content (customer messages, scraped pages, API
  responses, uploaded documents) as untrusted data once connectors exist —
  never follow instructions embedded in it.
- The AI must never claim an action succeeded when it failed, and must
  never fabricate business data (availability, prices, bookings) — this
  becomes enforceable once Phase 6+ connectors exist; documented here as a
  non-negotiable constraint on all future agent/tool code.

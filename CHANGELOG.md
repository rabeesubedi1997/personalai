# Changelog

## Phase 11 — SaaS (2026-10-04)

### Added
- `Plan` + `TenantSubscription` models; 3 seeded tiers (free/starter/pro —
  this platform's own commercial model, not a fact about an external
  business), idempotently seeded on startup and defensively re-seeded on
  first API use.
- Usage computed by counting real `AgentRun` rows in the current calendar
  month — no separate counter to desync from reality.
- `POST /api/v1/agents/run` now enforces the plan limit: **402 Payment
  Required** once a tenant's `max_agent_runs_per_month` is reached.
- `GET/POST /api/v1/billing/subscription`, `GET /api/v1/billing/plans`.
  Plan switching is self-service selection (platform-admin only) — no
  real payment processor integrated or invented.
- `GET /api/v1/admin/tenants` (platform-admin only): the one intentionally
  cross-tenant endpoint in the API, for multi-tenant administration.
- 14 new tests (124 → 138 total).

### Verified
- `pytest -q` → 138 passed.
- Live, real end-to-end: plan catalog seeded correctly on real server
  boot, a real agent run correctly incremented `current_period_agent_runs`
  from 0 to 1, plan switch to `pro` took effect immediately, and the admin
  endpoint correctly aggregated user count + plan + usage for the tenant.

### Two bugs the test suite caught before commit
1. `get_plan_by_slug` lacked the defensive re-seed `list_plans` had —
   calling `POST /billing/subscription` as the very first billing call in
   a test hit a spurious 404 on an unseeded DB. Fixed by moving the
   defensive seed into `get_plan_by_slug` itself.
2. That fix used "is the `Plan` table empty?" as the seed trigger, which
   broke as soon as a *different* test inserted its own one-off test plan
   first — table no longer empty, but still missing the real catalog.
   Fixed by always calling the already per-slug-idempotent
   `seed_default_plans()` unconditionally, rather than gating it behind a
   fragile emptiness check. Both caught and fixed before the live
   verification above, not discovered by it.

### Documented scope boundary
Real payment processing, white-labeling, and custom per-tenant workflows
are out of scope — they need either real credentials this environment
doesn't have or a concrete need that doesn't exist yet. The architecture
is built so real billing later is "add a payment step before the plan
switch commits," not a redesign.

## Phase 10 — Proactive Automation (2026-10-04)

### Added
- `SchedulerEngine` (`app/scheduler/engine.py`): plain asyncio loop, no
  external scheduling library — started/stopped from `app/main.py`'s
  lifespan, configurable via `SCHEDULER_ENABLED`/`SCHEDULER_INTERVAL_SECONDS`.
- 3 generic `ScheduledTask`s, all business-agnostic:
  `FailedAgentRunFollowUpTask`, `StalePendingApprovalReminderTask`,
  `StaleRequestEscalationTask` (the latter reuses the existing
  `RequestEngine` state machine — no new escalation logic). Each tracks
  its own "already handled" flag (`agent_runs.escalation_notified`,
  `approvals.reminder_sent`) so the idempotency guarantee is real, not
  assumed.
- `POST /api/v1/scheduler/run` (platform-admin only): manually trigger all
  tasks once, for ops and verification without waiting out the real
  interval.
- 10 new tests (114 → 124 total).

### Verified
- `pytest -q` → 124 passed.
- Live, real end-to-end against the running server (not just the test
  suite): confirmed the scheduler actually starts on boot (log line
  `scheduler_started`), created a real pending approval via the live
  Qwen2.5 3B agent, backdated it past the reminder threshold, triggered
  the scheduler manually, and confirmed exactly one "still pending"
  reminder notification appeared — then triggered it again and confirmed
  zero additional notifications, proving the no-duplicate guarantee holds
  for real, not just under a mocked clock in a test.

### Scope boundary, documented not accidental
Phase 10 builds the monitoring/escalation half of spec Section 21
(detect stale/failed state, notify) using direct lightweight queries —
not the agent-invocation half (a timer that runs the full orchestrator
proactively), which is a larger, inherently business-specific feature
better built once a real scheduled business workflow actually needs it.

## Phase 9 — Communication (2026-10-04)

### Added
- `NotificationChannelProvider` abstraction + `NotificationService`
  (`app/services/notifications/`). `WEB` channel is real (an in-app
  notification's delivery IS the DB row); `EMAIL`/`SMS`/`WHATSAPP` are
  clearly-labeled dev stubs — no real provider credentials exist or were
  invented, same pattern as the Phase 6-8 business connectors.
- `Notification` model, `GET /api/v1/notifications`,
  `POST /api/v1/notifications/{id}/read`.
- Wired into the Phase 5 approval flow, not left as unused scaffolding:
  requesting an approval notifies the requester; approving/rejecting
  notifies them again with the real outcome. Requester is resolved from
  the originating `AgentRun`, correctly distinct from whoever decides it.
- 11 new tests (103 → 114 total).

### Verified
- `pytest -q` → 114 passed.
- Live, real end-to-end against Qwen2.5 3B: triggered `cancel_booking`,
  confirmed exactly one "pending approval" notification, approved it,
  confirmed a second "approved and completed" notification with the
  actual tool result (not a canned string) in its message.

### New model-reliability finding (documented, not a system bug)
On the first live attempt, Qwen2.5 3B printed a literal, malformed
`<tool_call>{...}</tool_call>` text block instead of using Ollama's
structured tool-calling response field. Since `result.tool_calls` was
genuinely empty, the orchestrator correctly treated it as a plain text
answer — not a bug, since it can only act on what the provider actually
returns — and correctly created no notification, since no tool call
happened. A slightly more explicit rephrasing on retry worked correctly.
Logged as a known 3B-class/Ollama tool-calling reliability characteristic,
alongside the earlier hallucinated-id and hedging-language findings.

## Phase 8 — Paradise Nepal (2026-10-04)

### Spec correction (done before any code was written)
The master spec described Paradise Nepal as a film-production business.
Checked the real site (https://paradisenepal.kitetool.com/) first: it's a
React/Vite SPA with no public API docs, but its client JS bundle
references `hotel`, `hotels`, `rooms`, `checkin`/`checkout`, `guests`,
`bookings`, `rates`, `packages`, and amenities (`breakfast`, `pool`,
`wifi`) — it's a **hotel booking platform**, not film production. Built
accordingly, with the correction documented in `docs/CONNECTORS.md` and
`app/connectors/paradise_nepal/mock_data.py` rather than silently building
the wrong thing or silently overriding the spec without a trace.

### Added
- `ParadiseNepalModule` (`app/connectors/paradise_nepal/`): mock
  `ParadiseNepalConnector` (fictional hotel/room data), 4 tools
  (`search_hotels`, `get_hotel_details`, `check_room_availability`,
  `create_hotel_booking`), and `HotelBookingAgent` — third instance of the
  Phase 6 `BusinessModule` pattern.
- Registered with the same one-line pattern; zero other core files
  touched, confirmed by the full pre-existing 91-test suite passing
  unchanged before any Paradise Nepal test was written.
- 12 new tests (91 → 103 total).

### Verified
- `pytest -q` → 103 passed.
- Live, real end-to-end against Qwen2.5 3B, a 2-turn conversation: turn 1
  searched hotels in Pokhara; turn 2 ("book the deluxe room there..."),
  using the `conversation_id` from turn 1, correctly chained 4 tool calls
  (search → details → availability → booking) with zero hallucinated ids
  and an accurate final summary (correct booking id, dates, price) — the
  cleanest multi-tool run of the three business integrations so far.

### Recurring minor pattern, documented across two phases now
Both `PropertyAgent` (Phase 7) and `HotelBookingAgent` (Phase 8)
independently added an unprompted hedge ("pending review," "subject to
additional checks") to a `SAFE_WRITE` action that had already completed
successfully with no approval gate. The facts reported were accurate both
times; only the phrasing overstated uncertainty. Flagged as a future
prompt-tightening task across all three business agents, not treated as
urgent — see `docs/DEVELOPMENT_ROADMAP.md` Phase 8.

## Phase 7 — Ghar Nepal (2026-10-04)

### Added
- `GharNepalModule` (`app/connectors/ghar_nepal/`): mock
  `GharNepalConnector` (clearly-labeled fictional property listings), 4
  tools (`search_properties`, `get_property_details`,
  `create_property_enquiry`, `create_viewing_request`), and `PropertyAgent`.
- Registered with the exact one-line pattern from Phase 6
  (`register_business_module(GharNepalModule())`) — no other core file
  touched, confirmed by the full pre-Ghar-Nepal test suite (80 tests)
  passing unchanged before any Ghar Nepal test was written.
- 11 new tests (80 → 91 total): connector unit tests, full search→enquiry
  workflow via the API, honest error reporting for a sold property, and
  viewing cancellation reusing the Phase 5 approval flow.

### Verified
- `pytest -q` → 91 passed.
- Live, real end-to-end against Qwen2.5 3B, a 2-turn conversation: turn 1
  searched with location/budget/bedroom filters and found the correct
  property; turn 2 ("request a viewing for that one"), using the
  `conversation_id` from turn 1, correctly remembered the property id and
  created the viewing request — confirming the Phase 6 follow-up's
  conversation continuity fix generalizes to a second, differently-shaped
  business, not just the one it was built against.

### Minor finding, documented not hidden
The model described a successful, immediate `SAFE_WRITE` viewing-request
creation as "pending human review" — language that only actually applies
to the `SENSITIVE` `cancel_booking` tool. The underlying fact (a real
viewing was created, correct id) was accurate; only the narration was
imprecise. Not a safety issue or a false claim about what happened; noted
for a future prompt tightening pass, not treated as a structural bug.

## Phase 6 follow-up — multi-turn conversation continuity (2026-10-04)

Fixed same day, before moving to Phase 7, by explicit request ("fix for
all before move into next phase").

### Added
- `ConversationMessage` model + `ConversationStore`
  (`app/services/conversation_store.py`): a dedicated, tenant-scoped,
  ordered thread log — intentionally separate from the Phase 4 Memory
  system (which embeds every record; a chat turn doesn't need semantic
  search, just ordered replay, so this avoids an embedding call per turn).
- `AgentOrchestrator.run(..., history=...)` + `OrchestratorResult.new_messages`.
- `conversation_id` on `AgentRunRequest` (optional) and `AgentRunResponse`
  (always present) — omit to start fresh, pass back in to continue.
- Correctness fix bundled in: a turn that pauses early (approval required,
  or the tool-call limit hit mid-batch) now synthesizes a "not executed
  yet" tool-result message for every unresolved tool_call before
  returning, so the persisted conversation is always valid to replay (a
  dangling assistant `tool_calls` message with no response would otherwise
  be malformed on the next chat-completions call).
- 5 new tests (75 → 80 total): replay correctness, cross-call persistence,
  tenant-isolation of conversation history, and the dangling-tool-call
  regression check.

### Verified
- `pytest -q` → 80 passed.
- Live, real end-to-end against Qwen2.5 3B: replayed the exact scenario
  that exposed the original gap. Turn 1 ("find an electrician... my name
  is Ram Shrestha") found a provider and asked for confirmation. Turn 2
  ("yes, please go ahead and book it"), sent with the `conversation_id`
  from turn 1, correctly remembered the provider id and date and booked
  directly — no re-search needed, no information repeated by the caller.
  Also verified live that a conversation paused on `awaiting_approval`
  continues on a second real API call without error.

## Phase 6 — Tolemate integration + business-plugin architecture (2026-10-04)

### Added
- `BusinessModule` plugin system (`app/connectors/base.py`,
  `app/connectors/registry.py`): a new business registers its tools +
  agent(s) with one `register_business_module(...)` call; `app/tools/registry.py`
  and `app/agents/registry.py` pick them up automatically. Built
  specifically so Ghar Nepal, Paradise Nepal, and any future business can
  be added later without touching the core.
- `TolemateModule` (`app/connectors/tolemate/`): mock `TolemateConnector`
  (clearly-labeled fictional provider data — no real API access
  confirmed), 3 tools (`search_service_providers`,
  `check_provider_availability`, `create_service_booking`), and
  `ServiceBookingAgent` — the platform's first real business agent.
- `tests/test_business_module_extensibility.py`: defines an entirely new,
  fictional business (a Paradise Nepal-style crew lookup) **inside the
  test itself**, registers it with the one-line API, and proves it's
  immediately listed and runnable — the concrete, re-checked-on-every-run
  guarantee behind "add multiple businesses later."
- 13 new tests (62 → 75 total): Tolemate connector unit tests, full
  search→check→book workflow via the API, honest error reporting for an
  unavailable date, and cancellation reusing the Phase 5 approval flow.

### Verified
- `pytest -q` → 75 passed.
- Live, real end-to-end against Qwen2.5 3B, two runs:
  1. Asked it to find+book an electrician with all details given — it
     found the right provider then asked for human confirmation instead
     of booking immediately. Safe, not wrong, but revealed a real gap:
     `/agents/run` has no multi-turn conversation continuation yet (noted
     in `docs/DEVELOPMENT_ROADMAP.md`, not yet fixed).
  2. Re-run with an explicit "don't ask, just do it" directive: the model
     completed the full search→check→book chain, but partway through
     **hallucinated a provider id** (`"P1"` instead of the real
     `"PRV-001"` it had just been given), got genuine tool errors from
     that, logged a `create_task` noting the failure, retried the search,
     read the id correctly the second time, and completed the booking —
     the final answer only claimed success once the tool had actually
     confirmed the booking. The safety design (tool errors are real data
     fed back, never silently papered over; success is never claimed
     before the tool confirms it) held up under an actual model mistake,
     not just a contrived test of it.

### Scope notes
- Notifications (Phase 9) and scheduled follow-up (Phase 10) remain
  explicit stubs — not built here, as planned.
- Ghar Nepal and Paradise Nepal are not built yet (Phase 7/8) — only the
  plugin mechanism and one real example (Tolemate) exist so far.

## Phase 5 — Security + Approvals (2026-10-04)

### Added
- `ApprovalRequiredError` + structural registration check: `SENSITIVE`/
  `CRITICAL` tools cannot be registered without `requires_approval=True`
  (`ValueError` at registration, not a runtime surprise).
- `Approval` model + `POST/GET /api/v1/approvals[/​{id}][/approve|reject]`.
  Approve synchronously executes the underlying tool and records the real
  result; reject guarantees it never runs. Both are 409 on an
  already-decided approval.
- `AuditLog` model + `GET /api/v1/audit-logs` (optional `?event_type=`):
  every tool denial and every approval decision, queryable.
- `GET /api/v1/agents/runs[/​{id}]`: tenant-scoped audit query surface for
  past agent runs.
- Tool argument JSON-schema validation (`jsonschema`) before any tool
  executes.
- Prompt-injection defense: tool results are wrapped in an explicit "DATA
  ONLY, NOT INSTRUCTIONS" marker before being sent back to the model
  (`app/orchestrator/engine.py::_TOOL_RESULT_WRAPPER`).
- New generic `cancel_booking` tool (SENSITIVE, approval-gated) —
  business-agnostic booking management, usable by any future connector.
- `tests/test_multi_business_generality.py` — by explicit user request:
  a concrete test proving the Request engine, lifecycle, and
  booking-approval flow all work identically for three different
  simulated businesses (Tolemate-style service booking, Ghar Nepal-style
  property enquiry, Paradise Nepal-style production enquiry) with zero
  per-business branching anywhere in the core.
- 18 new tests (44 → 62 total).

### Verified
- `pytest -q` → 62 passed.
- Live, real end-to-end against Qwen2.5 3B: asked it to cancel a real
  booking → confirmed the tool did NOT execute (`tool_trace: []`,
  `status: awaiting_approval`) → approved via the API → confirmed it then
  executed for real (`status: executed`, real result payload) → confirmed
  a second decision on the same approval was rejected (409) → confirmed
  both the approval and its execution appear in `GET /api/v1/audit-logs`.

### Documented
- `docs/SECURITY.md`, `docs/TOOLS.md`, `docs/DATABASE_SCHEMA.md`,
  `docs/API_DOCUMENTATION.md` updated.
- `docs/CONNECTORS.md` gained an explicit "recipe for adding a real
  business later" section, naming exactly which 4 things get added
  (connector, tools, agent, request_type string) and which core files
  never need to change — backed by the generality test above, not just
  asserted.

## Phase 4 follow-up — wire memory into the demo agent (2026-10-04)

Done same-day by explicit request, before moving to Phase 5.

### Added
- `ToolContext` (`app/tools/base.py`): `tenant_id`, `db` session,
  `ai_provider`, built per-request in `POST /api/v1/agents/run` and
  threaded through `AgentOrchestrator.run()` -> `ToolRegistry.execute()` ->
  `Tool.execute()`. All tools now receive it (most ignore it).
- `app/tools/memory_tools.py`: real `SearchKnowledgeBaseTool`, replacing
  the Phase 2 hardcoded-dict mock of the same name — genuine
  `MemoryStore`-backed cosine-similarity search over the tenant's
  `knowledge` memory records, with `MATCH_THRESHOLD = 0.55` separating a
  real match from "no match" (never returns a weak, probably-wrong guess).

### Verified
- `pytest -q` → 44 passed (net +1; one old mock test replaced by two —
  real-match and honest-no-match — for the new implementation).
- Live, real end-to-end via `POST /api/v1/agents/run` against Qwen2.5 3B +
  nomic-embed-text, 3 scenarios:
  1. "What are your support hours?" → correctly retrieved and answered from
     the seeded 24/7 support memory.
  2. "How long do refunds take?" → correctly retrieved the *different*
     refund-policy memory, not the support one — confirms real
     discrimination between documents, not a lucky single-doc test.
  3. "Do you offer a student discount?" (no matching memory exists) →
     tool correctly reported no match; the agent told the user the
     information isn't available rather than guessing. This is the same
     honesty property verified in the original Phase 2 fix, now proven
     against real stored data instead of a hardcoded canned answer.

## Phase 4 — Memory (2026-10-04)

### Added
- `AIProvider.embed(text) -> list[float]` added to the provider interface
  (new abstract method); `OllamaProvider` implements it via a separate
  lightweight embedding model (`nomic-embed-text`, ~274MB), configurable via
  `OLLAMA_EMBEDDING_MODEL`.
- `MemoryRecord` model: one table for all 5 memory kinds (conversation,
  customer, business, agent, knowledge), tenant-scoped, with JSON
  `embedding` storage (see storage note below).
- `MemoryStore` service (`app/memory/store.py`): `add()` (embeds + persists),
  `list()` (filtered by type/subject), `search()` (cosine similarity
  ranking), all tenant-scoped.
- `POST/GET /api/v1/memory`, `POST /api/v1/memory/search`.
- 8 new tests (35 → 43 total): store-level ranking correctness (with a
  deterministic keyword-based fake embedding) and tenant isolation, plus
  API-level equivalents.

### Verified
- `pytest -q` → 43 passed.
- Live, real end-to-end: added 3 knowledge entries via the actual Ollama
  `nomic-embed-text` model, searched "Is there an electrician available in
  Lalitpur?" — correctly ranked the electrician document highest
  (score 0.85) over the plumbing document (0.62), excluding the unrelated
  refund-policy document entirely. ~0.36s per search including the
  embedding call — embeddings are far cheaper than generation, as expected.

### Documented, not deferred silently (spec Section 51)
- Runs on SQLite with embeddings as JSON and brute-force Python cosine
  similarity — correct and fully tested, but not how this should run at
  scale. The PostgreSQL + pgvector migration (native `Vector` column,
  indexed `<->` search) is fully specified in `docs/DATABASE_SCHEMA.md` but
  not implemented, since native Postgres isn't installed on this machine
  yet (still blocked on the elevated-shell install noted since Phase 0/1).
- Memory is not yet wired into any agent's tools — `general_assistant`
  still uses its Phase 2 hard-coded mock knowledge base unchanged, so as
  not to disturb already-tested behavior. A real memory-backed knowledge
  tool is deferred to Phase 6+ when a real business agent needs it.

## Phase 3 — Universal Request Engine (2026-10-04)

### Added
- `Request` model + `RequestStatus` lifecycle enum, open-ended
  `request_type`, free-form `customer`/`requirements`/`result` JSON,
  in-row `status_history` audit trail.
- `RequestEngine` (`app/services/request_engine.py`) — sole authority on
  status transitions; enforces the spec's lifecycle graph, raises
  `InvalidTransitionError` on an illegal jump.
- `POST/GET /api/v1/requests`, `GET /api/v1/requests/{id}`,
  `PATCH /api/v1/requests/{id}/status` — tenant-scoped (a request outside
  the caller's tenant 404s, never 403, so existence never leaks).
- 12 new tests (23 → 35 total).

### Verified
- `pytest -q` → 35 passed.
- Live smoke test: created a request, transitioned RECEIVED→UNDERSTANDING
  (200, history recorded), then attempted UNDERSTANDING→COMPLETED directly
  (correctly rejected, 409).

### Caught and fixed during test-writing (reported honestly)
`test_tenant_cannot_access_another_tenants_request` failed on first run.
Root cause was **not** a tenant-isolation bug in the new request code — it
was the Phase 1 dev `/auth/bootstrap` endpoint hard-coding `slug="dev"` for
every tenant it created, so bootstrapping a second user (needed to get a
second tenant for the isolation test) crashed on a unique-constraint
violation before isolation logic ever ran. Fixed by generating a unique
slug per bootstrap call (`dev-<random-hex>`). This is exactly the kind of
thing a real cross-tenant test is for, even this early.

## Phase 2 — AI Core (2026-10-04)

### Added
- `app/tools/`: `Tool` base class, `ToolRegistry` (allow-list enforcement +
  per-tool timeout), 3 mock tools (`get_current_time`,
  `search_knowledge_base`, `create_task`).
- `app/agents/`: `BaseAgent`, `GeneralAssistantAgent` (the Phase 2 demo
  agent), agent registry.
- `app/orchestrator/engine.py`: `AgentOrchestrator` — the controlled agent
  loop, hard-capped by `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` /
  per-tool timeout; returns an explicit status
  (`completed`/`failed`/`max_iterations_reached`/`escalated`), never
  reports success for a run that was cut off.
- `AgentRun` model — persists every run's full tool trace for auditability.
- `GET /api/v1/agents`, `GET /api/v1/tools`, `POST /api/v1/agents/run`.
- 14 new tests (9 → 23 total): orchestrator loop-limit and tool-call-limit
  enforcement, unauthorized-tool denial, tool registry behavior, agent API
  flow (all against a deterministic fake provider for CI reliability).

### Verified
- `pytest -q` → 23 passed.
- Live, real end-to-end runs against **Ollama + qwen2.5:3b-instruct** via
  `POST /api/v1/agents/run`: time lookup, knowledge-base lookup, and task
  creation all correctly selected and executed the right tool
  (~9–40s/run on CPU depending on how many tool round-trips were needed).

### Caught and fixed during live verification (reported honestly, not glossed over)
With the initial system prompt ("use tools when needed"), Qwen2.5 3B
answered "What are your support hours?" by **inventing** an answer ("9 AM
to 5 PM UTC") instead of calling `search_knowledge_base` — a direct
violation of the spec's "never invent business data" rule. Root cause: a
3B model doesn't reliably infer *when* a question needs a tool from a soft
instruction. Fix: rewrote `GeneralAssistantAgent.system_prompt` to mandate
tool use per fact category explicitly. Re-verified live: the model now
calls the tool every time for this class of question, and for a query the
mock knowledge base has no answer for ("Do you offer a student discount?"),
it honestly reports the information is unavailable instead of fabricating
one. Documented in `docs/AGENTS.md` as a standing requirement for every
future agent's system prompt, not a one-off fix.

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

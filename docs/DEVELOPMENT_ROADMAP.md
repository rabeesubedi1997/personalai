# Development Roadmap

Phases follow the master spec exactly. Each phase is built, tested, and
documented before the next begins.

## Phase 0 — Environment Discovery ✅ DONE
See [ENVIRONMENT_REPORT.md](../ENVIRONMENT_REPORT.md).

## Phase 1 — Platform Foundation ✅ DONE (this commit)
- FastAPI project structure, config (`pydantic-settings`), structured
  logging (`structlog`), health endpoint (DB + Redis + AI provider checks).
- SQLAlchemy async + Alembic migration scaffold.
- Redis client wrapper (graceful no-op when unavailable).
- Tenant / User / Role models, JWT auth, bcrypt password hashing.
- Next.js dashboard: health status + login form, talking to the real API.
- `docker-compose.yml` + native-dev alternative documented.
- `AIProvider` abstraction + `OllamaProvider`, verified live against
  Ollama + `qwen2.5:3b-instruct` (chat + tool-calling both confirmed working).
- 9 backend tests passing (health, auth, AI provider unit tests).

**Not built yet (by design):** agents, tool registry, workflows, memory,
connectors, approvals, marketplace. The AI provider work above is strictly
infrastructure verification, not Phase 2's orchestrator.

## Phase 2 — AI Core ✅ DONE
- `ToolRegistry` + `Tool` base class (JSON-schema params, permission level,
  timeout) with 3 mock tools (`get_current_time`, `search_knowledge_base`,
  `create_task`).
- `BaseAgent` + one demonstration agent, **General Assistant Agent**, with
  an explicit `allowed_tools` list.
- `AgentOrchestrator`: controlled loop (classify→plan→select tool→validate→
  execute→decide next step→respond), hard-capped by
  `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` / per-tool timeout —
  verified with tests that force endless tool-call requests and confirm the
  loop actually stops.
- `AgentRun` DB model — every run logged (agent, model, request, full tool
  trace, status, error).
- `GET /api/v1/agents`, `GET /api/v1/tools`, `POST /api/v1/agents/run`.
- 14 new tests (9 → 23 total) covering orchestrator limits, unauthorized-tool
  denial, tool registry, and the API.
- **Live-verified against real Ollama + qwen2.5:3b-instruct**, including a
  caught-and-fixed issue: the model initially fabricated a business answer
  instead of calling a tool — fixed by making tool-use mandatory per fact
  category in the system prompt (see `docs/AGENTS.md` for the full
  before/after). This is now a standing rule for every future agent prompt.

## Phase 3 — Universal Request Engine ✅ DONE
- `Request` model: open-ended `request_type` (no enum/schema change needed
  per new business), free-form `customer`/`requirements`/`result` JSON,
  in-row `status_history` audit trail.
- `RequestEngine` state machine (`app/services/request_engine.py`) — the
  sole writer of `request.status`; enforces the spec's lifecycle graph
  (RECEIVED → UNDERSTANDING ⇄ NEEDS_INFORMATION → VALIDATING → SEARCHING →
  MATCHING → WAITING_FOR_CONFIRMATION → EXECUTING → VERIFYING → COMPLETED,
  with CANCELLED/FAILED/ESCALATED reachable as terminal states from
  anywhere non-terminal); illegal jumps raise `InvalidTransitionError`.
- `POST/GET /api/v1/requests`, `GET /api/v1/requests/{id}`,
  `PATCH /api/v1/requests/{id}/status` — all tenant-scoped.
- 12 new tests (23 → 35 total): state machine unit tests (happy path,
  rejected skip-ahead, terminal-state lockout, info-gathering loop-back)
  and API tests (CRUD, filtering, invalid-transition 409, and — the
  important one — cross-tenant access denial).

### Bug caught and fixed by the tenant-isolation test
`test_tenant_cannot_access_another_tenants_request` failed on first run —
not because isolation logic was broken, but because the Phase 1 dev
`/auth/bootstrap` endpoint hard-coded `slug="dev"` for every new tenant, so
creating a second dev user crashed on a unique constraint before isolation
was even exercised. Fixed by generating a unique slug per bootstrap call.
Kept in the record as a concrete example of why this test needs to exist
even with one developer — it caught a real latent bug, not a theoretical
one.

## Phase 4 — Memory ✅ DONE (on SQLite; pgvector migration documented, not yet done)
- `AIProvider.embed(text) -> list[float]` added to the provider interface;
  `OllamaProvider` implements it via `nomic-embed-text` (274MB, CPU-fast —
  verified live at ~0.36s per search including the embedding call).
- `MemoryRecord` model covering all 5 memory kinds from the spec
  (conversation/customer/business/agent/knowledge) in one table,
  distinguished by `memory_type` + free-form `subject_id`.
- `MemoryStore` service: `add()`, `list()`, `search()` (cosine similarity),
  always tenant-scoped.
- `POST/GET /api/v1/memory`, `POST /api/v1/memory/search`.
- 8 new tests (35 → 43 total) covering ranking correctness and tenant
  isolation.
- **Deliberately NOT done, and documented as such** (spec Section 51: make
  the assumption, document it, don't silently under-deliver): this runs on
  SQLite with embeddings stored as JSON and similarity computed in Python —
  fine for dev-scale, not production-scale. The migration to PostgreSQL +
  pgvector's native `Vector` type and indexed `<->` search is specified in
  `docs/DATABASE_SCHEMA.md` but not implemented, since native Postgres isn't
  installed on this dev machine yet (needs the elevated-shell install still
  pending from Phase 0/1).
- **Update:** memory *is* now wired into `general_assistant` (done as an
  explicit follow-up, same day, by request — see below) — its
  `search_knowledge_base` tool is real, `MemoryStore`-backed semantic
  search, not the Phase 2 hardcoded dict. This required adding `ToolContext`
  (tenant_id/db/ai_provider) threaded through `Tool.execute()` ->
  `ToolRegistry.execute()` -> `AgentOrchestrator.run()`, since a real tool
  needs real dependencies a mock never did. 1 net new test (44 total);
  live-verified distinguishing two unrelated knowledge entries and honestly
  reporting "no match" for an unanswerable question.

## Phase 5 — Security + Approvals ✅ DONE
- Permission levels structurally enforced: `ToolRegistry.register()`
  refuses a `SENSITIVE`/`CRITICAL` tool that doesn't set
  `requires_approval=True`.
- `Approval` model + full engine: `POST /api/v1/approvals/{id}/approve|reject`.
  A gated tool call never executes inline — it raises
  `ApprovalRequiredError`, the orchestrator pauses the run
  (`AgentRunStatus.AWAITING_APPROVAL`), and only `/approve` actually runs
  it, recording the real result (`executed` or `failed`, never a false
  success).
- `AuditLog` model + `GET /api/v1/audit-logs`: every tool denial and every
  approval decision is queryable, not just logged to stdout.
- Tool argument JSON-schema validation before execution.
- Prompt-injection defense (first layer): tool output wrapped in an
  explicit "DATA ONLY, NOT INSTRUCTIONS" marker before being sent back to
  the model.
- `GET /api/v1/agents/runs[/​{id}]` added as an explicit audit query surface.
- New generic `cancel_booking` tool (SENSITIVE) — proves booking
  cancellation/management is a core platform capability usable by any
  future business, not something rebuilt per connector.
- **18 new tests (44 → 62 total)**, including
  `tests/test_multi_business_generality.py` — a concrete, passing
  demonstration (not just a doc claim) that the Request engine, lifecycle,
  and booking-approval flow all work identically across three different
  simulated businesses (Tolemate-style, Ghar Nepal-style, Paradise
  Nepal-style) with zero per-business code in the core.
- Live-verified against real Qwen2.5 3B: asked it to cancel a real booking
  id, confirmed the tool did NOT execute (empty tool_trace, status
  `awaiting_approval`), approved it via the API, confirmed it then
  executed for real, confirmed a second decision on the same approval was
  rejected (409), and confirmed both the approval and its execution
  appear in the audit log.

## Phase 6 — Tolemate (first real business integration) ✅ DONE (mock connector)
- **`BusinessModule` plugin system** (`app/connectors/base.py` +
  `registry.py`), built specifically so adding future businesses
  (Ghar Nepal, Paradise Nepal, anything else) is a single
  `register_business_module(...)` call — `app/tools/registry.py` and
  `app/agents/registry.py` pick up a module's tools/agents automatically,
  with zero other core-file changes required. Proven by
  `tests/test_business_module_extensibility.py`, which registers an
  entirely new fictional business from inside the test itself.
- `TolemateModule`: mock `TolemateConnector` (clearly-labeled fictional
  provider data — no real API access confirmed), 3 tools
  (`search_service_providers`, `check_provider_availability`,
  `create_service_booking`), and `ServiceBookingAgent` composing those with
  core tools (`cancel_booking`, `search_knowledge_base`, `create_task`).
- 13 new tests (62 → 75 total): connector unit tests, full search→check→book
  workflow, honest error reporting on an unavailable date, and reuse of the
  Phase 5 approval flow for cancellation.
- Live-verified against real Qwen2.5 3B, two runs:
  1. A cautious run where the model found a provider then asked for
     confirmation rather than booking immediately — safe, not a bug, but
     revealed each `/agents/run` call is currently a fresh single-turn
     conversation with no continuation across calls (a real gap, noted
     below, not a Phase 6 scope item).
  2. A fully-directed run that completed the whole chain. **Caught and
     worth recording honestly**: partway through, the model misread the
     search result and hallucinated a provider id (`"P1"` instead of the
     real `"PRV-001"`), got real tool errors from that, logged a
     `create_task` noting the failure, retried the search, extracted the
     correct id, and completed the booking successfully — and the final
     answer only claimed success once the tool had actually confirmed it.
     This is the safety architecture (error-as-data, never-claim-success)
     working exactly as designed under a real model mistake, not a
     hypothetical test of it.
- **Not done, and intentionally out of scope for Phase 6**: notifications
  (Phase 9) and scheduled/automated follow-up (Phase 10) remain stubs —
  only the request→search→book→cancel-with-approval path was built.
- **Gap fixed same day, before moving to Phase 7 (by explicit request)**:
  multi-turn conversation continuation. See "Phase 6 follow-up" below.

## Phase 6 follow-up — multi-turn conversation continuity ✅ DONE
- New `ConversationMessage` model + `ConversationStore`
  (`app/services/conversation_store.py`) — a dedicated, tenant-scoped,
  ordered thread log. Deliberately NOT built on the Phase 4 Memory system:
  that embeds every record for semantic search, which would mean an
  embedding call on every chat turn just to support sequential replay —
  real latency for no benefit, since replay needs order, not similarity.
- `AgentOrchestrator.run()` gained an optional `history: list[ChatMessage]`
  parameter and now returns `new_messages` (exactly what this call added,
  for the caller to persist) — backward compatible, no existing call site
  needed to change except the one that now passes history through.
- `POST /api/v1/agents/run` gained `conversation_id` (request, optional;
  response, always present). Omit to start fresh; pass the prior
  response's value back in to continue.
- **Correctness fix included**: a turn that pauses early (approval
  required, or the tool-call limit hit mid-turn) used to leave an
  assistant `tool_calls` message with no matching tool-result message in
  the conversation log — replaying that back to a chat-completions API on
  the next turn would be malformed. The orchestrator now synthesizes a
  "not executed yet" tool-result message for every unresolved call before
  returning, so every persisted conversation is always valid to replay.
- 5 new tests (75 → 80 total), including a tenant-isolation check
  (continuing another tenant's `conversation_id` silently starts fresh
  rather than leaking their history) and the dangling-tool-call regression
  check.
- Live-verified against real Qwen2.5 3B: replayed the exact scenario that
  exposed the gap — turn 1 found a provider and asked for confirmation;
  turn 2 ("yes, book it"), using the same `conversation_id`, correctly
  remembered the provider id and date from turn 1 and booked directly
  without re-searching. Also verified a conversation paused on
  `awaiting_approval` continues without error on the next real API call.

## Phase 7 — Ghar Nepal ✅ DONE (mock connector)
Second real instance of the Phase 6 `BusinessModule` plugin pattern —
confirming it generalizes beyond Tolemate's shape, not just working once
by coincidence.
- `GharNepalModule` (`app/connectors/ghar_nepal/`): mock `GharNepalConnector`
  (clearly-labeled fictional listings), 4 tools (`search_properties`,
  `get_property_details`, `create_property_enquiry`,
  `create_viewing_request`), and `PropertyAgent` — composing those with
  the same core tools (`cancel_booking`, `search_knowledge_base`,
  `create_task`) Tolemate's agent uses.
- Registered with the same one line
  (`register_business_module(GharNepalModule())`) proven in Phase 6 — zero
  other core files touched, re-confirmed by the full existing suite
  passing unchanged before any Ghar Nepal-specific tests were added.
- 11 new tests (80 → 91 total): connector unit tests, full
  search→enquiry workflow, honest error reporting for a sold property, and
  viewing cancellation reusing the Phase 5 approval flow.
- Live-verified against real Qwen2.5 3B across a 2-turn conversation:
  turn 1 searched and found the right property with all filters applied
  (location, budget, bedrooms); turn 2 ("request a viewing for that one"),
  using the `conversation_id` from turn 1, correctly remembered the
  property id and created the viewing request — confirming conversation
  continuity (the Phase 6 follow-up fix) works for a second, differently-shaped
  business too, not just Tolemate.
- **Minor finding, not a bug**: the model described the viewing request as
  "pending human review" even though `create_viewing_request` is
  `SAFE_WRITE` and executed immediately (unlike `cancel_booking`, which
  really does pend approval). The fact reported (a viewing request was
  created, with the real id) was accurate — only the process narration was
  imprecise. Noted here rather than silently ignored; not something to
  architect around, since it's natural-language flavor text, not a false
  claim about what happened or a security-relevant error.

## Phase 8 — Paradise Nepal ✅ DONE (mock connector) — spec correction included
**The master spec described Paradise Nepal as a film-production business.
Before building anything, the real site
(https://paradisenepal.kitetool.com/) was checked** — its client JS bundle
(a React/Vite SPA with no public API docs) references `hotel`, `hotels`,
`rooms`, `checkin`/`checkout`, `guests`, `bookings`, `rates`, `packages`,
and amenities (`breakfast`, `pool`, `wifi`). **It is a hotel booking
platform, not a production company.** Built accordingly — this is the
right call per the spec's own rule ("do not invent business rules" cuts
both ways: don't invent a wrong business either, when the real one is a
quick check away).

- `ParadiseNepalModule` (`app/connectors/paradise_nepal/`): mock
  `ParadiseNepalConnector` (fictional hotel/room data, shaped consistently
  with what the real site's own code suggests), 4 tools
  (`search_hotels`, `get_hotel_details`, `check_room_availability`,
  `create_hotel_booking`), and `HotelBookingAgent` — third instance of the
  same composition pattern as Tolemate/Ghar Nepal.
- Registered with the same one-line pattern — zero other core files
  touched, confirmed by the full pre-existing 91-test suite passing
  unchanged before any Paradise Nepal test was written.
- 12 new tests (91 → 103 total).
- Live-verified against real Qwen2.5 3B across a 2-turn conversation:
  turn 1 searched hotels in Pokhara; turn 2 ("book the deluxe room there..."),
  using the `conversation_id` from turn 1, correctly chained 4 tool calls
  (re-search → get details → check availability → create booking) with
  zero hallucinated ids and an accurate final summary (correct booking id,
  dates, price) — the strongest run of the three business integrations so far.
- **Recurring minor pattern, now seen twice (Ghar Nepal and Paradise
  Nepal)**: the model adds an unprompted hedge ("subject to additional
  checks," "pending human review") to a `SAFE_WRITE` action that actually
  completed immediately with no approval gate. The underlying facts
  reported were accurate both times; only the phrasing overstates
  uncertainty. Worth a prompt tweak across all three business agents in a
  future pass (e.g. explicitly stating "if the tool confirms success, say
  it succeeded — don't add approval caveats unless the tool itself is
  SENSITIVE/CRITICAL"), not urgent enough to block Phase 9.

## Phase 9 — Communication ✅ DONE
- `NotificationChannelProvider` abstraction (spec Section 22) +
  `NotificationService` — the one place application code sends a
  notification from. `GET /api/v1/notifications`,
  `POST /api/v1/notifications/{id}/read`.
- `WEB` channel is genuinely functional (the DB row IS the delivery — no
  external system to mock). `EMAIL`/`SMS`/`WHATSAPP` are clearly-labeled
  dev stubs (log what would be sent, report success) — no SMTP/Twilio/
  WhatsApp Business API credentials exist or were invented, same "mock
  now, swap later" rule as the business connectors.
- **Wired into something real, not left as unused scaffolding**: creating
  an approval (a `SENSITIVE`/`CRITICAL` tool call pausing for review) now
  notifies the requester; approving or rejecting it notifies them again
  with the outcome. The requester is looked up from the originating
  `AgentRun`, not assumed to be whoever decides it — correct for the case
  where a manager approves on behalf of someone else's agent session.
- 11 new tests (103 → 114 total): channel unit tests, service-level
  persistence/filtering/tenant-isolation, and the real approval→notify→
  resolve→notify integration through the API.
- Live-verified against real Qwen2.5 3B: triggered `cancel_booking`,
  confirmed exactly one "pending approval" notification appeared, approved
  it, confirmed a second "approved and completed" notification appeared
  with the actual tool result in its message — not a canned string.

### New model-reliability finding during live verification (documented, not a system bug)
On the first live attempt, Qwen2.5 3B didn't use Ollama's structured
tool-calling response field at all — it printed a literal, malformed
`<tool_call>{"name": "cancel_booking", ...}</tool_call>` text block as its
answer instead. Since `result.tool_calls` was genuinely empty, the
orchestrator correctly treated this as a final text answer (not a bug — it
can only act on what the API actually returns) and, correctly, no
notification was created, since no tool call actually happened. A
rephrased, slightly more explicit prompt on retry triggered proper
structured tool-calling and the full flow worked. This is a known
limitation of small (3B-class) models via Ollama's tool-calling interface,
not something this platform can fully engineer around — logged here as a
reliability characteristic to keep in mind, same spirit as the earlier
hallucinated-id and hedging-language findings.

## Phase 10 — Proactive Automation ✅ DONE (monitoring/escalation slice)
- `SchedulerEngine` (`app/scheduler/engine.py`): a plain asyncio loop, no
  external scheduling library (per "don't introduce a complex framework
  unless required") — started/stopped from `app/main.py`'s lifespan,
  configurable via `SCHEDULER_ENABLED`/`SCHEDULER_INTERVAL_SECONDS`.
- 3 generic, business-agnostic `ScheduledTask`s (spec Section 21's
  morning-check examples, generalized): `FailedAgentRunFollowUpTask`
  (notify a user once when their agent run fails or exhausts iterations),
  `StalePendingApprovalReminderTask` (remind the requester once an
  approval has sat PENDING too long), `StaleRequestEscalationTask`
  (auto-escalate a `Request` with no update for too long, via the same
  `RequestEngine` state machine every request already uses). Each tracks
  its own "already handled" flag so re-running the loop never duplicates
  a notification.
- `POST /api/v1/scheduler/run` — manually trigger all tasks once
  immediately (platform-admin only), for ops and for verification without
  waiting out the real interval.
- 10 new tests (114 → 124 total): each task unit-tested directly (fires
  once, never re-fires, respects terminal/fresh state), plus the API
  endpoint's RBAC check.
- Live-verified against the real running server (not just tests): the
  scheduler actually started on boot (confirmed in logs), a real approval
  was created via the live Qwen2.5 3B agent, backdated past the reminder
  threshold, and the manual trigger endpoint correctly sent exactly one
  "still pending" reminder — then a second trigger correctly sent zero
  more, proving the idempotency guarantee holds for real, not just in a
  mocked test.

### Deliberately NOT built (documented scope boundary, not an oversight)
The spec's full Section 21 diagram is `Scheduler -> Trigger -> Agent ->
Workflow -> Tool -> Verification -> Notification` — i.e., a timer that
actually *invokes the agent orchestrator* to take proactive action (e.g.
"every morning, have an agent re-check all pending Tolemate bookings").
Phase 10 builds the monitoring/escalation half (detect + notify) using
direct, lightweight queries — not the agent-invocation half, which is a
larger, inherently business-specific feature (what should an agent proactively
check, and for which business?) better built once a real scheduled
business workflow is needed, rather than speculatively now.

## Phase 11 — SaaS ✅ DONE (architecture + enforcement; no real payment processor)
- `Plan` + `TenantSubscription` models. 3 seeded tiers (free/starter/pro) —
  this platform's own commercial model (ours to define), not a fact about
  any external business. Idempotently seeded on startup
  (`seed_default_plans`), and defensively re-seeded on first use by the
  test client, which never runs `app.main`'s lifespan.
- Usage is computed by counting existing `AgentRun` rows in the current
  calendar month — not a separately-incremented counter, so there's
  nothing to desync from reality.
- **Actually enforced, not just modeled**: `POST /api/v1/agents/run`
  checks usage before running and returns **402 Payment Required** once a
  tenant's plan limit is hit — the free tier's default limit (1000/month)
  is generous enough that no existing test or real dev usage hits it by
  accident; a dedicated test proves the 402 fires using a test-only
  low-limit plan instead of making 1000 real calls.
- `GET/POST /api/v1/billing/subscription`, `GET /api/v1/billing/plans` —
  plan switching is self-service "selection," not a real charge (no
  Stripe/payment credentials exist or are invented).
- `GET /api/v1/admin/tenants` (platform-admin only): the one intentionally
  cross-tenant endpoint in the whole API — multi-tenant administration,
  gated by role instead of `tenant_id`.
- 14 new tests (124 → 138 total) — includes two real bugs the tests
  caught and fixed before commit, not after (see below).

### Two bugs the test suite caught before commit (not after)
1. `get_plan_by_slug` didn't defensively seed the catalog like `list_plans`
   did — a test hitting `POST /billing/subscription` as its very first
   billing call got a spurious 404 on a fresh DB. Fixed by moving the
   defensive seed into `get_plan_by_slug` itself.
2. The first fix used "is the `Plan` table empty?" as the seed trigger —
   broke the moment a *different* test inserted its own one-off test plan
   first, since the table was no longer empty but still missing the real
   catalog. Fixed by always calling the already-idempotent
   `seed_default_plans()` unconditionally rather than gating it behind a
   fragile emptiness check. Both are logged here because the live
   verification afterward (real server, real plan catalog, real usage
   counting, real plan switch, real admin listing) only works because
   these were caught first.

### Deliberately NOT built (documented scope boundary)
Real payment processing (Stripe or similar), white-labeling, and custom
per-tenant workflows are out of scope — all require either real
credentials this environment doesn't have, or a concrete customer need
that doesn't exist yet. The architecture (Plan/TenantSubscription,
enforcement hook point) is built so adding real billing later is "swap the
plan-switch endpoint's internals for a payment step," not a redesign.

## Phase 12 — Agent Marketplace ✅ DONE — completes the original roadmap
- Catalog is derived live from `app.agents.registry.list_agents()` — the
  same registry every other part of the platform already reads from — so
  there's one source of truth for "what agents exist," not a second,
  separately-maintained marketplace table that could drift out of sync.
  Every agent gained `version`/`category` class attributes
  (`app/agents/base_agent.py`).
- `AgentInstallation` model: per-tenant install state, soft-disabled on
  uninstall (not deleted) for auditability.
- `GET /api/v1/marketplace/agents` (browse, with `installed` flags),
  `GET /api/v1/marketplace/installed`,
  `POST /api/v1/marketplace/agents/{slug}/install|uninstall`.
- **Actually enforced**: `GET /api/v1/agents` only lists installed agents;
  `POST /api/v1/agents/run` 404s for an uninstalled one. Proven with a
  genuine uninstall → blocked → reinstall → restored cycle, not just a
  schema that stores an `is_enabled` flag nobody checks.
- **Backward compatibility preserved deliberately**: every tenant gets the
  full current catalog pre-installed at bootstrap
  (`ensure_default_agents_installed`), so none of the 138 pre-existing
  tests from Phases 1-11 needed to change. The installed-agents check only
  ever auto-populates a tenant that has *zero* installation rows — once a
  tenant has made any install/uninstall choice, that choice sticks and is
  never silently overwritten on the next request.
- 9 new tests (138 → 147 total), including the uninstall-blocks-it /
  reinstall-restores-it enforcement proof and tenant isolation of
  installation state.
- Live-verified against the real running server and real Qwen2.5 3B:
  browsed the catalog (all 4 agents, pre-installed), ran the Tolemate
  agent successfully, uninstalled it, confirmed the next run attempt
  404'd, reinstalled it, confirmed it worked again — the full lifecycle,
  for real, not simulated.

### This completes every phase in the master spec's original roadmap (Phase 0 → Phase 12).
Everything from environment discovery through the agent marketplace is
built, tested, and live-verified against the real local Ollama/Qwen2.5
stack. See `CHANGELOG.md` for the phase-by-phase history, including every
bug a test caught before commit and every honestly-reported model
reliability finding along the way — nothing in this roadmap was declared
done without a passing test suite and a real, live check against the
actual running system.

---

## Native local setup vs. Docker (Windows dev machine)

Per `ENVIRONMENT_REPORT.md`, this machine currently has very little free RAM
and no WSL2/Hyper-V active. The recommended Phase 1–4 local setup is:

| Service | Local dev (this machine) | Why |
|---|---|---|
| Database | SQLite file (default) now; native PostgreSQL+pgvector once installed with admin rights | No WSL2/Docker VM overhead; native Postgres install needs an elevated shell this environment doesn't have — **run `choco install postgresql16 -y` yourself in an elevated PowerShell when ready for Phase 4** |
| Redis | Skipped (app degrades gracefully) or native via Memurai Developer (`choco install memurai-developer -y`, elevated) | Redis has no first-class Windows build; Memurai is Redis-API compatible and lightweight |
| Ollama | Native Windows app (already installed) | Already the right choice; no change |
| Backend/Frontend | Run directly with `uvicorn`/`npm run dev` | No containerization overhead needed for a single dev |

Docker Compose remains fully defined in `docker-compose.yml` for: CI, a
teammate's machine with more RAM, or the eventual Linux production server.

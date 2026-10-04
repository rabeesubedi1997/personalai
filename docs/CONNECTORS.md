# Business Connectors

No connectors exist yet. Planned structure (Phase 6+):
```
backend/app/connectors/
├── ghar_nepal/
├── tolemate/
├── paradise_nepal/
└── common/
```

Existing applications (gharnepal.kitetool.com, tolemate.kitetool.com,
paradisenepal.kitetool.com) stay independent — connectors call their
controlled APIs rather than merging databases or rewriting them. Where real
API docs/access aren't available, mock connectors are built first and swapped
for real ones later. No real endpoints, schemas, or business rules are
invented ahead of that access — see the master spec's explicit instruction
on this.

Tolemate is the designated first real integration (Phase 6).

## Why this is already safe to build later, without touching the core

As of Phase 5, the entire core (Request engine, Agent orchestrator, Tool
registry, Approval engine, Memory, Audit log) has been exercised against
**three different simulated businesses** — Tolemate-style service bookings,
Ghar Nepal-style property enquiries, and Paradise Nepal-style production
enquiries — using nothing but the generic APIs already built, with zero
per-business branching anywhere in the core code. This is proven by
`backend/tests/test_multi_business_generality.py`, not just asserted here:

- **Requests**: all three use `POST /api/v1/requests` with a different
  `request_type` string and arbitrary `requirements` JSON — no schema
  change, no new table, no new endpoint per business
  (`test_three_different_businesses_use_the_same_generic_request_engine`).
- **Lifecycle**: all three go through the exact same
  RECEIVED→...→COMPLETED state machine
  (`test_same_generic_lifecycle_applies_to_every_business_type`).
- **Booking management**: the same `cancel_booking` tool + approval flow
  cancels both a `TOLEMATE-BOOKING-...` and a `GHARNEPAL-VIEWING-...` with
  identical code
  (`test_booking_cancellation_approval_flow_is_business_agnostic`).

### Recipe for adding a real business later (Phase 6+)
When Tolemate (or Ghar Nepal, or Paradise Nepal) access is actually
available, adding it means:
1. **Connector** (`app/connectors/<business>/`): functions wrapping that
   business's real API (`search_providers()`, `create_booking()`, ...) —
   never invented endpoints or credentials in code.
2. **Tools** (`app/tools/<business>_tools.py`): thin `Tool` subclasses that
   call the connector, each with its own `permission_level` — booking
   creation might be `SAFE_WRITE`, a price change `SENSITIVE`, using the
   exact same `ToolContext`/`ToolRegistry`/approval machinery that already
   exists.
3. **Agent** (`app/agents/<business>_agent.py`): a `BaseAgent` with an
   explicit `allowed_tools` list drawn from step 2 — same pattern as
   `GeneralAssistantAgent`.
4. **Request type**: just start using a new `request_type` string
   (e.g. `"tolemate_service_booking"`) — no migration needed.

None of these four steps touch `app/services/request_engine.py`,
`app/orchestrator/engine.py`, `app/tools/registry.py`, or
`app/models/{request,approval,audit_log}.py`. That's the core guarantee
this phase was built to prove, not just claim.

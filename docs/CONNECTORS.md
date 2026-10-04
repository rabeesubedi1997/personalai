# Business Connectors

## Implemented (Phase 6): Tolemate (mock)
```
backend/app/connectors/
├── base.py              # BusinessModule plugin interface
├── registry.py           # register_business_module() + the lists tool/agent registries read from
└── tolemate/
    ├── connector.py       # TolemateConnector — mock data, real method signatures
    ├── mock_data.py       # clearly-labeled fictional providers
    ├── tools.py           # search_service_providers, check_provider_availability, create_service_booking
    ├── agent.py           # ServiceBookingAgent
    └── module.py          # TolemateModule(BusinessModule) — wires the above together
```
No real Tolemate API access has been confirmed, so `TolemateConnector`
returns fixed mock data in the same shape a real integration would —
nothing invented about real endpoints, credentials, or business rules.
Swapping in the real API later means rewriting only `connector.py`'s
method bodies; `tools.py`, `agent.py`, and the entire core stay unchanged.

Ghar Nepal and Paradise Nepal are not built yet (Phase 7/8) — existing
applications (gharnepal.kitetool.com, tolemate.kitetool.com,
paradisenepal.kitetool.com) stay independent either way; connectors call
their controlled APIs rather than merging databases or rewriting them.

## The plugin mechanism (how "add a business" actually works)

A business is a `BusinessModule` (`app/connectors/base.py`): its tools +
its agent(s), nothing more. Registering one is a single function call —
`register_business_module(YourModule())` — and from that point on,
`app/tools/registry.py` and `app/agents/registry.py` automatically include
its tools/agents everywhere (the `/api/v1/tools`, `/api/v1/agents`, and
`/api/v1/agents/run` endpoints need no changes at all).

This is proven, not just described:
`backend/tests/test_business_module_extensibility.py` defines an entirely
new, fictional business (a Paradise Nepal-style film-crew lookup) **inside
the test file itself** — zero edits to any core file — registers it with
one call, and shows it immediately appears in the tool/agent listings and
runs a full agent turn correctly. That test is the actual guarantee behind
"you can add multiple businesses later," re-checked on every test run, not
a claim that can silently go stale.

### Recipe for adding a real business (e.g. when Ghar Nepal/Paradise Nepal access exists)
1. **Connector** (`app/connectors/<business>/connector.py`): functions
   wrapping that business's real API — never invented endpoints or
   credentials in code. Start from mock data if real access isn't ready
   yet, exactly like `TolemateConnector`.
2. **Tools** (`app/connectors/<business>/tools.py`): thin `Tool` subclasses
   calling the connector, each with its own `permission_level` — the
   registry structurally refuses a `SENSITIVE`/`CRITICAL` tool that
   doesn't require approval (Phase 5), so this can't be gotten wrong
   silently.
3. **Agent** (`app/connectors/<business>/agent.py`): a `BaseAgent` with an
   explicit `allowed_tools` list — mix business-specific tools with core
   ones (`cancel_booking`, `search_knowledge_base`, `create_task`) as
   `ServiceBookingAgent` does.
4. **Module** (`app/connectors/<business>/module.py`): a `BusinessModule`
   bundling 2+3.
5. **One line** in `app/connectors/__init__.py`:
   `register_business_module(<Business>Module())`.
6. **Request type**: start using a new `request_type` string with the
   existing generic `POST /api/v1/requests` — no migration needed.

None of steps 1–6 touch `app/services/request_engine.py`,
`app/orchestrator/engine.py`, `app/tools/registry.py`,
`app/agents/registry.py`, or any model in `app/models/`. That is the core
guarantee this phase was built to prove, and both
`test_multi_business_generality.py` (Phase 5) and
`test_business_module_extensibility.py` (Phase 6) check it mechanically.

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

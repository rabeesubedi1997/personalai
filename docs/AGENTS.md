# Agents

## Implemented (Phase 2)
`BaseAgent` (`backend/app/agents/base_agent.py`) declares `name`,
`description`, `system_prompt`, and an explicit `allowed_tools` list —
agents never get unrestricted tool access.

**General Assistant Agent** (`general_assistant.py`) is the one demonstration
agent: receives a message, the orchestrator lets it select from its 3
allowed tools (`get_current_time`, `search_knowledge_base`, `create_task`),
executes, returns a result. Registered in `agents/registry.py`; run via
`POST /api/v1/agents/run`. As of the Phase 4 follow-up, `search_knowledge_base`
is a real `MemoryStore`-backed tool, not a mock (see `docs/TOOLS.md`) — this
agent now does genuine semantic knowledge retrieval, scoped to whatever has
actually been added via `POST /api/v1/memory` for the caller's tenant.

Every run is bounded by `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` /
per-tool `timeout_seconds` (`app/core/config.py` + `app/tools/base.py`) —
verified by tests that force a provider to request tool calls forever and
confirm the orchestrator stops rather than looping (`tests/test_orchestrator.py`).

### Verified finding: tool-use must be explicitly mandated in the prompt
Live-tested against Qwen2.5 3B: with a softer system prompt
("use tools when needed"), the model answered a factual question
("What are your support hours?") **from invented memory** instead of
calling `search_knowledge_base` — a direct violation of spec Section 47/48
("never invent business data"). Rewriting the prompt to explicitly mandate
tool calls for business-fact questions (see `general_assistant.py`) fixed
this; re-verified live that the model now calls the tool and, for a query
with no matching document, honestly reports the information is unavailable
rather than fabricating an answer. This is recorded as a standing
constraint on every future agent's system prompt, not a one-off prompt
tweak: **small local models need explicit, mandatory tool-use instructions
per fact category — "use tools when appropriate" is not reliable enough.**

## Implemented (Phase 6): ServiceBookingAgent (Tolemate)
`app/connectors/tolemate/agent.py` — the first real business agent,
registered via the `BusinessModule` plugin system (see `docs/CONNECTORS.md`),
not hand-wired into `agents/registry.py`. Composes business-specific tools
(`search_service_providers`, `check_provider_availability`,
`create_service_booking`) with core platform tools (`cancel_booking`,
`search_knowledge_base`, `create_task`).

Live-verified finding (see `docs/DEVELOPMENT_ROADMAP.md` Phase 6 for the
full account): Qwen2.5 3B can misread a tool's own result text and
hallucinate an id (e.g. `"P1"` instead of the real `"PRV-001"`) mid-run —
it self-corrected via the normal error→retry path and never claimed
success before the tool actually confirmed it, but this is a reminder that
small local models need real end-to-end testing per agent, not just unit
tests against a fake provider.

## Implemented (Phase 7): PropertyAgent (Ghar Nepal)
`app/connectors/ghar_nepal/agent.py` — second real business agent, proving
the composition pattern generalizes to a genuinely different domain (real
estate vs. Tolemate's service bookings). Composes `search_properties`,
`get_property_details`, `create_property_enquiry`,
`create_viewing_request` with the same core tools as
`ServiceBookingAgent`.

Live-verified finding (minor, not a bug — see
`docs/DEVELOPMENT_ROADMAP.md` Phase 7): the model narrated a successful,
immediate `SAFE_WRITE` viewing-request creation as "pending human review,"
language that only actually applies to the `SENSITIVE` `cancel_booking`
tool. The fact reported (a real viewing was created, with its real id) was
accurate; only the process description was imprecise. Worth tightening
`PropertyAgent`'s system prompt if it recurs, not worth a structural fix.

## Planned (Phase 8+)
```
backend/app/connectors/
├── tolemate/agent.py              ✅ ServiceBookingAgent (Phase 6)
├── ghar_nepal/agent.py            ✅ PropertyAgent (Phase 7)
├── paradise_nepal/agent.py        Phase 8
└── ...
```
Each new business agent follows the same recipe:
`docs/CONNECTORS.md` → "Recipe for adding a real business."
Permissions, escalation rules, and required-data declarations beyond
`allowed_tools` are added as each real business agent needs them — not
built speculatively ahead of that need.

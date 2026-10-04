# Agents

No agents are implemented yet — Phase 1 only verifies the AI provider layer
they will eventually run on (see `backend/app/services/ai/`).

## Planned (Phase 2+)
Every agent will define: identity, responsibilities, allowed tools,
permissions, workflow, required data, escalation rules, success conditions —
per the master spec. Agents never get unrestricted tool access; each
agent's allowed-tool list is explicit.

Planned structure:
```
backend/app/agents/
├── base_agent.py
├── customer_support_agent.py
├── sales_agent.py
├── property_agent.py
├── service_booking_agent.py
└── ...
```

First agent to be built (Phase 2): **General Assistant Agent** — receives a
request, selects from a small set of mock tools, executes, returns a result.
Bounded by `AGENT_MAX_ITERATIONS` / `AGENT_MAX_TOOL_CALLS` /
`AGENT_TOOL_TIMEOUT_SECONDS` (already present in `app/core/config.py`) so no
agent loop can run unbounded.

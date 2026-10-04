# Tools

## Implemented (Phase 2)
`Tool` base class (`backend/app/tools/base.py`): `name`, `description`,
JSON-schema `parameters`, `permission_level`, `requires_approval`,
`timeout_seconds`, async `execute()`.

`ToolRegistry` (`tools/registry.py`) is the only place a tool name resolves
to executable code:
- `specs_for(allowed_tool_names)` — hands the model only the tool specs an
  agent is allowed to use, never the full registry.
- `execute(name, arguments, allowed_tool_names=...)` — **hard-refuses**
  (raises `ToolExecutionError`, does not execute) a tool that either
  doesn't exist or isn't in the calling agent's own allow-list, and enforces
  each tool's `timeout_seconds` via `asyncio.wait_for`. Covered by
  `tests/test_tool_registry.py` and `tests/test_orchestrator.py`
  (`test_unauthorized_tool_call_is_denied_not_executed`).

Permission levels (spec Section 11) are modeled now as `PermissionLevel`
(`READ` / `SAFE_WRITE` / `SENSITIVE` / `CRITICAL`); **enforcement beyond
the agent allow-list** (e.g. requiring human approval before a `CRITICAL`
tool runs) is Phase 5.

## Tools (as of Phase 4 follow-up)
- `get_current_time` (READ) — mock, `tools/mock_tools.py`
- `create_task` (SAFE_WRITE) — mock, `tools/mock_tools.py`
- `search_knowledge_base` (READ) — **real**, `tools/memory_tools.py`.
  Graduated from a Phase 2 hardcoded-dict mock to a genuine
  `MemoryStore`-backed implementation: embeds the query, does cosine
  similarity search over the tenant's `knowledge`-type memory records, and
  returns the best match only above `MATCH_THRESHOLD` (0.55, tuned against
  `nomic-embed-text` — see CHANGELOG for the live verification). Below
  that, it honestly reports no match rather than returning an
  unrelated document. Live-verified distinguishing between two unrelated
  knowledge entries (support hours vs. refund policy) and correctly
  reporting "no match" for a genuinely unanswerable question.

Tool execution now receives a `ToolContext` (`tenant_id`, `db` session,
`ai_provider`) — see `app/tools/base.py` — so a tool can do real,
tenant-scoped work instead of only seeing its LLM-supplied arguments.

`get_current_time` and `create_task` remain explicit mocks (spec: "Use mock
tools initially") — swapped for real implementations starting Phase 6 when
a real connector exists to back them.

## `cancel_booking` (SENSITIVE, Phase 5) — the business-agnostic booking tool
`cancel_booking` (`tools/mock_tools.py`) exists specifically to prove
booking management is a **core platform capability**, not something
rebuilt per business: `{booking_id, reason?}` is all it needs, and nothing
in its code, the orchestrator, or the approval engine knows or cares
whether `booking_id` refers to a Tolemate service booking, a Ghar Nepal
viewing appointment, or a Paradise Nepal production slot. When a real
connector exists (Phase 6+), only the mock body swaps for a real API call
— the tool contract, its `SENSITIVE` permission level, and the mandatory
approval gate all stay exactly as they are.

Concrete proof, not just a claim:
`tests/test_multi_business_generality.py::test_booking_cancellation_approval_flow_is_business_agnostic`
runs this exact tool through the full approval flow for both a
`TOLEMATE-BOOKING-...` id and a `GHARNEPAL-VIEWING-...` id, with zero
code differences between the two.

## Permission level enforcement (Phase 5, structural not conventional)
`ToolRegistry.register()` raises `ValueError` if a tool declares
`permission_level: SENSITIVE` or `CRITICAL` without `requires_approval =
True` — a future tool author cannot ship a sensitive tool that skips human
approval by forgetting a flag; the registry refuses to even register it.

The LLM never gets unrestricted SQL, shell, filesystem, or direct
production database access — only named, schema-validated tools, resolved
through the registry above.

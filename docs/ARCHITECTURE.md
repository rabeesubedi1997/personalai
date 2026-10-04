# Architecture

## Vision
PersonalOps AI is an AI Workforce / Operations Agent Platform, not a chatbot.
The long-term shape (unchanged from the master spec):

```
                    PERSONALOPS AI
                         |
              AI ORCHESTRATOR
                         |
        +----------------+----------------+
        |                |                |
   SPECIALIST       WORKFLOW          TOOL
     AGENTS           ENGINE          REGISTRY
        |                |                |
        +----------------+----------------+
                         |
              UNIVERSAL REQUEST ENGINE
                         |
        +----------------+----------------+
        |                |                |
      MEMORY         APPROVALS       NOTIFICATIONS
        |
   BUSINESS CONNECTORS (Ghar Nepal, Tolemate, Paradise Nepal, future...)
```

Phase 1 (current) builds only the foundation this sits on: API, auth,
database, config, logging, and health checks — plus, as a forward-looking
smoke test, the `AIProvider` abstraction wired to a live local model. Agents,
tools, workflows, memory, approvals and connectors are **not** implemented
yet — they begin in Phases 2–8 of [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md).

## Repository layout
```
personalops-ai/
├── backend/
│   ├── app/
│   │   ├── api/v1/        # FastAPI routers (health, auth, ai smoke-test)
│   │   ├── core/          # config, logging, redis client
│   │   ├── db/             # SQLAlchemy base + async session
│   │   ├── models/         # ORM models (Tenant, User, Role)
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── security/       # password hashing, JWT, auth dependency
│   │   ├── services/ai/    # AIProvider abstraction + OllamaProvider
│   │   ├── agents/         # (Phase 2+)
│   │   ├── tools/          # (Phase 2+)
│   │   ├── workflows/      # (Phase 3+)
│   │   ├── memory/         # (Phase 4+)
│   │   ├── connectors/     # (Phase 6+)
│   │   └── main.py
│   ├── alembic/            # DB migrations
│   └── tests/
├── frontend/                # Next.js admin dashboard
├── infrastructure/docker/   # (reserved for future compose overrides)
├── docs/
├── scripts/
├── docker-compose.yml
└── .env.example
```

## AI provider abstraction
The app never calls Ollama/Claude/OpenAI directly — only `AIProvider`
(`backend/app/services/ai/base.py`):

```
AIProvider (ABC)
├── generate(prompt, system=None) -> GenerationResult
├── chat(messages) -> GenerationResult
├── generate_with_tools(messages, tools) -> GenerationResult
└── health_check() -> bool

OllamaProvider   — implemented, default (AI_PROVIDER=ollama)
ClaudeProvider   — stubbed in factory.py, raises NotImplementedError until built
OpenAIProvider   — stubbed in factory.py, raises NotImplementedError until built
```

`get_ai_provider()` in `factory.py` is the single switch point driven by the
`AI_PROVIDER` env var. This was verified end-to-end in Phase 1 against a
running Ollama instance with `qwen2.5:3b-instruct`, including structured
tool-calling (see CHANGELOG.md for the verification transcript).

## Key architecture decisions (Phase 1)

| Decision | Reason | Alternative | Why chosen |
|---|---|---|---|
| SQLite as the Phase-1 default `DATABASE_URL`, Postgres fully supported by the same async SQLAlchemy code | Zero-install bring-up on a dev machine where native Postgres install needs admin elevation this environment doesn't have | Require Postgres from day one | Switching is one env var; no code forked between the two |
| Redis optional, app degrades gracefully if absent | Phase 1 priority is core API + AI; Redis-backed caching/rate-limiting isn't load-bearing yet | Hard-require Redis | Matches spec's "avoid unnecessary services" resource rule |
| Native process model documented as the primary local dev path, Docker Compose kept for parity | ~1.7GB free RAM measured in ENVIRONMENT_REPORT.md; Docker Desktop's WSL2 VM has real overhead | Docker-only dev setup | Spec Section 34 explicitly allows/encourages this trade-off |
| `qwen2.5:3b-instruct` as default Ollama model | Verified reliable native tool-calling + structured JSON output, runs acceptably (~8s/response) on this CPU | Keep pre-existing `deepseek-r1:1.5b` | R1-distill models are reasoning/CoT-tuned with unreliable tool-calling in Ollama |
| Tenant/User/Role modeled now, full permission engine deferred | Spec Section 24/9 needs tenant scoping everywhere from day one, but fine-grained tool/agent permissions are a Phase 5 concern | Build full RBAC now | Avoid over-engineering ahead of the agent/tool system that permissions actually gate |

## Security posture (Phase 1 scope)
- Passwords hashed with bcrypt (via passlib), never stored/logged in plaintext.
- JWT secret only read from env (`JWT_SECRET`), never hard-coded, never logged.
- `/api/v1/auth/bootstrap` (dev convenience, creates the first tenant+admin)
  is hard-disabled when `APP_ENV=production`.
- CORS restricted to the local frontend origin.
- Full security architecture (tool permission levels, approvals, audit
  logging, prompt-injection defenses) is Phase 5 — see
  [docs/SECURITY.md](SECURITY.md) for what's planned vs. implemented today.

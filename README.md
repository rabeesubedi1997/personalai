# PersonalOps AI

A low-resource, local-first AI Operations Agent Platform, designed to grow into
a multi-tenant commercial AI Workforce SaaS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the full vision and [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
for the phase-by-phase build plan.

**Current status: all 13 phases of the original roadmap complete** (Phase 0
environment discovery through Phase 12 Agent Marketplace), plus a full
dashboard UI — see [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
for the phase-by-phase history. 150 backend tests passing; every capability
live-verified against a real running Ollama + Qwen2.5 3B stack, not mocked.

## Why local-first

This runs with **$0 AI API cost** using [Ollama](https://ollama.com) + a small
Qwen2.5 model, entirely on a CPU-only, 16GB-RAM Windows machine. See
[ENVIRONMENT_REPORT.md](ENVIRONMENT_REPORT.md) for the hardware/software
discovery this was built against, and the reasoning behind every resource
decision (native services over Docker, model size, etc).

## Quick start (native Windows dev setup)

### Prerequisites already verified on this machine
- Python 3.11, Git, Node.js 24 / npm 9, Ollama — see ENVIRONMENT_REPORT.md.

### 1. Pull the models and start Ollama
```powershell
ollama serve          # if not already running
ollama pull qwen2.5:3b-instruct
ollama pull nomic-embed-text   # for the Phase 4 memory/embedding system
```

### 2. Backend
```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example ..\.env        # from repo root, or create backend/.env
uvicorn app.main:app --reload --port 8000
```
Defaults to a local SQLite file (`personalops.db`) — zero extra installs.
To use PostgreSQL instead, just change `DATABASE_URL` in `.env` (see below).

Check it's alive:
```
GET http://localhost:8000/api/v1/health
```

### 3. Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:3000 — sign up ("Create account"), and you land on a
full dashboard: Agents (chat with any installed agent, see its tool calls
live), Marketplace (browse/install/uninstall), Approvals (approve/reject
sensitive actions), Billing (plan + usage), Notifications, and (for the
platform-admin role every signup gets) a cross-tenant Admin view.

### 4. Or explore the API directly via Swagger
```
http://localhost:8000/docs
```
Every endpoint is there, interactive, with a Bearer-token "Authorize"
button — useful for anything not yet wired into a dashboard screen.

### Switching to PostgreSQL
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/personalops
```
No code changes needed — only the env var. Run migrations with:
```powershell
cd backend
alembic upgrade head
```

### Running with Docker instead
`docker-compose.yml` at the repo root defines postgres/redis/ollama/backend/
frontend for Linux/production parity. **Not recommended on this specific dev
machine right now** (WSL2/Docker Desktop overhead vs. ~1.7GB free RAM) — see
ENVIRONMENT_REPORT.md. Fine to use once more RAM is free, or on a Linux
server/CI.

## Tests
```powershell
cd backend
.venv\Scripts\activate
pytest -q
```
150/150 passing. Tests use a deterministic fake AI provider so CI doesn't
depend on Ollama running; every phase was additionally live-verified
against the real Ollama + Qwen2.5 3B stack (see CHANGELOG.md for each
phase's live-verification notes, and the honestly-reported model-reliability
and real-bug findings along the way — nothing here was declared done on
passing tests alone).

The frontend has no automated test suite yet; it's been verified with a
scripted Playwright pass driving a real headless browser against the real
backend (not just a build check) — see CHANGELOG.md's "Dashboard UI" entry
for 3 real bugs that surfaced only under that kind of testing and were
fixed, not worked around.

## Repository layout
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation index
- [ENVIRONMENT_REPORT.md](ENVIRONMENT_REPORT.md) — Phase 0 hardware/software discovery
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)
- [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/AGENTS.md](docs/AGENTS.md)
- [docs/TOOLS.md](docs/TOOLS.md)
- [docs/CONNECTORS.md](docs/CONNECTORS.md)
- [CHANGELOG.md](CHANGELOG.md)

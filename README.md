# PersonalOps AI

A low-resource, local-first AI Operations Agent Platform, designed to grow into
a multi-tenant commercial AI Workforce SaaS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the full vision and [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md)
for the phase-by-phase build plan.

**Current status: Phase 1 — Platform Foundation.** FastAPI backend, Next.js
dashboard, JWT auth, tenant/user/role models, and a working provider-agnostic
AI layer talking to a local Ollama + Qwen2.5 model — all verified end to end.

## Why local-first

This runs with **$0 AI API cost** using [Ollama](https://ollama.com) + a small
Qwen2.5 model, entirely on a CPU-only, 16GB-RAM Windows machine. See
[ENVIRONMENT_REPORT.md](ENVIRONMENT_REPORT.md) for the hardware/software
discovery this was built against, and the reasoning behind every resource
decision (native services over Docker, model size, etc).

## Quick start (native Windows dev setup)

### Prerequisites already verified on this machine
- Python 3.11, Git, Node.js 24 / npm 9, Ollama — see ENVIRONMENT_REPORT.md.

### 1. Pull the model and start Ollama
```powershell
ollama serve          # if not already running
ollama pull qwen2.5:3b-instruct
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
Open http://localhost:3000 — it shows live backend health and a login form.

### 4. Create a dev user and try the AI smoke test
```powershell
curl -X POST http://localhost:8000/api/v1/auth/bootstrap `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@example.com","password":"DevPassw0rd!"}'

curl -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@example.com","password":"DevPassw0rd!"}'
# copy the access_token from the response, then:

curl -X POST http://localhost:8000/api/v1/ai/smoke-test `
  -H "Content-Type: application/json" -H "Authorization: Bearer <token>" `
  -d '{"prompt":"Say hello in one short sentence."}'
```

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
9/9 passing as of Phase 1 (health, auth, AI provider unit tests — the AI
provider tests use a mocked transport so CI doesn't depend on Ollama running;
the `/api/v1/ai/smoke-test` endpoint above is the live integration check).

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

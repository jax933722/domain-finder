# Local Setup Guide

How to run **Domain Finder** on your own computer — from zero to uploading a
file and downloading verified domains. Two paths:

- **[Option A — Docker](#option-a--docker-recommended)** (recommended): one
  command brings up the whole stack. Best for just *using* the app.
- **[Option B — Native](#option-b--native-without-docker)**: run each piece
  directly with Python + Node. Best for *developing* the code.

You do **not** need any paid API keys — search works out of the box via the
bundled SearXNG + Wikidata providers.

---

## Option A — Docker (recommended)

### 1. Install Docker

Install **Docker Desktop** (macOS/Windows) or Docker Engine + Compose (Linux):
https://docs.docker.com/get-docker/

Verify:

```bash
docker --version
docker compose version
```

### 2. Get the code

```bash
git clone <your-repo-url> domain-finder
cd domain-finder
```

### 3. Create your `.env`

```bash
cp .env.example .env
```

Open `.env` and set at least these:

```ini
# Generate a strong key:  openssl rand -hex 32
SECRET_KEY=paste_a_long_random_string_here

# The first admin account, created automatically on first startup:
FIRST_ADMIN_EMAIL=admin@example.com
FIRST_ADMIN_PASSWORD=ChangeMe123!
```

Everything else has sensible defaults. Leave the search API keys blank — the
app falls back to the keyless SearXNG + Wikidata providers.

### 4. Start everything

```bash
docker compose up --build
```

This launches: PostgreSQL, Redis, SearXNG (search), the FastAPI backend, the
Celery worker, the React frontend, and an Nginx reverse proxy. First build takes
a few minutes; subsequent starts are fast. Add `-d` to run in the background.

### 5. Open the app

| URL | What |
| --- | --- |
| http://localhost:8080 | The web application |
| http://localhost:8080/docs | Interactive API docs (Swagger) |
| http://localhost:8080/health/ready | Readiness check (DB + Redis) |

Log in with the `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` from your `.env`,
or click **Sign up** to create a regular account.

> **Only port 8080 is exposed.** The backend, database, Redis, and SearXNG are
> internal to the Docker network and reached through Nginx.

### 6. Try it

1. On the dashboard, drag in `sample_data/companies_sample.csv`.
2. Pick the **Company** column, click **Start Processing**.
3. Watch the live progress bar, logs, and results fill in.
4. Download the enriched **Excel** or **CSV**.

### Stopping / resetting

```bash
docker compose down            # stop (keeps data)
docker compose down -v         # stop and DELETE all data (fresh start)
docker compose logs -f backend # tail backend logs
docker compose logs -f worker  # tail the processing worker
```

---

## Option B — Native (without Docker)

Use this if you want to develop the code directly. You'll run four things:
Postgres, Redis, the backend (API + worker), and the frontend.

### Prerequisites

- **Python 3.11+**
- **Node.js 20+** and npm
- **PostgreSQL 14+** and **Redis 6+** (install natively, or run just those two
  in Docker — see below)

The quickest way to get Postgres + Redis is Docker (even if you run the app
natively):

```bash
docker run -d --name df-postgres -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=domainfinder \
  -p 5432:5432 postgres:16-alpine

docker run -d --name df-redis -p 6379:6379 redis:7-alpine
```

If you installed Postgres natively instead, create the database once:

```bash
createdb domainfinder
```

### 1. Backend — API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env` (the backend reads env vars from here):

```ini
SECRET_KEY=paste_a_long_random_string_here
POSTGRES_HOST=localhost
REDIS_HOST=localhost
FIRST_ADMIN_EMAIL=admin@example.com
FIRST_ADMIN_PASSWORD=ChangeMe123!
BACKEND_CORS_ORIGINS=http://localhost:5173
# Optional: point at a SearXNG instance for keyless web search (see note below).
# SEARXNG_URL=http://localhost:8888
```

Run the API (tables are created automatically on startup):

```bash
uvicorn app.main:app --reload
```

The API is now at http://localhost:8000 (docs at http://localhost:8000/docs).

### 2. Backend — worker

In a **second terminal**, from `backend/` with the venv activated:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

The worker does the actual domain discovery. The API enqueues jobs to it via
Redis. Both must be running to process files.

### 3. Frontend

In a **third terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend on
`:8000` automatically.

### Search providers in native mode

Without Docker's SearXNG service, keyless search falls back to **Wikidata only**
(good for well-known companies). To get full web search you can either:

- **Run SearXNG** and point the backend at it:

  ```bash
  docker run -d --name df-searxng -p 8888:8080 \
    -v "$(pwd)/searxng/settings.yml:/etc/searxng/settings.yml:ro" \
    searxng/searxng:latest
  # then set SEARXNG_URL=http://localhost:8888 in backend/.env and restart uvicorn
  ```

- **or** add a paid key in `backend/.env` (`BRAVE_SEARCH_API_KEY=...`).

---

## Optional add-ons

### Self-hosted LLM re-ranker (accuracy booster, no keys)

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull llama3.1
# set LLM_ENABLED=true in .env, then:
docker compose up -d backend worker
```

### Metrics (Prometheus)

```bash
docker compose --profile observability up -d prometheus
```

- Prometheus UI: http://localhost:9090
- API metrics: http://localhost:8080/metrics
- Worker metrics: `worker:9100` (scraped by Prometheus inside the network)

---

## Running the tests

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt   # if not already
pytest                            # 60+ tests, no database/Redis required
```

---

## Ports reference

| Port | Service | Docker | Native |
| --- | --- | --- | --- |
| 8080 | Web app (Nginx) | ✅ exposed | — |
| 5173 | Frontend dev server | — | ✅ |
| 8000 | Backend API | internal | ✅ |
| 5432 | PostgreSQL | internal | ✅ (if you publish it) |
| 6379 | Redis | internal | ✅ (if you publish it) |
| 8080/8888 | SearXNG | internal | optional |
| 9090 | Prometheus | opt-in profile | — |
| 11434 | Ollama | opt-in profile | — |

---

## Troubleshooting

**Port 8080 already in use** — change the Nginx mapping in `docker-compose.yml`
(`"8080:80"` → e.g. `"8090:80"`), then use `http://localhost:8090`.

**`/health/ready` returns 503** — Postgres or Redis isn't up yet. Wait a few
seconds on first boot, or check `docker compose logs db redis`.

**Login fails right after first start** — the admin user is created on backend
startup; give it a few seconds, and confirm `FIRST_ADMIN_EMAIL/PASSWORD` are set
in `.env`. You can always **Sign up** for a fresh account.

**Everything says NOT FOUND** — no search provider is answering. In Docker,
check `docker compose logs searxng`. In native mode, either run SearXNG (above)
or add a search API key. Wikidata-only mode legitimately returns NOT FOUND for
smaller/local companies.

**Uploads rejected** — only `.csv` and `.xlsx` are accepted, up to the row/size
limits in `.env` (`MAX_UPLOAD_ROWS`, `MAX_UPLOAD_BYTES`).

**Worker not processing (jobs stuck at Pending)** — the Celery worker isn't
running. In Docker it's the `worker` service (`docker compose logs worker`); in
native mode start it in its own terminal (Step 2).

**Reset all data** — `docker compose down -v` wipes the Postgres/Redis volumes
for a clean slate.

---

## Command cheat sheet

```bash
# Docker
docker compose up --build            # start everything (foreground)
docker compose up -d                 # start in background
docker compose ps                    # service status
docker compose logs -f backend worker
docker compose restart backend
docker compose down                  # stop
docker compose down -v               # stop + delete data

# Native
uvicorn app.main:app --reload                                   # API
celery -A app.workers.celery_app.celery_app worker --loglevel=info   # worker
npm run dev                                                     # frontend
pytest                                                          # tests
```

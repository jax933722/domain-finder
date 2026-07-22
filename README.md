# Domain Finder — Company Domain Enrichment

A production-ready SaaS web application that ingests a spreadsheet of company
names, **cleans** each name, discovers the **verified official domain** from
trusted internet sources, and exports the enriched file.

> **The core promise:** the application *never guesses* a domain. It never
> assumes `.com`, never fabricates, never infers. If no authoritative source
> confirms the official website, the result is **`NOT FOUND`**.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Search providers](#search-providers)
- [How domain discovery works](#how-domain-discovery-works)
- [API reference](#api-reference)
- [Database schema](#database-schema)
- [Testing](#testing)
- [Project structure](#project-structure)

---

## Features

- **Upload** `.xlsx` / `.csv` via drag-and-drop, choose the company column, preview data.
- **Intelligent cleaning** — strips job titles (`CEO at`, `Founder @`, ...) and legal
  suffixes (`Inc`, `Ltd`, `LLC`, `Pvt Ltd`, ...) while preserving the real brand.
- **Verified domain discovery** using reliable search APIs (Brave / Google CSE /
  Bing) and authoritative structured data (Wikidata *official website* property).
- **Confidence scoring** with a configurable threshold — low-confidence results
  become `NOT FOUND` with a human-readable reason.
- **Real-time progress**, live logs, and search statistics while processing.
- **Preview results while processing** and download the enriched **Excel** or **CSV**.
- **Redis caching + de-duplication** — each unique company is searched only once.
- **Scalable async processing** with Celery workers, retries, timeouts,
  exponential backoff, connection pooling — designed for 100,000+ rows.
- **JWT authentication** (signup / login / refresh / forgot-password), role-based
  access, and an **admin dashboard** (stats, top companies, cache, users, jobs).
- **Full search transparency** — every row records the cleaned name, query,
  source, domain, confidence, reason, and processing time.
- **Dark mode**, responsive design, clean shadcn-style UI.
- **Dockerized** with Postgres, Redis, backend, worker, frontend, and Nginx.

---

## Architecture

```
                    +-------------+
   Browser -------> |    Nginx    |  :8080  (reverse proxy + static SPA)
                    +------+------+
             /api/*        |        /
        +-----------------+--------------------+
        v                                      v
 +-------------+                       +---------------+
 |  FastAPI    |  enqueue jobs         |  React SPA    |
 |  (backend)  | -------------------->  |  (frontend)   |
 +------+------+                       +---------------+
        |  ^  progress/logs/cache
        |  |
   +----v--+----+        +--------------+        +-------------------+
   | PostgreSQL |        |    Redis     |<------>|  Celery worker(s) |
   | (durable)  |        | cache+broker |        |  async discovery  |
   +------------+        +--------------+        +---------+---------+
                                                           | HTTPS
                                             +-------------v--------------+
                                             | Brave / Google / Bing /    |
                                             | Wikidata search providers  |
                                             +----------------------------+
```

- The **API** handles auth, uploads, and job orchestration; it hands processing
  to **Celery** and never blocks on network searches.
- Each **worker task** runs its own asyncio loop and fans out bounded-concurrency
  lookups, streaming progress and logs to **Redis** for the UI to poll.
- **Postgres** is the durable record (users, uploads, jobs, per-row results,
  cached domains, search history, logs).

---

## Tech stack

**Frontend:** React + TypeScript, Vite, Tailwind CSS, shadcn-style components,
TanStack Table, TanStack Query (React Query), Axios, React Router, Lucide icons.

**Backend:** Python 3.11, FastAPI (async), SQLAlchemy 2.0 async + asyncpg,
PostgreSQL, Redis, Celery, httpx, tenacity, pandas + openpyxl, python-jose, passlib.

---

## Quick start (Docker)

Prerequisites: Docker + Docker Compose.

```bash
git clone <this-repo>
cd domain-finder
cp .env.example .env
# Edit .env: set SECRET_KEY, admin credentials, and at least one search API key.

docker compose up --build
```

Then open:

| URL | What |
| --- | --- |
| http://localhost:8080 | Web application |
| http://localhost:8080/docs | Interactive API docs (Swagger) |
| http://localhost:8080/redoc | API docs (ReDoc) |

Log in with the `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` you set in `.env`,
or sign up for a new (non-admin) account.

A sample file to try is at `sample_data/companies_sample.csv`.

> Even with **no** search API keys configured, the app works out of the box using
> the free **Wikidata** provider (lower coverage than the paid APIs).

---

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Requires a local Postgres + Redis (or use the docker-compose db/redis services).
export POSTGRES_HOST=localhost REDIS_HOST=localhost
uvicorn app.main:app --reload

# In a second terminal — the Celery worker:
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

---

## Configuration

All settings are environment variables — see `.env.example`. Highlights:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | — | JWT signing key (**set this**). |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | — | Bootstraps an admin on startup. |
| `DOMAIN_CACHE_TTL_SECONDS` | `2592000` (30d) | Redis domain-cache expiry (configurable). |
| `CONFIDENCE_THRESHOLD` | `0.6` | Minimum confidence to accept a domain, else `NOT FOUND`. |
| `JOB_CONCURRENCY` | `10` | Concurrent lookups per job. |
| `SEARCH_PROVIDER_ORDER` | `brave,google,bing,wikipedia` | Provider preference order. |
| `SEARCH_MAX_RETRIES` | `3` | Retries with exponential backoff. |
| `MAX_UPLOAD_ROWS` | `200000` | Upload row cap. |

---

## Search providers

Configure **at least one** for best coverage. The app scrapes **no** search
engine HTML — it uses official, reliable APIs, which are more stable and harder
to block.

| Provider | Env vars | Notes |
| --- | --- | --- |
| **Brave Search** (preferred) | `BRAVE_SEARCH_API_KEY` | Fast, generous free tier. |
| **Google Custom Search** | `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ENGINE_ID` | High quality. |
| **Bing Web Search** | `BING_SEARCH_API_KEY` | Broad coverage. |
| **Wikidata / Wikipedia** | *(none)* | Authoritative `official website` (P856); always available. |

Providers without configured credentials are automatically skipped.

---

## How domain discovery works

For each **cleaned** company name the orchestrator
(`backend/app/services/search/discovery.py`):

1. Checks the **in-run dedup map**, then **Redis**, then the durable cache.
2. Queries providers **in order**, stopping as soon as a confident answer emerges.
3. Runs the **verifier** (`backend/app/services/search/verifier.py`):
   - An **authoritative** Wikidata *official website* match wins immediately.
   - Otherwise web candidates are scored on name-to-domain match, search rank,
     multi-provider agreement, and corroborating evidence (LinkedIn/Crunchbase).
   - **Aggregators** (LinkedIn, Crunchbase, Wikipedia, ...) are never returned as
     the official domain — only a company's own site qualifies.
4. If the best candidate is below `CONFIDENCE_THRESHOLD`, the row is `NOT FOUND`
   with a reason. **No domain is ever invented.**

Every attempt is logged (provider, query, URL, timing, outcome) for transparency.

---

## API reference

Base path: `/api/v1`. Full interactive docs at `/docs`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/auth/signup` | Create account, returns JWTs. |
| `POST` | `/auth/login` | OAuth2 password login (`username`=email). |
| `POST` | `/auth/refresh` | Exchange refresh token. |
| `GET`  | `/auth/me` | Current user. |
| `POST` | `/auth/forgot-password` | Begin password reset. |
| `POST` | `/auth/reset-password` | Complete password reset. |
| `POST` | `/uploads` | Upload `.xlsx`/`.csv`; returns columns + preview. |
| `GET`  | `/uploads` | List your uploads. |
| `POST` | `/jobs/process` | Start processing `{upload_id, company_column}`. |
| `GET`  | `/jobs/{id}/progress` | Live progress snapshot. |
| `GET`  | `/jobs/{id}/results` | Paginated per-row results. |
| `GET`  | `/jobs/{id}/logs` | Live job logs. |
| `GET`  | `/jobs/{id}/download?fmt=xlsx\|csv` | Download enriched file. |
| `GET`  | `/admin/stats` | Platform statistics (admin). |
| `GET`  | `/admin/users`, `/admin/jobs` | Management (admin). |
| `PATCH`| `/admin/users/{id}/toggle-active` | Enable/disable a user (admin). |

### Output columns

`Original Company` - `Clean Company Name` - `Official Domain` -
`Verification Status` - `Confidence` - `Source Used` - `Search URL` -
`Processing Time`.

---

## Database schema

PostgreSQL tables (see `backend/app/db/models.py`):
`users`, `uploads`, `jobs`, `companies` (per-row results),
`cached_domains` (durable cache), `search_history`, `logs`.

Tables are created automatically on startup (`Base.metadata.create_all`).

---

## Testing

```bash
cd backend
source .venv/bin/activate
pytest            # cleaning, verifier, and discovery unit tests (no infra needed)
```

The suite covers the company-cleaning rules against every documented example,
the verification/scoring logic (including the "never guess" guarantees), and the
discovery orchestrator using an in-memory fake provider.

---

## Project structure

```
domain-finder/
├── docker-compose.yml         # db, redis, backend, worker, frontend, nginx
├── .env.example
├── nginx/nginx.conf           # top-level reverse proxy (HTTPS-ready)
├── sample_data/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py            # FastAPI app + lifespan
│   │   ├── core/              # config, security, logging
│   │   ├── db/                # base, session, models
│   │   ├── schemas/           # pydantic schemas
│   │   ├── api/               # deps + routes (auth, uploads, jobs, admin)
│   │   ├── services/          # cleaning, cache, files, search/*
│   │   └── workers/           # celery_app, tasks
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── src/
    │   ├── components/ (ui/ + feature components)
    │   ├── pages/     (Login, Signup, ForgotPassword, Dashboard, Admin)
    │   ├── hooks/     (auth, theme, toast)
    │   ├── lib/       (api client, utils)
    │   └── types/
    └── nginx.conf             # SPA static server
```

---

## License

Provided as-is for evaluation and deployment. Configure your own search-provider
API keys and comply with each provider's terms of service.

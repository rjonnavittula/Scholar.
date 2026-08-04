# HIVE Tasks — a self-hosted, Shovel-style study planner brain

The planning **brain** for a H.I.V.E. study/productivity stack. Super
Productivity (re-skinned with the `ma.` theme) is the **client**; this FastAPI
service is the **source of record**, the **Cushion engine**, and the
**Canvas/LMS ingestion** layer.

## Why this split
Super Productivity is local-first with no server — great UI, no shared brain.
A self-hosted Vikunja-style API gives you a real database of record, an
automatable surface, and room for the one thing SP lacks: the Cushion.

```
  Canvas / Brightspace / Moodle
            │  (clients/canvas_sync.py)
            ▼
   ┌────────────────────┐   POST /ingest/canvas
   │   HIVE Tasks API    │◄──────────────────────  external scripts / H.I.V.E. agents
   │  FastAPI + Postgres │
   │  • tasks / courses  │
   │  • commitments      │   GET /cushion  ──►  "feasible? tightest slack = 6h 20m"
   │  • Cushion engine   │
   └─────────┬───────────┘
             │  (Phase 2: custom SP SyncProvider)
             ▼
   Super Productivity (ma. theme)  —  timeboxing, planner, timer, the pretty UI
```

## Run it
```bash
cp .env.example .env && $EDITOR .env        # set DB creds
docker compose up -d --build
# API docs:  http://<host>:8077/docs   (Swagger)   /redoc
# SP web:    http://<host>:8080
```
Local dev without Docker: `pip install -r requirements.txt && uvicorn app.main:app --reload --port 8077`

The API also serves a first-party web UI at `http://<host>:8077/` (`webui/`,
vanilla JS/CSS, no build step) — calendar, courses, analytics, settings, all
against this same API. It's the simplest way to actually use the app today;
Super Productivity remains an optional, separate client for whoever wants it.

## First calls
```bash
# 1. mint a key (no auth required on this one endpoint for bootstrap — lock it
#    down behind your reverse proxy / Tailscale, or guard it before exposing)
curl -X POST "http://127.0.0.1:8077/auth/keys?label=laptop"

# 2. create a task
curl -X POST http://127.0.0.1:8077/tasks \
  -H "X-API-Key: hive_xxx" -H "Content-Type: application/json" \
  -d '{"title":"CMPSC 465 HW3","due_at":"2026-06-15T23:59:00","time_needed_min":180}'

# 3. ask the Cushion if you're going to make it
curl http://127.0.0.1:8077/cushion -H "X-API-Key: hive_xxx"
```

## What's built (v0) vs next
**Built:** tasks/courses CRUD, API-key auth (mint/list/revoke), Canvas ingest
(token sync, ICS calendar feed, bookmarklet import, upsert by external id),
weighted grades, PDF/text syllabus parsing, the EDF Cushion engine, past/future
analytics + CSV export, study streaks, Alembic migrations, a first-party web
UI (`webui/`, calendar/courses/analytics/settings), and a full learning/RAG
subsystem — source parsing/chunking, Ollama embeddings, Qdrant semantic
search, retrieval-grounded lesson generation, and OKF course export/import.
This has been runtime-tested end to end, not just wired.

**Next:**
- Phase 2: custom Super Productivity **SyncProvider** so the SP UI reads/writes
  this API instead of WebDAV — that's what makes SP a true client.
- Phase 3: a **Cushion widget** inside SP's planner (the one feature SP lacks).
- Per-day capacity config, JWT + multi-user, an "available time" view,
  write-back from SP to HIVE.
```

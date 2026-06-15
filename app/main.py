"""HIVE Tasks API — the planning brain for the H.I.V.E. study/productivity stack.

A self-hostable, Vikunja-flavored REST service. Source of record for tasks,
courses, commitments and events; computes the Shovel-style Cushion; ingests
assignments from Canvas/LMS. Super Productivity (re-skinned) is the client.

Run locally:   uvicorn app.main:app --reload
Docs:          http://127.0.0.1:8077/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    commitments_router,
    auth_router,
    courses_router,
    cushion_router,
    ingest_router,
    tasks_router,
)
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="HIVE Tasks API",
    version="0.1.0",
    summary="Self-hosted study planner brain — tasks, courses, and the Cushion.",
    description=__doc__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

for r in (auth_router, courses_router, tasks_router, commitments_router, ingest_router, cushion_router):
    app.include_router(r)

# CORS: the Cushion panel runs inside Super Productivity (different origin)
# and calls GET /cushion with an X-API-Key header. Auth is the API key, not
# cookies, so a permissive origin policy is acceptable on a Tailscale-only
# deployment. Tighten HIVE_CORS_ORIGINS to your SP origin(s) if you prefer.
import os as _os  # noqa: E402

_origins = _os.getenv("HIVE_CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The Shovel-style web UI (ma. dark). Served at / when webui/ exists;
# API routes and /docs are registered first, so they take precedence.
from pathlib import Path as _Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_webui = _Path(__file__).resolve().parent.parent / "webui"
if _webui.is_dir():
    app.mount("/", StaticFiles(directory=_webui, html=True), name="webui")


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    return {"status": "ok"}

"""HIVE Scholar — self-hosted Shovel-style study planner (brain + web UI)."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    activities_router, auth_router, awake_router, config_router,
    courses_router, cushion_router, integrations_router, planned_router,
    streak_router, tasks_router, timer_router,
)
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="HIVE Scholar API", version="0.4.21", lifespan=lifespan)

for r in (auth_router, courses_router, tasks_router, activities_router,
          planned_router, awake_router, config_router, cushion_router,
          streak_router, timer_router, integrations_router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_webui = Path(__file__).resolve().parent.parent / "webui"
if _webui.is_dir():
    app.mount("/", StaticFiles(directory=_webui, html=True), name="webui")

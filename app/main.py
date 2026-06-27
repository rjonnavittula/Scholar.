"""HIVE Scholar — self-hosted Shovel-style study planner (brain + web UI)."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    activities_router, analytics_router, auth_router, awake_router, config_router,
    courses_router, cushion_router, grades_router, integrations_router, learn_router, planned_router,
    streak_router, tasks_router, timer_router,
)
from app.db import init_db


def _maybe_autosync():
    """Run a Canvas sync if auto-sync is on and the interval has elapsed.
    Synchronous + network-bound — call via asyncio.to_thread. Never raises."""
    from sqlmodel import Session
    from app.db import engine
    from app.models import Settings
    try:
        with Session(engine) as s:
            st = s.get(Settings, 1)
            if not st or not getattr(st, "canvas_autosync", False):
                return
            hours = max(1, getattr(st, "canvas_sync_hours", 12) or 12)
            last = getattr(st, "canvas_last_sync", None)
            if last and (datetime.now() - last) < timedelta(hours=hours):
                return
            from app.integrations import sync_canvas_ics, sync_canvas
            if st.canvas_ics_url:
                sync_canvas_ics(s, st)
            elif st.canvas_token and st.canvas_base_url:
                sync_canvas(s, st)
            else:
                return
            st.canvas_last_sync = datetime.now()
            s.add(st); s.commit()
    except Exception as e:  # background task must never crash the app
        print(f"[autosync] {e}")


async def _autosync_loop():
    first = True
    while True:
        try:
            await asyncio.sleep(60 if first else 900)   # ~1 min after boot, then every 15 min
            first = False
            await asyncio.to_thread(_maybe_autosync)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[autosync loop] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_autosync_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="HIVE Scholar API", version="0.5.11", lifespan=lifespan)

for r in (auth_router, courses_router, tasks_router, activities_router,
          planned_router, awake_router, config_router, cushion_router,
          streak_router, timer_router, integrations_router, analytics_router,
          grades_router, learn_router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

_webui = Path(__file__).resolve().parent.parent / "webui"
if _webui.is_dir():
    app.mount("/", StaticFiles(directory=_webui, html=True), name="webui")

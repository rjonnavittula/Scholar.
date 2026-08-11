"""HIVE Scholar v2 HTTP surface."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session, select

from zoneinfo import ZoneInfo

from app.cushion import EngineConfig, availability_days, compute_cushion
from app.rollup import roll_up
from app.learn_parser import parse_source
from app.learn_store import (
    add_lesson_block, complete_learning_node, create_track_from_spec, delete_track,
    get_lesson_tree, get_or_create_lesson_for_node, get_track_tree, list_tracks,
    start_learning_node,
)
from app.chunk_store import list_source_chunks
from app.chunker import chunk_registered_source
from app.source_store import (
    create_source, delete_source, get_source, get_source_audit, link_source_to_track, list_sources,
    list_source_sections, list_track_sources, parse_registered_source, unlink_source_from_track,
)
from app.source_upload import build_upload_source_spec
from app.embedding_client import embed_text_preview, get_embedding_health
from app.vector_store import ensure_scholar_collection, get_memory_layers, get_qdrant_health, upsert_source_chunks
from app.generation_client import get_generation_health
from app.rag_engine import generate_lesson_blocks


def _due_to_utc(due, school_tz: str):
    """A due datetime from the UI is wall-clock in the SCHOOL zone.
    Store it as an aware UTC instant. Already-aware inputs are respected."""
    if due is None:
        return None
    if due.tzinfo is not None:
        return due.astimezone(ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(school_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return due.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))


def _home_to_utc(dt, home_tz: str):
    """A planned-block wall time from the UI is in the user's HOME zone."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(home_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return dt.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))
from app.db import get_session
from app.models import (
    Activity, ApiKey, AwakeTime, Course, Holiday, PlannedBlock,
    ActiveTimer, Settings, Source, Task, TaskStatus, Term, TimeLog,
)


# ---- auth ------------------------------------------------------------------ #
def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> ApiKey:
    key = session.exec(
        select(ApiKey).where(ApiKey.hashed_key == _hash(x_api_key), ApiKey.revoked == False)  # noqa: E712
    ).first()
    if not key:
        raise HTTPException(401, "invalid_or_revoked_api_key")
    return key


auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/keys", summary="Mint a new API key (shown once)")
def create_key(label: str = Query(...), session: Session = Depends(get_session)):
    raw = "hive_" + secrets.token_urlsafe(32)
    rec = ApiKey(label=label, hashed_key=_hash(raw))
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"id": rec.id, "label": rec.label, "api_key": raw}


AUTH = [Depends(require_api_key)]


@auth_router.get("/keys", summary="List minted API keys (never the key itself)", dependencies=AUTH)
def list_keys(session: Session = Depends(get_session)):
    rows = session.exec(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return [{"id": k.id, "label": k.label, "created_at": k.created_at, "revoked": k.revoked} for k in rows]


@auth_router.post("/keys/{key_id}/revoke", summary="Revoke an API key", dependencies=AUTH)
def revoke_key(key_id: int, session: Session = Depends(get_session)):
    key = session.get(ApiKey, key_id)
    if not key:
        raise HTTPException(404, "key_not_found")
    key.revoked = True
    session.add(key)
    session.commit()
    return {"id": key.id, "revoked": True}


# ---- learn / forge --------------------------------------------------------- #
class ParseSourceIn(BaseModel):
    text: str


class ParseSourceOut(BaseModel):
    input_type: str
    track_title: str
    role: Optional[str] = None
    modules: list[str]
    teaching_rules: list[str]
    assessment_rules: list[str]
    visual_rules: list[str]
    constraints: list[str]
    source_hash: str


class ForgeTrackIn(BaseModel):
    track_title: str
    input_type: str = "source_text"
    role: Optional[str] = None
    modules: list[str] = PydanticField(default_factory=list)
    teaching_rules: list[str] = PydanticField(default_factory=list)
    assessment_rules: list[str] = PydanticField(default_factory=list)
    visual_rules: list[str] = PydanticField(default_factory=list)
    constraints: list[str] = PydanticField(default_factory=list)
    source_hash: str = ""


class SourceIn(BaseModel):
    title: str = ""
    source_type: str = "text"
    trust_level: str = "user"
    mime_type: str = "text/plain"
    original_name: str = ""
    body_text: str
    metadata: dict = PydanticField(default_factory=dict)


class TrackSourceLinkIn(BaseModel):
    role: str = "primary"


class ChunkSourceIn(BaseModel):
    max_chars: int = 900
    overlap_chars: int = 120
    replace: bool = True


class EnsureQdrantIn(BaseModel):
    recreate: bool = False


class EmbeddingPreviewIn(BaseModel):
    text: str


class LessonBlockIn(BaseModel):
    block_type: str
    title: str = ""
    payload: dict = PydanticField(default_factory=dict)
    source_refs: list[str] = PydanticField(default_factory=list)
    confidence: float = 0.0


class NodeProgressIn(BaseModel):
    mastery: float = 1.0


learn_router = APIRouter(prefix="/learn", tags=["learn"], dependencies=AUTH)


@learn_router.post("/parse-source", response_model=ParseSourceOut)
def parse_learn_source(payload: ParseSourceIn):
    if not payload.text.strip():
        raise HTTPException(400, "text_required")
    return parse_source(payload.text)


@learn_router.get("/sources")
def list_learning_sources(session: Session = Depends(get_session)):
    return list_sources(session)


@learn_router.get("/memory/layers")
def read_memory_layers():
    return get_memory_layers()


@learn_router.get("/memory/qdrant/health")
def read_qdrant_health():
    return get_qdrant_health()


@learn_router.post("/memory/qdrant/ensure")
def ensure_qdrant_collection(payload: EnsureQdrantIn | None = None):
    result = ensure_scholar_collection(recreate=bool(payload and payload.recreate))
    if result.get("status") == "unavailable":
        raise HTTPException(400, result.get("error") or "qdrant_unavailable")
    return result


@learn_router.get("/memory/embeddings/health")
def read_embedding_health():
    return get_embedding_health()


@learn_router.get("/memory/generation/health")
def read_generation_health():
    return get_generation_health()


@learn_router.post("/memory/embeddings/preview")
def preview_embedding(payload: EmbeddingPreviewIn):
    try:
        return embed_text_preview(payload.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@learn_router.post("/sources", status_code=201)
def create_learning_source(payload: SourceIn, session: Session = Depends(get_session)):
    try:
        return create_source(session, payload.dict())
    except ValueError as e:
        raise HTTPException(400, str(e))




@learn_router.post("/sources/upload", status_code=201)
async def upload_learning_source(
    file: UploadFile = File(...),
    title: str = Form(""),
    source_type: str = Form("auto"),
    trust_level: str = Form("user"),
    parse_now: bool = Form(False),
    session: Session = Depends(get_session),
):
    try:
        data = await file.read()
        spec = build_upload_source_spec(
            filename=file.filename or "upload.txt",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            title=title,
            source_type=source_type,
            trust_level=trust_level,
        )
        source = create_source(session, spec)
        if parse_now:
            parsed = parse_registered_source(session, int(source["id"]))
            return {"source": get_source(session, int(source["id"])), "parsed": parsed}
        return source
    except ValueError as e:
        raise HTTPException(400, str(e))

@learn_router.get("/sources/audit")
def audit_learning_sources(session: Session = Depends(get_session)):
    return get_source_audit(session)


@learn_router.get("/sources/{source_id}")
def read_learning_source(source_id: int, session: Session = Depends(get_session)):
    source = get_source(session, source_id)
    if not source:
        raise HTTPException(404, "source_not_found")
    return source


@learn_router.post("/sources/{source_id}/parse")
def parse_learning_source(source_id: int, session: Session = Depends(get_session)):
    try:
        parsed = parse_registered_source(session, source_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not parsed:
        raise HTTPException(404, "source_not_found")
    return parsed


@learn_router.get("/sources/{source_id}/sections")
def list_learning_source_sections(source_id: int, session: Session = Depends(get_session)):
    sections = list_source_sections(session, source_id)
    if sections is None:
        raise HTTPException(404, "source_not_found")
    return sections


@learn_router.post("/sources/{source_id}/chunk")
def chunk_learning_source(source_id: int, payload: ChunkSourceIn | None = None, session: Session = Depends(get_session)):
    config = payload or ChunkSourceIn()
    try:
        result = chunk_registered_source(
            session,
            source_id,
            max_chars=config.max_chars,
            overlap_chars=config.overlap_chars,
            replace=config.replace,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result:
        raise HTTPException(404, "source_not_found")
    return result


@learn_router.get("/sources/{source_id}/chunks")
def list_learning_source_chunks(source_id: int, session: Session = Depends(get_session)):
    chunks = list_source_chunks(session, source_id)
    if chunks is None:
        raise HTTPException(404, "source_not_found")
    return chunks


@learn_router.post("/sources/{source_id}/index")
def index_learning_source(source_id: int, session: Session = Depends(get_session)):
    try:
        return upsert_source_chunks(session, source_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@learn_router.delete("/sources/{source_id}", status_code=204)
def delete_learning_source(source_id: int, session: Session = Depends(get_session)):
    if not delete_source(session, source_id):
        raise HTTPException(404, "source_not_found")
    return None


@learn_router.get("/tracks/{track_id}/sources")
def list_learning_track_sources(track_id: int, session: Session = Depends(get_session)):
    sources = list_track_sources(session, track_id)
    if sources is None:
        raise HTTPException(404, "track_not_found")
    return sources


@learn_router.post("/tracks/{track_id}/sources/{source_id}", status_code=201)
def link_learning_source_to_track(
    track_id: int,
    source_id: int,
    payload: TrackSourceLinkIn,
    session: Session = Depends(get_session),
):
    try:
        source = link_source_to_track(session, track_id, source_id, payload.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not source:
        raise HTTPException(404, "track_or_source_not_found")
    return source


@learn_router.delete("/tracks/{track_id}/sources/{source_id}", status_code=204)
def unlink_learning_source_from_track(
    track_id: int,
    source_id: int,
    session: Session = Depends(get_session),
):
    result = unlink_source_from_track(session, track_id, source_id)
    if result is None:
        raise HTTPException(404, "track_or_source_not_found")
    if result is False:
        raise HTTPException(404, "source_link_not_found")
    return None


@learn_router.get("/tracks")
def list_learning_tracks(session: Session = Depends(get_session)):
    return list_tracks(session)


@learn_router.post("/tracks", status_code=201)
def create_learning_track(payload: ForgeTrackIn, session: Session = Depends(get_session)):
    return create_track_from_spec(session, payload.dict())


@learn_router.post("/tracks/from-source", status_code=201)
def create_learning_track_from_source(payload: ParseSourceIn, session: Session = Depends(get_session)):
    if not payload.text.strip():
        raise HTTPException(400, "text_required")
    return create_track_from_spec(session, parse_source(payload.text))


@learn_router.get("/tracks/{track_id}")
def read_learning_track(track_id: int, session: Session = Depends(get_session)):
    track = get_track_tree(session, track_id)
    if not track:
        raise HTTPException(404, "track_not_found")
    return track


@learn_router.delete("/tracks/{track_id}", status_code=204)
def delete_learning_track(track_id: int, session: Session = Depends(get_session)):
    if not delete_track(session, track_id):
        raise HTTPException(404, "track_not_found")
    return None


@learn_router.get("/nodes/{node_id}/lesson")
def read_or_create_node_lesson(node_id: int, session: Session = Depends(get_session)):
    lesson = get_or_create_lesson_for_node(session, node_id)
    if not lesson:
        raise HTTPException(404, "node_not_found")
    return lesson


@learn_router.post("/nodes/{node_id}/start")
def start_learning_lesson(node_id: int, session: Session = Depends(get_session)):
    try:
        result = start_learning_node(session, node_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result:
        raise HTTPException(404, "node_not_found")
    return result


@learn_router.post("/nodes/{node_id}/generate")
def generate_node_lesson(node_id: int, session: Session = Depends(get_session)):
    result = generate_lesson_blocks(session, node_id)
    if not result:
        raise HTTPException(404, "node_not_found")
    return result


@learn_router.post("/nodes/{node_id}/complete")
def complete_learning_lesson(node_id: int, payload: NodeProgressIn, session: Session = Depends(get_session)):
    try:
        result = complete_learning_node(session, node_id, payload.mastery)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result:
        raise HTTPException(404, "node_not_found")
    return result


@learn_router.get("/lessons/{lesson_id}")
def read_learning_lesson(lesson_id: int, session: Session = Depends(get_session)):
    lesson = get_lesson_tree(session, lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson_not_found")
    return lesson


@learn_router.post("/lessons/{lesson_id}/blocks", status_code=201)
def create_learning_block(lesson_id: int, payload: LessonBlockIn, session: Session = Depends(get_session)):
    try:
        lesson = add_lesson_block(session, lesson_id, payload.dict())
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not lesson:
        raise HTTPException(404, "lesson_not_found")
    return lesson


@learn_router.get("/tracks/{track_id}/search", summary="Semantic search over a course's indexed sources")
def search_learning_track(track_id: int, q: str = "", session: Session = Depends(get_session)):
    from app.rag_engine import search_track
    return {"results": search_track(session, track_id, q)}


@learn_router.get("/tracks/{track_id}/okf/export", summary="Export a course as a portable OKF bundle")
def export_learning_track_okf(track_id: int, session: Session = Depends(get_session)):
    from app.okf import export_filename, export_track_okf
    bundle = export_track_okf(session, track_id)
    if not bundle:
        raise HTTPException(404, "track_not_found")
    return {"filename": export_filename(bundle), "json": bundle}


@learn_router.post("/okf/import", status_code=201, summary="Import a portable OKF bundle as a new course")
def import_learning_track_okf(payload: dict, session: Session = Depends(get_session)):
    from app.okf import import_track_okf
    try:
        return import_track_okf(session, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"okf_import_failed: {e}")


# ---- tutor mode ---------------------------------------------------------------#
@learn_router.get("/tutor/presets", summary="Curated tutor persona presets")
def list_tutor_presets():
    from app.tutor_presets import list_presets
    return list_presets()


@learn_router.post("/tracks/{track_id}/tutor/generate-prompt", summary="Expand a description into a tutor system prompt (preview, not saved)")
def generate_tutor_system_prompt(track_id: int, payload: dict, session: Session = Depends(get_session)):
    from app.models import LearningTrack
    from app.tutor_engine import generate_tutor_prompt
    if not session.get(LearningTrack, track_id):
        raise HTTPException(404, "track_not_found")
    try:
        return {"system_prompt": generate_tutor_prompt(payload.get("describe", ""))}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"generation_failed: {e}")


@learn_router.post("/tracks/{track_id}/tutor/enable", summary="Enable tutor mode with a final system prompt")
def enable_track_tutor(track_id: int, payload: dict, session: Session = Depends(get_session)):
    from app.tutor_store import enable_tutor
    try:
        result = enable_tutor(session, track_id, payload.get("system_prompt", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result is None:
        raise HTTPException(404, "track_not_found")
    return result


@learn_router.post("/tracks/{track_id}/tutor/disable", summary="Disable tutor mode (keeps history)")
def disable_track_tutor(track_id: int, session: Session = Depends(get_session)):
    from app.tutor_store import disable_tutor
    result = disable_tutor(session, track_id)
    if result is None:
        raise HTTPException(404, "track_not_found")
    return result


@learn_router.get("/tracks/{track_id}/tutor/messages", summary="List a track's tutor conversation")
def list_track_tutor_messages(track_id: int, session: Session = Depends(get_session)):
    from app.tutor_store import list_messages
    messages = list_messages(session, track_id)
    if messages is None:
        raise HTTPException(404, "track_not_found")
    return messages


@learn_router.delete("/tracks/{track_id}/tutor/messages", status_code=204, summary="Clear a track's tutor conversation")
def clear_track_tutor_messages(track_id: int, session: Session = Depends(get_session)):
    from app.tutor_store import clear_messages
    if not clear_messages(session, track_id):
        raise HTTPException(404, "track_not_found")
    return None


@learn_router.post("/tracks/{track_id}/tutor/messages", summary="Send a message, stream the tutor's reply")
def send_track_tutor_message(track_id: int, payload: dict, session: Session = Depends(get_session)):
    from fastapi.responses import StreamingResponse
    from app.models import LearningTrack
    from app.tutor_engine import run_tutor_turn

    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "content_required")
    if not session.get(LearningTrack, track_id):
        raise HTTPException(404, "track_not_found")

    def _events():
        import json as _json
        for event in run_tutor_turn(track_id, content):
            yield _json.dumps(event) + "\n"

    return StreamingResponse(_events(), media_type="application/x-ndjson")


# ---- engine context helper -------------------------------------------------- #
def engine_ctx(session: Session):
    st = session.get(Settings, 1) or Settings(id=1)
    awake = {a.weekday: (a.start_min, a.end_min)
             for a in session.exec(select(AwakeTime)).all()}
    cfg = EngineConfig(min_block_min=st.min_block_min, awake=awake or None,
                       home_tz=st.home_tz, school_tz=st.school_tz)
    activities = session.exec(select(Activity)).all()
    planned = session.exec(select(PlannedBlock)).all()
    term = session.exec(select(Term)).first()
    holidays = session.exec(select(Holiday)).all()
    return st, cfg, activities, planned, term, holidays


# ---- courses ----------------------------------------------------------------#
courses_router = APIRouter(prefix="/courses", tags=["courses"], dependencies=AUTH)


@courses_router.get("")
def list_courses(session: Session = Depends(get_session)):
    return session.exec(select(Course)).all()


@courses_router.post("", status_code=201)
def create_course(c: Course, session: Session = Depends(get_session)):
    session.add(c); session.commit(); session.refresh(c)
    return c


@courses_router.patch("/{cid}")
def update_course(cid: int, body: dict, session: Session = Depends(get_session)):
    c = session.get(Course, cid)
    if not c:
        raise HTTPException(404)
    for k in ("name", "color", "instructor", "url", "notes", "credits"):
        if k in body:
            setattr(c, k, body[k])
    session.add(c); session.commit(); session.refresh(c)
    return c


@courses_router.delete("/{cid}", status_code=204)
def delete_course(cid: int, session: Session = Depends(get_session)):
    c = session.get(Course, cid)
    if not c:
        return
    # "delete course, keep its tasks" - null out the FK on everything that
    # references this course first, or the delete hits a FK violation.
    for t in session.exec(select(Task).where(Task.course_id == cid)):
        t.course_id = None; session.add(t)
    for a in session.exec(select(Activity).where(Activity.course_id == cid)):
        a.course_id = None; session.add(a)
    session.delete(c); session.commit()


# ---- tasks ------------------------------------------------------------------#
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=AUTH)


class TaskIn(BaseModel):
    title: str
    notes: str = ""
    course_id: Optional[int] = None
    parent_id: Optional[int] = None
    category: str = ""
    due_at: Optional[datetime] = None
    start_date: Optional[date] = None
    time_needed_min: int = 60
    priority_flag: bool = False


class TaskPatch(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    course_id: Optional[int] = None
    parent_id: Optional[int] = None
    category: Optional[str] = None
    due_at: Optional[datetime] = None
    start_date: Optional[date] = None
    time_needed_min: Optional[int] = None
    time_spent_min: Optional[int] = None
    priority_flag: Optional[bool] = None
    status: Optional[TaskStatus] = None


@tasks_router.get("")
def list_tasks(status: Optional[TaskStatus] = None,
               session: Session = Depends(get_session)):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    rows = session.exec(stmt.order_by(Task.due_at)).all()
    kids = {}
    for t in rows:
        if t.parent_id is not None:
            kids.setdefault(t.parent_id, []).append(t)
    out = []
    for t in rows:
        if t.parent_id is not None:
            continue  # children are nested under parents below
        d = {**t.model_dump(), "remaining_min": t.remaining_min,
             "direct_spent_min": t.time_spent_min}
        ch = kids.get(t.id, [])
        if ch:
            d["subtasks"] = [{**c.model_dump(), "remaining_min": c.remaining_min,
                              "direct_spent_min": c.time_spent_min} for c in ch]
            d["time_needed_min"] = sum(c.time_needed_min for c in ch)
            # parent total = subtasks' spent + time logged directly on the parent
            d["time_spent_min"] = sum(c.time_spent_min for c in ch) + t.time_spent_min
            d["remaining_min"] = max(0, d["time_needed_min"] - d["time_spent_min"])
        else:
            d["subtasks"] = []
        out.append(d)
    return out


@tasks_router.post("", status_code=201)
def create_task(payload: TaskIn, session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    data = payload.model_dump()
    data["due_at"] = _due_to_utc(data.get("due_at"), st.school_tz)
    t = Task(**data, source=Source.api)
    if t.due_at and not t.start_date:
        t.start_date = t.due_at.date() - timedelta(days=st.start_ahead_days)
    session.add(t); session.commit(); session.refresh(t)
    return t


@tasks_router.patch("/{tid}")
def update_task(tid: int, payload: TaskPatch, session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if not t:
        raise HTTPException(404)
    patch = payload.model_dump(exclude_unset=True)
    if "due_at" in patch:
        st = session.get(Settings, 1) or Settings(id=1)
        patch["due_at"] = _due_to_utc(patch["due_at"], st.school_tz)
    going_done = patch.get("status") == TaskStatus.done and t.status != TaskStatus.done
    for k, v in patch.items():
        setattr(t, k, v)
    now_utc = datetime.now(ZoneInfo("UTC"))
    t.updated_at = now_utc
    if going_done:
        t.completed_at = now_utc
        # log any not-yet-logged spent time so the streak/effort reflects it
        already = sum(lg.minutes for lg in session.exec(
            select(TimeLog).where(TimeLog.task_id == t.id)).all())
        gap = max(0, t.time_spent_min - already)
        if gap:
            session.add(TimeLog(task_id=t.id, minutes=gap, logged_at=now_utc, source="manual"))
    elif patch.get("status") == TaskStatus.todo and t.completed_at:
        t.completed_at = None  # un-completing
    session.add(t); session.commit(); session.refresh(t)
    return t


@tasks_router.post("/{tid}/log", summary="Log focused minutes on a task")
def log_time(tid: int, minutes: int = Query(..., gt=0), session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if not t:
        raise HTTPException(404)
    t.time_spent_min += minutes
    t.updated_at = datetime.now(ZoneInfo("UTC"))
    session.add(t)
    session.add(TimeLog(task_id=tid, minutes=minutes, source="timer"))
    session.commit()
    return {"task_id": tid, "time_spent_min": t.time_spent_min}


@tasks_router.delete("/{tid}", status_code=204)
def delete_task(tid: int, session: Session = Depends(get_session)):
    t = session.get(Task, tid)
    if t:
        for p in session.exec(select(PlannedBlock).where(PlannedBlock.task_id == tid)):
            session.delete(p)
        session.delete(t); session.commit()


# ---- activities --------------------------------------------------------------#
activities_router = APIRouter(prefix="/activities", tags=["activities"], dependencies=AUTH)


class ActivityPatch(BaseModel):
    title: Optional[str] = None
    color: Optional[str] = None
    weekday: Optional[int] = None
    start_min: Optional[int] = None
    end_min: Optional[int] = None
    tz: Optional[str] = None
    course_id: Optional[int] = None
    notes: Optional[str] = None


@activities_router.get("")
def list_activities(session: Session = Depends(get_session)):
    return session.exec(select(Activity)).all()


@activities_router.post("", status_code=201)
def create_activity(a: Activity, session: Session = Depends(get_session)):
    if not (0 <= a.start_min < a.end_min <= 1440):
        raise HTTPException(400, "bad_time_range")
    session.add(a); session.commit(); session.refresh(a)
    return a


@activities_router.patch("/{aid}")
def update_activity(aid: int, payload: ActivityPatch, session: Session = Depends(get_session)):
    a = session.get(Activity, aid)
    if not a:
        raise HTTPException(404, "activity_not_found")
    patch = payload.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(a, k, v)
    if not (0 <= a.start_min < a.end_min <= 1440):
        raise HTTPException(400, "bad_time_range")
    session.add(a); session.commit(); session.refresh(a)
    return a


@activities_router.delete("/{aid}", status_code=204)
def delete_activity(aid: int, session: Session = Depends(get_session)):
    a = session.get(Activity, aid)
    if a:
        session.delete(a); session.commit()


# ---- planned blocks (DO dates) ------------------------------------------------#
planned_router = APIRouter(prefix="/planned", tags=["planned"], dependencies=AUTH)


class PlanIn(BaseModel):
    task_id: int
    start_at: datetime
    end_at: datetime


class PlanPatch(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    completed: Optional[bool] = None


@planned_router.get("")
def list_planned(session: Session = Depends(get_session)):
    return session.exec(select(PlannedBlock)).all()


@planned_router.post("", status_code=201)
def create_planned(p: PlanIn, session: Session = Depends(get_session)):
    if p.end_at <= p.start_at:
        raise HTTPException(400, "end_before_start")
    if not session.get(Task, p.task_id):
        raise HTTPException(404, "task_not_found")
    st = session.get(Settings, 1) or Settings(id=1)
    data = p.model_dump()
    data["start_at"] = _home_to_utc(data["start_at"], st.home_tz)
    data["end_at"] = _home_to_utc(data["end_at"], st.home_tz)
    pb = PlannedBlock(**data)
    session.add(pb); session.commit(); session.refresh(pb)
    return pb


@planned_router.patch("/{pid}")
def update_planned(pid: int, body: PlanPatch, session: Session = Depends(get_session)):
    pb = session.get(PlannedBlock, pid)
    if not pb:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
    st = session.get(Settings, 1) or Settings(id=1)
    if "start_at" in data:
        data["start_at"] = _home_to_utc(data["start_at"], st.home_tz)
    if "end_at" in data:
        data["end_at"] = _home_to_utc(data["end_at"], st.home_tz)
    was_completed = pb.completed
    for k, v in data.items():
        setattr(pb, k, v)
    # completing a block logs its duration onto the task
    if data.get("completed") and not was_completed:
        t = session.get(Task, pb.task_id)
        if t:
            t.time_spent_min += int((pb.end_at - pb.start_at).total_seconds() // 60)
            t.updated_at = datetime.now()
            session.add(t)
    session.add(pb); session.commit(); session.refresh(pb)
    return pb


@planned_router.delete("/{pid}", status_code=204)
def delete_planned(pid: int, session: Session = Depends(get_session)):
    pb = session.get(PlannedBlock, pid)
    if pb:
        session.delete(pb); session.commit()


# ---- awake time ---------------------------------------------------------------#
awake_router = APIRouter(prefix="/awake", tags=["awake"], dependencies=AUTH)


class AwakeRow(BaseModel):
    weekday: int
    start_min: int
    end_min: int


@awake_router.get("")
def get_awake(session: Session = Depends(get_session)):
    return session.exec(select(AwakeTime).order_by(AwakeTime.weekday)).all()


@awake_router.put("")
def put_awake(rows: list[AwakeRow], session: Session = Depends(get_session)):
    for old in session.exec(select(AwakeTime)).all():
        session.delete(old)
    for r in rows:
        if not (0 <= r.start_min < r.end_min <= 1440):
            raise HTTPException(400, f"bad_range_weekday_{r.weekday}")
        session.add(AwakeTime(**r.model_dump()))
    session.commit()
    return {"ok": True}


# ---- term + settings -----------------------------------------------------------#
config_router = APIRouter(prefix="/config", tags=["config"], dependencies=AUTH)


@config_router.get("/settings")
def get_settings(session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    out = st.model_dump()
    out["canvas_token"] = bool(st.canvas_token)  # never echo the secret
    out["canvas_ics_url"] = bool(st.canvas_ics_url)  # ICS feed URLs embed a token too
    return out


@config_router.get("/timezones", summary="Zones grouped for the location picker")
def list_timezones(country: Optional[str] = None):
    # Friendly labels for US zones; falls back to the raw zone id elsewhere.
    US_LABELS = {
        "America/New_York": "Eastern", "America/Chicago": "Central",
        "America/Denver": "Mountain", "America/Phoenix": "Arizona (no DST)",
        "America/Los_Angeles": "Pacific", "America/Anchorage": "Alaska",
        "Pacific/Honolulu": "Hawaii",
    }
    try:
        import zoneinfo
        by_country = zoneinfo.available_timezones  # not country-mapped in stdlib
    except Exception:
        pass
    # stdlib has no country->zone map; ship a curated common set + full list.
    COUNTRIES = {
        "US": [("America/New_York", "Eastern"), ("America/Chicago", "Central"),
               ("America/Denver", "Mountain"), ("America/Phoenix", "Arizona (no DST)"),
               ("America/Los_Angeles", "Pacific"), ("America/Anchorage", "Alaska"),
               ("Pacific/Honolulu", "Hawaii")],
        "IN": [("Asia/Kolkata", "India (IST)")],
        "GB": [("Europe/London", "UK")],
        "CA": [("America/Toronto", "Eastern"), ("America/Winnipeg", "Central"),
               ("America/Edmonton", "Mountain"), ("America/Vancouver", "Pacific"),
               ("America/Halifax", "Atlantic")],
        "AU": [("Australia/Sydney", "Eastern"), ("Australia/Adelaide", "Central"),
               ("Australia/Perth", "Western")],
    }
    from zoneinfo import available_timezones
    out = {"countries": sorted(COUNTRIES.keys()),
           "zones": [{"id": z, "label": lbl} for z, lbl in COUNTRIES.get((country or "US").upper(), [])],
           "all": sorted(available_timezones())}
    return out


@config_router.put("/settings")
def put_settings(body: dict, session: Session = Depends(get_session)):
    from app.crypto import encrypt_secret
    st = session.get(Settings, 1) or Settings(id=1)
    for k in ("min_block_min", "start_ahead_days", "yellow_threshold_pct",
              "day_start_min", "canvas_base_url", "canvas_token", "canvas_ics_url",
              "home_tz", "school_tz", "week_start", "country",
              "theme", "accent", "density", "fontscale", "default_view",
              "display_name", "canvas_autosync", "canvas_sync_hours"):
        if k in body and body[k] is not None:
            value = body[k]
            if k in ("canvas_token", "canvas_ics_url") and isinstance(value, str):
                value = encrypt_secret(value)
            setattr(st, k, value)
    session.add(st); session.commit()
    return {"ok": True}


@config_router.get("/term")
def get_term(session: Session = Depends(get_session)):
    term = session.exec(select(Term)).first()
    holidays = session.exec(select(Holiday).order_by(Holiday.day)).all()
    return {"term": term, "holidays": holidays}


@config_router.put("/term")
def put_term(body: dict, session: Session = Depends(get_session)):
    term = session.exec(select(Term)).first() or Term()
    if "name" in body and body["name"] is not None:
        term.name = body["name"]
    for k in ("classes_start", "classes_end", "exam_end"):
        if k in body:
            v = body[k]
            setattr(term, k, date.fromisoformat(v) if isinstance(v, str) and v else (v or None))
    session.add(term); session.commit()
    return {"ok": True}


class HolidayIn(BaseModel):
    day: date
    name: str = ""


@config_router.post("/holidays", status_code=201)
def add_holiday(payload: HolidayIn, session: Session = Depends(get_session)):
    h = Holiday(**payload.model_dump())
    session.add(h); session.commit(); session.refresh(h)
    return h


@config_router.delete("/holidays/{hid}", status_code=204)
def del_holiday(hid: int, session: Session = Depends(get_session)):
    h = session.get(Holiday, hid)
    if h:
        session.delete(h); session.commit()


# ---- cushion + availability ------------------------------------------------------#
cushion_router = APIRouter(prefix="/cushion", tags=["cushion"], dependencies=AUTH)


@cushion_router.get("")
def get_cushion(session: Session = Depends(get_session)):
    st, cfg, acts, planned, term, hols = engine_ctx(session)
    tasks = roll_up(session.exec(select(Task)).all())
    r = compute_cushion(tasks, cfg, acts, planned, term, hols)
    return {
        "computed_at": r.computed_at,
        "feasible": r.feasible,
        "total_cushion_min": r.total_cushion_min,
        "total_cushion_human": f"{abs(r.total_cushion_min)//60}h {abs(r.total_cushion_min)%60:02d}m"
                               + (" short" if r.total_cushion_min < 0 else ""),
        "unscheduled_task_ids": r.unscheduled_task_ids,
        "per_task": [{**c.__dict__, "level": c.level(st.yellow_threshold_pct)}
                     for c in r.per_task],
    }


@cushion_router.get("/availability")
def get_availability(start: Optional[date] = None, days: int = 7,
                     session: Session = Depends(get_session)):
    _, cfg, acts, planned, term, hols = engine_ctx(session)
    start = start or date.today()
    days = max(1, min(days, 60))
    out = availability_days(start, days, cfg, acts, planned, term, hols)
    # decorate with due counts
    tasks = session.exec(select(Task).where(Task.status == TaskStatus.todo)).all()
    for d in out:
        d["due_count"] = sum(1 for t in tasks if t.due_at and t.due_at.date().isoformat() == d["date"])
    return out


# ---- timer (single global active timer) -----------------------------------#
timer_router = APIRouter(prefix="/timer", tags=["timer"], dependencies=AUTH)


def _timer_payload(tm, session):
    t = session.get(Task, tm.task_id)
    return {
        "task_id": tm.task_id,
        "title": t.title if t else "task",
        "parent_id": t.parent_id if t else None,
        "started_at": _aware(tm.started_at).isoformat(),
        "accumulated_sec": tm.accumulated_sec,
        "paused": tm.paused,
        "running": True,
    }


@timer_router.get("", summary="Current running timer (or null)")
def get_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    return _timer_payload(tm, session) if tm else {"running": False}


@timer_router.post("/start", summary="Start timing a task/subtask")
def start_timer(task_id: int = Query(...), session: Session = Depends(get_session)):
    if not session.get(Task, task_id):
        raise HTTPException(404, "task_not_found")
    existing = session.get(ActiveTimer, 1)
    replaced = None
    if existing:
        replaced = existing.task_id
        session.delete(existing); session.commit()
    tm = ActiveTimer(id=1, task_id=task_id,
                     started_at=datetime.now(ZoneInfo("UTC")), accumulated_sec=0, paused=False)
    session.add(tm); session.commit(); session.refresh(tm)
    out = _timer_payload(tm, session); out["replaced_task_id"] = replaced
    return out


@timer_router.post("/pause", summary="Pause — bank elapsed into accumulated")
def pause_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"running": False}
    if not tm.paused:
        elapsed = int((datetime.now(ZoneInfo("UTC")) - _aware(tm.started_at)).total_seconds())
        tm.accumulated_sec += max(0, elapsed)
        tm.paused = True
        session.add(tm); session.commit()
    return {"paused": True, "accumulated_sec": tm.accumulated_sec}


@timer_router.post("/resume", summary="Resume a paused timer")
def resume_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"running": False}
    if tm.paused:
        tm.started_at = datetime.now(ZoneInfo("UTC"))
        tm.paused = False
        session.add(tm); session.commit()
    return _timer_payload(tm, session)


@timer_router.post("/stop", summary="Stop, log the minutes, clear the timer")
def stop_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if not tm:
        return {"logged_min": 0}
    live = 0 if tm.paused else int((datetime.now(ZoneInfo("UTC")) - _aware(tm.started_at)).total_seconds())
    total_sec = tm.accumulated_sec + max(0, live)
    mins = round(total_sec / 60)
    task_id = tm.task_id
    if mins > 0:
        t = session.get(Task, task_id)
        if t:
            t.time_spent_min += mins
            session.add(t)
            session.add(TimeLog(task_id=task_id, minutes=mins, source="timer"))
    session.delete(tm); session.commit()
    return {"logged_min": mins, "task_id": task_id}


@timer_router.post("/cancel", summary="Discard the running timer — log nothing")
def cancel_timer(session: Session = Depends(get_session)):
    tm = session.get(ActiveTimer, 1)
    if tm:
        session.delete(tm); session.commit()
    return {"running": False, "discarded": True}


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))


# ---- study streak ----------------------------------------------------------#
streak_router = APIRouter(prefix="/streak", tags=["streak"], dependencies=AUTH)


@streak_router.get("", summary="Daily efficiency scores for the streak bar")
def get_streak(days: int = 9, session: Session = Depends(get_session)):
    from app.streak import current_streak, streak_window
    st = session.get(Settings, 1) or Settings(id=1)
    tasks = roll_up(session.exec(select(Task)).all())
    logs = session.exec(select(TimeLog)).all()
    window = streak_window(tasks, logs, days=max(1, min(days, 30)), home_tz=st.home_tz)
    return {
        "current": current_streak(window),
        "days": [{"day": d.day.isoformat(), "score": d.score, "level": d.level,
                  "completed": d.completed, "minutes": d.minutes, "overdue": d.overdue}
                 for d in window],
    }


@streak_router.get("/stats", summary="Plan-adherence streak + per-day heatmap data")
def get_streak_stats(session: Session = Depends(get_session)):
    from app.streak import streak_stats
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    tasks = roll_up(session.exec(select(Task)).all())
    logs = session.exec(select(TimeLog)).all()
    term_start = getattr(term, "start_date", None) if term else None
    return streak_stats(tasks, logs, planned, term_start, home_tz=st.home_tz)


# ---- analytics -------------------------------------------------------------#
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=AUTH)


@analytics_router.get("/past", summary="Past analytics aggregates for the insights page")
def analytics_past(range: str = "this_week", session: Session = Depends(get_session)):
    from app.analytics import past_analytics
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    return past_analytics(session, cfg, activities, planned, term, holidays, range)


@analytics_router.get("/future", summary="Forward-looking analytics for the insights page")
def analytics_future(range: str = "this_week", session: Session = Depends(get_session)):
    from app.analytics import future_analytics
    st, cfg, activities, planned, term, holidays = engine_ctx(session)
    return future_analytics(session, cfg, activities, planned, term, holidays, range)


@analytics_router.get("/export", summary="Export time logs as a CSV timesheet")
def analytics_export(range: str = "all", session: Session = Depends(get_session)):
    from app.analytics import timelog_export
    return timelog_export(session, range)


# ---- canvas integration ------------------------------------------------------------#
integrations_router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=AUTH)


@integrations_router.get("/canvas/status")
def canvas_status(session: Session = Depends(get_session)):
    st = session.get(Settings, 1) or Settings(id=1)
    return {"configured": bool(st.canvas_base_url and st.canvas_token),
            "base_url": st.canvas_base_url,
            "ics_configured": bool(st.canvas_ics_url),
            "autosync": bool(getattr(st, "canvas_autosync", False)),
            "sync_hours": getattr(st, "canvas_sync_hours", 12) or 12,
            "last_sync": st.canvas_last_sync.isoformat() if getattr(st, "canvas_last_sync", None) else None}


@integrations_router.post("/canvas/sync")
def canvas_sync(session: Session = Depends(get_session)):
    from app.integrations import sync_canvas
    st = session.get(Settings, 1) or Settings(id=1)
    if not (st.canvas_base_url and st.canvas_token):
        raise HTTPException(400, "canvas_not_configured")
    try:
        return sync_canvas(session, st)
    except Exception as e:  # surface the reason to the UI
        raise HTTPException(502, f"canvas_sync_failed: {e}")


@integrations_router.post("/canvas/sync-ics", summary="Pull the Canvas calendar feed (no token)")
def canvas_sync_ics(session: Session = Depends(get_session)):
    from app.integrations import sync_canvas_ics
    st = session.get(Settings, 1) or Settings(id=1)
    if not st.canvas_ics_url:
        raise HTTPException(400, "ics_not_configured")
    try:
        return sync_canvas_ics(session, st)
    except Exception as e:
        raise HTTPException(502, f"ics_sync_failed: {e}")


@integrations_router.post("/canvas/import", summary="Import data collected by the browser script")
def canvas_import(payload: dict, session: Session = Depends(get_session)):
    from app.integrations import import_canvas_payload
    st = session.get(Settings, 1) or Settings(id=1)
    if not isinstance(payload, dict) or not payload.get("assignments"):
        raise HTTPException(400, "empty_payload")
    try:
        return import_canvas_payload(session, st, payload)
    except Exception as e:
        raise HTTPException(502, f"import_failed: {e}")


@integrations_router.post("/syllabus/parse", summary="Extract candidate tasks from a syllabus (PDF or text, base64)")
def syllabus_parse(payload: dict, session: Session = Depends(get_session)):
    import base64
    from app.syllabus import extract_text, parse_syllabus
    try:
        data = base64.b64decode(payload.get("data_b64") or "")
    except Exception:
        raise HTTPException(400, "bad_file_data")
    if len(data) > 8_000_000:
        raise HTTPException(413, "file_too_large")
    text = extract_text(data, payload.get("filename", "") or "")
    if not text.strip():
        return {"items": [], "chars": 0, "note": "no extractable text — is this a scanned PDF?"}
    items = parse_syllabus(text, default_year=payload.get("year"),
                           dayfirst=bool(payload.get("dayfirst")))
    return {"items": items, "chars": len(text)}


@integrations_router.post("/syllabus/import", summary="Create tasks from reviewed syllabus items")
def syllabus_import(payload: dict, session: Session = Depends(get_session)):
    from app.integrations import import_syllabus_tasks
    st = session.get(Settings, 1) or Settings(id=1)
    items = payload.get("items") or []
    if not items:
        raise HTTPException(400, "no_items")
    try:
        return import_syllabus_tasks(session, st, course_name=payload.get("course_name"), items=items)
    except Exception as e:
        raise HTTPException(502, f"import_failed: {e}")


# ---- grades ----------------------------------------------------------------#
grades_router = APIRouter(prefix="/grades", tags=["grades"], dependencies=AUTH)


def _grade_structure(session, cid):
    from app.models import GradeCategory, GradeItem
    cats = session.exec(select(GradeCategory).where(GradeCategory.course_id == cid)
                        .order_by(GradeCategory.position)).all()
    items = session.exec(select(GradeItem).where(GradeItem.course_id == cid)).all()
    by_cat = {}
    for it in items:
        by_cat.setdefault(it.category_id, []).append(
            {"id": it.id, "title": it.title, "earned": it.earned, "possible": it.possible})
    return [{"id": c.id, "name": c.name, "weight": c.weight, "items": by_cat.get(c.id, [])} for c in cats]


@grades_router.get("/summary", summary="Current grade per course (for the hub)")
def grades_summary(session: Session = Depends(get_session)):
    from app.grades import compute_grade
    from app.models import GradeCategory, GradeItem
    cats = session.exec(select(GradeCategory)).all()
    items = session.exec(select(GradeItem)).all()
    items_by_cat = {}
    for it in items:
        items_by_cat.setdefault(it.category_id, []).append({"earned": it.earned, "possible": it.possible})
    by_course = {}
    for c in cats:
        by_course.setdefault(c.course_id, []).append(
            {"name": c.name, "weight": c.weight, "items": items_by_cat.get(c.id, [])})
    out = {}
    for cid, cl in by_course.items():
        s = compute_grade(cl)
        if s["percent"] is not None:
            out[str(cid)] = {"percent": s["percent"], "letter": s["letter"]}
    return out


@grades_router.get("/{cid}", summary="Grade categories + items + summary for a course")
def get_grades(cid: int, session: Session = Depends(get_session)):
    from app.grades import compute_grade
    cat_list = _grade_structure(session, cid)
    return {"categories": cat_list, "summary": compute_grade(cat_list)}


@grades_router.put("/{cid}", summary="Replace a course's grade structure")
def put_grades(cid: int, body: dict, session: Session = Depends(get_session)):
    from app.grades import compute_grade
    from app.models import GradeCategory, GradeItem
    if not session.get(Course, cid):
        raise HTTPException(404)
    for it in session.exec(select(GradeItem).where(GradeItem.course_id == cid)).all():
        session.delete(it)
    for c in session.exec(select(GradeCategory).where(GradeCategory.course_id == cid)).all():
        session.delete(c)
    session.commit()
    cat_list = []
    for pos, c in enumerate(body.get("categories") or []):
        cat = GradeCategory(course_id=cid, name=(c.get("name") or "").strip(),
                            weight=float(c.get("weight") or 0), position=pos)
        session.add(cat); session.commit(); session.refresh(cat)
        out_items = []
        for it in (c.get("items") or []):
            title = (it.get("title") or "").strip()
            poss = float(it.get("possible") or 0)
            earn = float(it.get("earned") or 0)
            if not title and poss == 0 and earn == 0:
                continue
            session.add(GradeItem(category_id=cat.id, course_id=cid, title=title, earned=earn, possible=poss))
            out_items.append({"title": title, "earned": earn, "possible": poss})
        cat_list.append({"name": cat.name, "weight": cat.weight, "items": out_items})
    session.commit()
    return {"summary": compute_grade(cat_list)}

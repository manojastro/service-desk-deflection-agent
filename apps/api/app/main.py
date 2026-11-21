from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.auth import CurrentUser, authenticate, create_token, require_roles
from apps.api.app.config import get_settings
from apps.api.app.dashboard import dashboard_snapshot, metrics_text
from apps.api.app.db import Database, seed_database
from packages.shared.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmationRequest,
    LoginRequest,
    LoginResponse,
    Role,
    UserContext,
)
from services.agent import ServiceDeskAgent


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("service_desk")
settings = get_settings()
db = Database()
rate_windows: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_database(db)
    logger.info(json.dumps({"event": "application_started", "environment": settings.app_env, "llm_provider": settings.llm_provider}))
    yield


app = FastAPI(
    title="Service Desk Deflection Agent API",
    version="0.1.0",
    description="Safe, grounded L1 IT support automation with strict deflection metrics.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:80]
    client = request.client.host if request.client else "local"
    now = time.monotonic()
    window = rate_windows[client]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        return Response(content='{"detail":"Rate limit exceeded"}', status_code=429, media_type="application/json", headers={"X-Request-ID": request_id})
    window.append(now)
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({"event": "http_request", "request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round((time.perf_counter()-started)*1000, 3)}))
    return response


@app.get("/health", tags=["operations"])
def health() -> dict:
    return {"status": "ok", "service": "service-desk-api"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict:
    try:
        db.fetchone("SELECT 1 AS ready")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready", "database": "connected", "llm_provider": settings.llm_provider}


@app.get("/metrics", tags=["operations"])
def metrics() -> Response:
    return Response(metrics_text(db), media_type="text/plain; version=0.0.4")


@app.post("/api/auth/login", response_model=LoginResponse, tags=["authentication"])
def login(payload: LoginRequest) -> LoginResponse:
    row = authenticate(db, payload.username, payload.password)
    if not row:
        db.insert_audit("login", "rejected", metadata={"username": payload.username[:80]})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    db.insert_audit("login", "accepted", actor_user_id=row["id"])
    return LoginResponse(access_token=create_token(row["id"]), role=Role(row["role"]), display_name=row["display_name"])


@app.post("/api/chat", response_model=ChatResponse, tags=["employee support"])
def chat(payload: ChatRequest, request: Request, user: CurrentUser) -> ChatResponse:
    return ServiceDeskAgent(db).start(payload.message, user, request.headers.get("X-Request-ID"))


@app.post("/api/chat/{session_id}/confirm", response_model=ChatResponse, tags=["employee support"])
def confirm(session_id: str, payload: ConfirmationRequest, user: CurrentUser) -> ChatResponse:
    try:
        return ServiceDeskAgent(db).confirm(session_id, payload.approved, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/trace", tags=["operations"])
def session_trace(session_id: str, user: CurrentUser) -> dict:
    session = db.fetchone("SELECT * FROM support_sessions WHERE id=?", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role == Role.EMPLOYEE and session["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Insufficient role")
    state = json.loads(session["state_json"])
    return {
        "session": {key: session[key] for key in ("id", "detected_intent", "status", "confidence", "ticket_id", "started_at", "completed_at", "duration_ms")},
        "states": state.get("trace", []),
        "evidence": db.fetchall("SELECT document_id,rank,hybrid_score,excerpt,latency_ms FROM retrieval_evidence WHERE session_id=? ORDER BY rank", (session_id,)),
        "tool_calls": db.fetchall("SELECT tool_name,arguments_json,result_json,success,duration_ms,created_at FROM tool_executions WHERE session_id=? ORDER BY created_at", (session_id,)),
        "audit": db.fetchall("SELECT event_type,outcome,safe_metadata_json,created_at FROM audit_events WHERE session_id=? ORDER BY created_at", (session_id,)),
    }


OpsUser = Annotated[UserContext, Depends(require_roles(Role.SUPPORT_AGENT, Role.ADMIN))]


@app.get("/api/dashboard", tags=["operations"])
def dashboard(_: OpsUser) -> dict:
    return dashboard_snapshot(db, settings)


@app.get("/api/tickets", tags=["operations"])
def tickets(_: OpsUser) -> list[dict]:
    return db.fetchall("SELECT external_id,session_id,status,priority,diagnostic_summary_json,created_at FROM tickets ORDER BY created_at DESC LIMIT 50")


@app.get("/api/users/me", tags=["authentication"])
def current_user(user: CurrentUser) -> UserContext:
    return user

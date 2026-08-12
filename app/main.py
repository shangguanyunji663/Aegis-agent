from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent_harness import AegisAgentHarness
from app.auth import AuthPrincipal
from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema, readiness_check
from app.evaluation import latest_evaluation, run_evaluation
from app.llm import build_llm_client
from app.models import CaseStatus, ReportStatus, UserRole
from app.orchestrator import PsychOrchestrator
from app.repository import DatabaseStore
from app.runtime import RuntimeServices
from app.skills import SkillRegistry
from app.tool_contracts import list_tool_contracts
from app.tool_gateway import build_tool_gateway
from app.services.tool_queue import ToolQueueWorker

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
EVAL_FIXTURES_DIR = ROOT / "eval" / "fixtures"
EVAL_OUTPUT_DIR = ROOT / "data" / "eval"
KNOWLEDGE_BACKUP_DIR = ROOT / "data" / "knowledge-backups"
logger = logging.getLogger("aegis.app")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ReportUpdate(BaseModel):
    status: ReportStatus


class SessionCreateRequest(BaseModel):
    title: str = "新对话"


class SessionRenameRequest(BaseModel):
    title: str


class CaseNoteRequest(BaseModel):
    note: str


class CaseStatusUpdate(BaseModel):
    status: CaseStatus


class KnowledgeIngestRequest(BaseModel):
    source: str
    content: str


class KnowledgeUploadRequest(BaseModel):
    filename: str
    content: str


class LoginRequest(BaseModel):
    username: str
    password: str


def create_app(runtime_settings: Settings | None = None) -> FastAPI:
    settings = runtime_settings or get_settings()
    knowledge_dir = settings.resolve_path(settings.knowledge_dir)
    engine = build_engine(settings)
    session_factory = build_session_factory(settings)
    create_schema(engine)
    store = DatabaseStore(session_factory, settings=settings)
    store.ensure_default_users()
    store.seed_knowledge_dir(knowledge_dir)
    runtime = RuntimeServices(settings)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge)
    llm_client = build_llm_client(settings)
    orchestrator = PsychOrchestrator(registry, store, llm_client)
    agent_harness = AegisAgentHarness(orchestrator, store)
    tool_gateway = build_tool_gateway(settings, store)
    tool_worker = ToolQueueWorker(settings, session_factory)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        tool_worker.start()
        try:
            yield
        finally:
            tool_worker.stop()

    app = FastAPI(title="Aegis Psych Agent", version="0.2.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.settings = settings
    app.state.engine = engine
    app.state.store = store
    app.state.registry = registry
    app.state.llm_client = llm_client
    app.state.orchestrator = orchestrator
    app.state.agent_harness = agent_harness
    app.state.runtime = runtime
    app.state.tool_gateway = tool_gateway
    app.state.tool_worker = tool_worker

    @app.middleware("http")
    async def attach_request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid4().hex[:12]}"
        trace_id = request.headers.get("X-Trace-ID") or f"trace-{uuid4().hex[:12]}"
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            payload = {
                "event": "http_request",
                "request_id": request_id,
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            }
            if duration_ms >= settings.slow_request_threshold_ms:
                logger.warning(json.dumps(payload | {"level": "warning", "kind": "slow_request"}, ensure_ascii=False))
            else:
                logger.info(json.dumps(payload | {"level": "info"}, ensure_ascii=False))
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response

    def current_principal(session_token: str | None = Cookie(default=None, alias=settings.auth_session_cookie)) -> AuthPrincipal:
        if not session_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        auth_session = store.get_auth_session(session_token)
        if auth_session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        user = auth_session["user"]
        return AuthPrincipal(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            auth_session_id=auth_session["auth_session_id"],
        )

    def require_admin(principal: AuthPrincipal = Depends(current_principal)) -> AuthPrincipal:
        if principal.role != UserRole.ADMIN.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return principal

    def assert_session_owner(session_id: str, principal: AuthPrincipal) -> None:
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if session["owner_user_id"] != principal.user_id:
            raise HTTPException(status_code=403, detail="session access denied")

    def audit(principal: AuthPrincipal, action: str, target_type: str, target_id: str, payload: dict | None = None) -> None:
        store.add_audit_log(principal.user_id, principal.username, principal.role, action, target_type, target_id, payload)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/student", response_class=HTMLResponse)
    def student_page() -> str:
        return (STATIC_DIR / "student.html").read_text(encoding="utf-8")

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page() -> str:
        return (STATIC_DIR / "admin.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "UP",
            "provider": llm_client.provider,
            "llm": llm_client.status(),
            "agent_runtime": settings.agent_runtime,
            "agent_models": orchestrator.model_registry.status(),
        }

    @app.get("/api/agent/status")
    def agent_status(principal: AuthPrincipal = Depends(current_principal)) -> dict:
        return {
            "runtimeHarness": {
                "name": agent_harness.name,
                "description": "统一管理输入脱敏、上下文注入、Agent runtime 调用、trace/report 输出和工具计划。",
            },
            "agentFramework": {
                "requested": settings.agent_runtime,
                "active": orchestrator.autonomous_runtime.framework_name if settings.agent_runtime == "autonomous" else "ordered_runtime",
                "scheduler": "claim-based-actor-runtime" if settings.agent_runtime == "autonomous" else "ordered-runtime",
                "langgraph": "disabled_by_request",
                "maxRounds": settings.agent_max_rounds,
                "maxClaimsPerRound": settings.agent_max_claims_per_round,
                "state": "append-only-blackboard",
            },
            "agents": [
                {"name": "MemoryAgent", "role": "session and private memory"},
                {"name": "SupervisorAgent", "aliasOf": "LeadAgent", "role": "intent routing"},
                {"name": "LeadAgent", "role": "intent routing"},
                {"name": "RiskGuardianAgent", "role": "risk assessment and response safety review"},
                {"name": "KnowledgeAgent", "role": "RAG and standard skill context"},
                {"name": "CounselorAgent", "role": "support response planning"},
                {"name": "CompanionAgent", "role": "low-risk companion response planning"},
            ],
            "memory": store.memory_backend_status(),
            "models": orchestrator.model_registry.status(),
            "toolBackend": tool_gateway.backend,
            "toolQueue": {
                "enabled": settings.tool_queue_enabled,
                "mode": "background-worker" if settings.tool_queue_enabled else "manual",
                "pollIntervalSeconds": settings.tool_queue_poll_interval_seconds,
                "batchSize": settings.tool_queue_batch_size,
                "workerThreads": settings.tool_queue_worker_threads,
            },
            "viewer": principal.username,
            "role": principal.role,
        }

    @app.get("/api/readiness")
    def readiness() -> dict:
        checks = {
            "database": "up" if readiness_check(engine) else "down",
            "redis": runtime.redis_status(),
            "vector": store.knowledge_status().get("vector_backend", "disabled"),
        }
        return {"status": "READY" if checks["database"] == "up" else "DEGRADED", "checks": checks}

    @app.post("/api/auth/login")
    def login(request: LoginRequest, response: Response) -> dict:
        username = request.username.strip()
        password = request.password
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        auth_session = store.authenticate_user(username, password)
        if auth_session is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        response.set_cookie(
            key=settings.auth_session_cookie,
            value=auth_session["session_token"],
            max_age=settings.auth_session_ttl_hours * 3600,
            httponly=True,
            samesite="lax",
        )
        return {"user": auth_session["user"], "expires_at": auth_session["expires_at"]}

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        principal: AuthPrincipal = Depends(current_principal),
        session_token: str | None = Cookie(default=None, alias=settings.auth_session_cookie),
    ) -> dict:
        if session_token:
            store.revoke_auth_session(session_token)
        response.delete_cookie(settings.auth_session_cookie)
        return {"ok": True, "user_id": principal.user_id}

    @app.get("/api/auth/me")
    def me(principal: AuthPrincipal = Depends(current_principal)) -> dict:
        return {"user": {"id": principal.user_id, "username": principal.username, "role": principal.role}}

    @app.get("/api/skills")
    def skills() -> dict:
        return {"skills": registry.schemas(), "standard_skills": registry.standard_skill_status()}

    @app.post("/api/chat")
    def chat(request: ChatRequest, principal: AuthPrincipal = Depends(current_principal)) -> dict:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        allowed, remaining = runtime.check_rate_limit(
            f"user:{principal.user_id}:chat",
            settings.chat_rate_limit_per_minute,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="chat rate limit exceeded")
        if request.session_id:
            assert_session_owner(request.session_id, principal)
        outcome = agent_harness.run(message, request.session_id, principal.user_id)
        response = outcome.response
        return asdict(response) | {"rate_limit_remaining": remaining}

    @app.post("/api/chat/stream")
    def chat_stream(request: ChatRequest, principal: AuthPrincipal = Depends(current_principal)) -> StreamingResponse:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        allowed, _ = runtime.check_rate_limit(
            f"user:{principal.user_id}:chat",
            settings.chat_rate_limit_per_minute,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="chat rate limit exceeded")
        if request.session_id:
            assert_session_owner(request.session_id, principal)
        owned_session_id = store.ensure_session(request.session_id, message, owner_user_public_id=principal.user_id)

        def event_stream():
            try:
                for item in agent_harness.stream(message, owned_session_id, principal.user_id)[0]:
                    payload = json.dumps({"event": item.event, **item.data}, ensure_ascii=False)
                    yield f"event: {item.event}\ndata: {payload}\n\n"
            except Exception as exc:
                fallback_response = orchestrator.handle(message, owned_session_id)
                error_payload = json.dumps({"event": "error", "message": str(exc)}, ensure_ascii=False)
                done_payload = json.dumps({"event": "done", "response": asdict(fallback_response)}, ensure_ascii=False)
                yield f"event: error\ndata: {error_payload}\n\n"
                yield f"event: done\ndata: {done_payload}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/sessions")
    def sessions(principal: AuthPrincipal = Depends(current_principal)) -> dict:
        return {"sessions": store.list_sessions(principal.user_id)}

    @app.post("/api/sessions")
    def create_session(request: SessionCreateRequest | None = None, principal: AuthPrincipal = Depends(current_principal)) -> dict:
        session_id = store.ensure_session(None, (request.title if request else "新对话"), owner_user_public_id=principal.user_id)
        session = store.get_session(session_id)
        return {"session": session}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, principal: AuthPrincipal = Depends(current_principal)) -> dict:
        assert_session_owner(session_id, principal)
        return {"session": store.get_session(session_id)}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(session_id: str, request: SessionRenameRequest, principal: AuthPrincipal = Depends(current_principal)) -> dict:
        assert_session_owner(session_id, principal)
        if not store.rename_session(session_id, request.title):
            raise HTTPException(status_code=404, detail="session not found")
        return {"session": store.get_session(session_id)}

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str, principal: AuthPrincipal = Depends(current_principal)) -> dict:
        assert_session_owner(session_id, principal)
        if not store.delete_session(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return {"ok": True}

    @app.get("/api/admin/reports")
    def reports(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"reports": store.list_reports(), "viewer": principal.username}

    @app.patch("/api/admin/reports/{report_id}")
    def update_report(report_id: str, update: ReportUpdate, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        report = store.update_report(report_id, update.status)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        audit(principal, "update_report", "report", report_id, {"status": update.status.value})
        return {"report": report}

    @app.get("/api/admin/traces")
    def traces(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"traces": store.list_traces(), "viewer": principal.username}

    @app.get("/api/admin/cases")
    def cases(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"cases": store.list_cases(), "viewer": principal.username}

    @app.post("/api/admin/cases/{case_id}/notes")
    def add_case_note(case_id: str, request: CaseNoteRequest, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        note = request.note.strip()
        if not note:
            raise HTTPException(status_code=400, detail="note is required")
        case = store.add_case_note(case_id, note, principal.username)
        if case is None:
            raise HTTPException(status_code=404, detail="case not found")
        audit(principal, "add_case_note", "case", case_id, {"note": note})
        return {"case": case}

    @app.patch("/api/admin/cases/{case_id}")
    def update_case(case_id: str, request: CaseStatusUpdate, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        case = store.update_case_status(case_id, request.status)
        if case is None:
            raise HTTPException(status_code=404, detail="case not found")
        audit(principal, "update_case_status", "case", case_id, {"status": request.status.value})
        return {"case": case}

    @app.get("/api/admin/tool-jobs")
    def tool_jobs(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"jobs": store.list_tool_jobs(), "viewer": principal.username}

    @app.get("/api/admin/tool-contracts")
    def tool_contracts(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"contracts": list_tool_contracts(), "viewer": principal.username}

    @app.get("/api/admin/tool-audits")
    def tool_audits(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"audits": store.list_tool_audits(), "viewer": principal.username}

    @app.get("/api/admin/excel-records")
    def excel_records(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"records": store.list_excel_records(), "viewer": principal.username}

    @app.get("/api/admin/alert-records")
    def alert_records(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"records": store.list_alert_records(), "viewer": principal.username}

    @app.get("/api/admin/agent-models")
    def agent_models(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"profiles": store.list_agent_model_profiles(), "viewer": principal.username}

    @app.get("/api/admin/agent-memories")
    def agent_memories(agent: str, session_id: str, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"memories": store.load_agent_private_memory(agent, session_id, 20), "viewer": principal.username}

    @app.post("/api/admin/tool-jobs/run")
    def run_tool_jobs(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        with runtime.lock("tool-jobs-run", settings.redis_lock_timeout_seconds) as acquired:
            if not acquired:
                raise HTTPException(status_code=409, detail="tool jobs are already running")
            result = store.run_pending_tool_jobs()
        audit(principal, "run_tool_jobs", "tool_job_batch", "pending", {"processed": result["processed"]})
        return result

    @app.get("/api/admin/tool-worker/status")
    def tool_worker_status(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {
            "enabled": settings.tool_queue_enabled,
            "mode": "background-worker" if settings.tool_queue_enabled else "manual",
            "poll_interval_seconds": settings.tool_queue_poll_interval_seconds,
            "batch_size": settings.tool_queue_batch_size,
            "worker_threads": settings.tool_queue_worker_threads,
            "viewer": principal.username,
        }

    @app.post("/api/admin/tool-worker/run-once")
    def tool_worker_run_once(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        processed = tool_worker.run_once()
        audit(principal, "tool_worker_run_once", "tool_worker", "background", {"processed": processed})
        return {"processed": processed, "viewer": principal.username}

    @app.post("/api/admin/tool-jobs/{job_id}/retry")
    def retry_tool_job(job_id: str, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        job = store.retry_tool_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="tool job not found")
        audit(principal, "retry_tool_job", "tool_job", job_id)
        return {"job": job}

    @app.get("/api/admin/dead-letters")
    def dead_letters(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"jobs": store.list_dead_letters(), "viewer": principal.username}

    @app.get("/api/admin/knowledge/status")
    def knowledge_status(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return store.knowledge_status() | {"viewer": principal.username}

    @app.get("/api/admin/knowledge/search")
    def search_knowledge(
        q: str,
        top_k: int = 5,
        topic: str = "",
        risk_level: str = "",
        audience: str = "",
        principal: AuthPrincipal = Depends(require_admin),
    ) -> dict:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=400, detail="q is required")
        return {
            "query": query,
            "filters": {"topic": topic, "risk_level": risk_level, "audience": audience},
            "results": store.search_knowledge(
                query,
                max(1, min(top_k, 10)),
                topic=topic or None,
                risk_level=risk_level or None,
                audience=audience or None,
            ),
            "viewer": principal.username,
        }

    @app.post("/api/admin/knowledge")
    def ingest_knowledge(request: KnowledgeIngestRequest, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        source = request.source.strip()
        content = request.content.strip()
        if not source or not content:
            raise HTTPException(status_code=400, detail="source and content are required")
        chunks = store.ingest_knowledge(source, content)
        audit(principal, "ingest_knowledge", "knowledge_source", source, {"chunks": chunks})
        return {"source": source, "chunks": chunks, "status": store.knowledge_status()}

    @app.post("/api/admin/knowledge/rebuild")
    def rebuild_knowledge(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        result = store.rebuild_knowledge_dir(knowledge_dir)
        audit(principal, "rebuild_knowledge", "knowledge_index", "primary", {"chunks": result["chunks"]})
        return result

    @app.post("/api/admin/knowledge/rebuild-vector")
    def rebuild_knowledge_vector(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        result = store.rebuild_vector_index()
        audit(principal, "rebuild_vector_index", "knowledge_index", "vector", result)
        return result

    @app.post("/api/admin/knowledge/backup")
    def backup_knowledge(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        result = store.backup_knowledge_dir(KNOWLEDGE_BACKUP_DIR)
        audit(principal, "backup_knowledge", "knowledge_index", "primary", result)
        return result

    @app.post("/api/admin/knowledge/upload")
    def upload_knowledge(request: KnowledgeUploadRequest, principal: AuthPrincipal = Depends(require_admin)) -> dict:
        filename = safe_knowledge_filename(request.filename)
        content = request.content.strip()
        byte_size = len(content.encode("utf-8"))
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        if byte_size > settings.max_knowledge_upload_bytes:
            raise HTTPException(status_code=413, detail="knowledge file is too large")
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        path = knowledge_dir / filename
        path.write_text(content, encoding="utf-8")
        chunks = store.ingest_knowledge(filename, content)
        audit(principal, "upload_knowledge", "knowledge_source", filename, {"bytes": byte_size, "chunks": chunks})
        return {"source": filename, "bytes": byte_size, "chunks": chunks, "status": store.knowledge_status()}

    @app.post("/api/admin/knowledge/file")
    async def upload_knowledge_file(file: UploadFile = File(...), principal: AuthPrincipal = Depends(require_admin)) -> dict:
        filename = safe_knowledge_filename(file.filename or "")
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="file is required")
        if len(raw) > settings.max_knowledge_upload_bytes:
            raise HTTPException(status_code=413, detail="knowledge file is too large")
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader

                import io

                reader = PdfReader(io.BytesIO(raw))
                content = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"pdf parse failed: {exc}") from exc
        else:
            content = raw.decode("utf-8")
        if not content.strip():
            raise HTTPException(status_code=400, detail="file content is empty")
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        path = knowledge_dir / filename
        path.write_bytes(raw)
        chunks = store.ingest_knowledge(filename, content)
        audit(principal, "upload_knowledge_file", "knowledge_source", filename, {"bytes": len(raw), "chunks": chunks})
        return {"source": filename, "bytes": len(raw), "chunks": chunks, "status": store.knowledge_status()}

    @app.get("/api/admin/eval-results")
    def eval_results(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return latest_evaluation(EVAL_OUTPUT_DIR) | {"viewer": principal.username}

    @app.post("/api/admin/eval-results/run")
    def run_eval_results(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        result = run_evaluation(orchestrator, store, EVAL_FIXTURES_DIR, EVAL_OUTPUT_DIR)
        audit(principal, "run_eval", "evaluation", "latest", {"summary": result.get("summary", {})})
        return result

    @app.get("/api/admin/audit-logs")
    def audit_logs(principal: AuthPrincipal = Depends(require_admin)) -> dict:
        return {"logs": store.list_audit_logs(), "viewer": principal.username}

    return app


def safe_knowledge_filename(filename: str) -> str:
    raw = Path(filename.strip()).name
    if not raw:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(raw).suffix.lower()
    if suffix not in {".md", ".txt", ".pdf"}:
        raise HTTPException(status_code=400, detail="only .md, .txt, and .pdf knowledge files are allowed")
    stem = Path(raw).stem.strip().replace(" ", "-")
    safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in {"-", "_"})
    if not safe_stem:
        raise HTTPException(status_code=400, detail="filename must contain letters or numbers")
    return f"{safe_stem[:80]}{suffix}"


app = create_app()

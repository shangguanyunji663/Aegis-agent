"""管理端路由:报告/个案/工具任务/知识库/评测/审计等后台接口(全部要求 admin 角色)。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.api.deps import audit, require_admin
from app.api.schemas import (
    CaseNoteRequest,
    CaseStatusUpdate,
    KnowledgeIngestRequest,
    KnowledgeUploadRequest,
    ReportUpdate,
)
from app.core.auth import AuthPrincipal
from app.evaluation import latest_evaluation, run_evaluation
from app.tools.contracts import list_tool_contracts

ROOT = Path(__file__).resolve().parents[2]
# 评估测试用例目录
EVAL_FIXTURES_DIR = ROOT / "eval" / "fixtures"
# 评估结果输出目录
EVAL_OUTPUT_DIR = ROOT / "data" / "eval"
# 知识库备份目录
KNOWLEDGE_BACKUP_DIR = ROOT / "data" / "knowledge-backups"

router = APIRouter(prefix="/api/admin")


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


@router.get("/reports")
def reports(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"reports": request.app.state.store.list_reports(), "viewer": principal.username}


@router.patch("/reports/{report_id}")
def update_report(report_id: str, update: ReportUpdate, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    report = store.update_report(report_id, update.status)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    audit(store, principal, "update_report", "report", report_id, {"status": update.status.value})
    return {"report": report}


@router.get("/traces")
def traces(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"traces": request.app.state.store.list_traces(), "viewer": principal.username}


@router.get("/cases")
def cases(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"cases": request.app.state.store.list_cases(), "viewer": principal.username}


@router.post("/cases/{case_id}/notes")
def add_case_note(case_id: str, body: CaseNoteRequest, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    case = store.add_case_note(case_id, note, principal.username)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    audit(store, principal, "add_case_note", "case", case_id, {"note": note})
    return {"case": case}


@router.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseStatusUpdate, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    case = store.update_case_status(case_id, body.status)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    audit(store, principal, "update_case_status", "case", case_id, {"status": body.status.value})
    return {"case": case}


@router.get("/tool-jobs")
def tool_jobs(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"jobs": request.app.state.store.list_tool_jobs(), "viewer": principal.username}


@router.get("/tool-contracts")
def tool_contracts(principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"contracts": list_tool_contracts(), "viewer": principal.username}


@router.get("/tool-audits")
def tool_audits(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"audits": request.app.state.store.list_tool_audits(), "viewer": principal.username}


@router.get("/excel-records")
def excel_records(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"records": request.app.state.store.list_excel_records(), "viewer": principal.username}


@router.get("/alert-records")
def alert_records(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"records": request.app.state.store.list_alert_records(), "viewer": principal.username}


@router.get("/agent-models")
def agent_models(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"profiles": request.app.state.store.list_agent_model_profiles(), "viewer": principal.username}


@router.get("/agent-memories")
def agent_memories(agent: str, session_id: str, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"memories": request.app.state.store.load_agent_private_memory(agent, session_id, 20), "viewer": principal.username}


@router.post("/tool-jobs/run")
def run_tool_jobs(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    store = state.store
    with state.runtime.lock("tool-jobs-run", state.settings.redis_lock_timeout_seconds) as acquired:
        if not acquired:
            raise HTTPException(status_code=409, detail="tool jobs are already running")
        result = store.run_pending_tool_jobs()
    audit(store, principal, "run_tool_jobs", "tool_job_batch", "pending", {"processed": result["processed"]})
    return result


@router.get("/tool-worker/status")
def tool_worker_status(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    settings = request.app.state.settings
    return {
        "enabled": settings.tool_queue_enabled,
        "mode": "background-worker" if settings.tool_queue_enabled else "manual",
        "poll_interval_seconds": settings.tool_queue_poll_interval_seconds,
        "batch_size": settings.tool_queue_batch_size,
        "worker_threads": settings.tool_queue_worker_threads,
        "viewer": principal.username,
    }


@router.post("/tool-worker/run-once")
def tool_worker_run_once(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    processed = state.tool_worker.run_once()
    audit(state.store, principal, "tool_worker_run_once", "tool_worker", "background", {"processed": processed})
    return {"processed": processed, "viewer": principal.username}


@router.post("/tool-jobs/{job_id}/retry")
def retry_tool_job(job_id: str, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    job = store.retry_tool_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="tool job not found")
    audit(store, principal, "retry_tool_job", "tool_job", job_id)
    return {"job": job}


@router.get("/dead-letters")
def dead_letters(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"jobs": request.app.state.store.list_dead_letters(), "viewer": principal.username}


@router.get("/knowledge/status")
def knowledge_status(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return request.app.state.store.knowledge_status() | {"viewer": principal.username}


@router.get("/knowledge/search")
def search_knowledge(
    q: str,
    request: Request,
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
        "results": request.app.state.store.search_knowledge(
            query,
            max(1, min(top_k, 10)),
            topic=topic or None,
            risk_level=risk_level or None,
            audience=audience or None,
        ),
        "viewer": principal.username,
    }


@router.post("/knowledge")
def ingest_knowledge(body: KnowledgeIngestRequest, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    source = body.source.strip()
    content = body.content.strip()
    if not source or not content:
        raise HTTPException(status_code=400, detail="source and content are required")
    chunks = store.ingest_knowledge(source, content)
    audit(store, principal, "ingest_knowledge", "knowledge_source", source, {"chunks": chunks})
    return {"source": source, "chunks": chunks, "status": store.knowledge_status()}


@router.post("/knowledge/rebuild")
def rebuild_knowledge(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    result = state.store.rebuild_knowledge_dir(state.knowledge_dir)
    audit(state.store, principal, "rebuild_knowledge", "knowledge_index", "primary", {"chunks": result["chunks"]})
    return result


@router.post("/knowledge/rebuild-vector")
def rebuild_knowledge_vector(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    result = store.rebuild_vector_index()
    audit(store, principal, "rebuild_vector_index", "knowledge_index", "vector", result)
    return result


@router.post("/knowledge/backup")
def backup_knowledge(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    store = request.app.state.store
    result = store.backup_knowledge_dir(KNOWLEDGE_BACKUP_DIR)
    audit(store, principal, "backup_knowledge", "knowledge_index", "primary", result)
    return result


@router.post("/knowledge/upload")
def upload_knowledge(body: KnowledgeUploadRequest, request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    store = state.store
    settings = state.settings
    knowledge_dir = state.knowledge_dir
    filename = safe_knowledge_filename(body.filename)
    content = body.content.strip()
    byte_size = len(content.encode("utf-8"))
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    if byte_size > settings.max_knowledge_upload_bytes:
        raise HTTPException(status_code=413, detail="knowledge file is too large")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    path = knowledge_dir / filename
    path.write_text(content, encoding="utf-8")
    chunks = store.ingest_knowledge(filename, content)
    audit(store, principal, "upload_knowledge", "knowledge_source", filename, {"bytes": byte_size, "chunks": chunks})
    return {"source": filename, "bytes": byte_size, "chunks": chunks, "status": store.knowledge_status()}


@router.post("/knowledge/file")
async def upload_knowledge_file(request: Request, file: UploadFile = File(...), principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    store = state.store
    settings = state.settings
    knowledge_dir = state.knowledge_dir
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
    audit(store, principal, "upload_knowledge_file", "knowledge_source", filename, {"bytes": len(raw), "chunks": chunks})
    return {"source": filename, "bytes": len(raw), "chunks": chunks, "status": store.knowledge_status()}


@router.get("/eval-results")
def eval_results(principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return latest_evaluation(EVAL_OUTPUT_DIR) | {"viewer": principal.username}


@router.post("/eval-results/run")
def run_eval_results(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    state = request.app.state
    result = run_evaluation(state.orchestrator, state.store, EVAL_FIXTURES_DIR, EVAL_OUTPUT_DIR)
    audit(state.store, principal, "run_eval", "evaluation", "latest", {"summary": result.get("summary", {})})
    return result


@router.get("/audit-logs")
def audit_logs(request: Request, principal: AuthPrincipal = Depends(require_admin)) -> dict:
    return {"logs": request.app.state.store.list_audit_logs(), "viewer": principal.username}

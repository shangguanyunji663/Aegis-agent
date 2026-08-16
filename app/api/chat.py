"""对话与会话路由:聊天、SSE 流式对话、会话 CRUD。"""
from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import assert_session_owner, current_principal
from app.api.schemas import ChatRequest, SessionCreateRequest, SessionRenameRequest
from app.core.auth import AuthPrincipal

router = APIRouter()


@router.post("/api/chat")
def chat(request: ChatRequest, http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    state = http_request.app.state
    settings = state.settings
    store = state.store
    runtime = state.runtime
    agent_harness = state.agent_harness
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
        assert_session_owner(store, request.session_id, principal)
    outcome = agent_harness.run(message, request.session_id, principal.user_id)
    response = outcome.response
    return asdict(response) | {"rate_limit_remaining": remaining}


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest, http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> StreamingResponse:
    state = http_request.app.state
    settings = state.settings
    store = state.store
    runtime = state.runtime
    agent_harness = state.agent_harness
    orchestrator = state.orchestrator
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
        assert_session_owner(store, request.session_id, principal)
    # 预解析归属会话:SSE 异常时的兜底回退路径也需要它
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


@router.get("/api/sessions")
def sessions(http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    return {"sessions": http_request.app.state.store.list_sessions(principal.user_id)}


@router.post("/api/sessions")
def create_session(
    http_request: Request,
    request: SessionCreateRequest | None = None,
    principal: AuthPrincipal = Depends(current_principal),
) -> dict:
    store = http_request.app.state.store
    session_id = store.ensure_session(None, (request.title if request else "新对话"), owner_user_public_id=principal.user_id)
    session = store.get_session(session_id)
    return {"session": session}


@router.get("/api/sessions/{session_id}")
def get_session(session_id: str, http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    store = http_request.app.state.store
    assert_session_owner(store, session_id, principal)
    return {"session": store.get_session(session_id)}


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, request: SessionRenameRequest, http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    store = http_request.app.state.store
    assert_session_owner(store, session_id, principal)
    if not store.rename_session(session_id, request.title):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": store.get_session(session_id)}


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    store = http_request.app.state.store
    assert_session_owner(store, session_id, principal)
    if not store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}

"""认证路由:登录 / 登出 / 当前身份。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import current_principal
from app.api.schemas import LoginRequest
from app.core.auth import AuthPrincipal

router = APIRouter(prefix="/api/auth")


@router.post("/login")
def login(request: LoginRequest, http_request: Request, response: Response) -> dict:
    state = http_request.app.state
    settings = state.settings
    store = state.store
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
        httponly=True,  # Cookie 不能被 JavaScript 读取,防止 XSS 窃取令牌
        samesite="lax",  # Cookie 在跨站请求中不会被发送,防止 CSRF 攻击
    )
    return {"user": auth_session["user"], "expires_at": auth_session["expires_at"]}


@router.post("/logout")
def logout(
    http_request: Request,
    response: Response,
    principal: AuthPrincipal = Depends(current_principal),
) -> dict:
    state = http_request.app.state
    cookie_name = state.settings.auth_session_cookie
    session_token = http_request.cookies.get(cookie_name)
    if session_token:
        state.store.revoke_auth_session(session_token)
    response.delete_cookie(cookie_name)
    return {"ok": True, "user_id": principal.user_id}


@router.get("/me")
def me(principal: AuthPrincipal = Depends(current_principal)) -> dict:
    return {"user": {"id": principal.user_id, "username": principal.username, "role": principal.role}}

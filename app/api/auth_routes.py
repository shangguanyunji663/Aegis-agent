"""认证路由:登录 / 注册 / 登出 / 当前身份。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import current_principal
from app.api.schemas import LoginRequest, RegisterRequest, ThemeRequest
from app.core.auth import AuthPrincipal
from app.models import UserRole

router = APIRouter(prefix="/api/auth")

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff]{2,32}$")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, http_request: Request, response: Response) -> dict:
    state = http_request.app.state
    settings = state.settings
    store = state.store
    username = request.username.strip()
    password = request.password
    if not _USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="用户名需为 2-32 位字母、数字、下划线或中文")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    role = request.role.strip().lower()
    if role not in {UserRole.STUDENT.value, UserRole.TEACHER.value}:
        raise HTTPException(status_code=400, detail="注册角色仅支持 student 或 teacher")
    # 教师角色可进入管理端,必须凭邀请码注册,防止任意人自助获取工作台权限
    if role == UserRole.TEACHER.value and request.invite_code != settings.auth_teacher_invite_code:
        raise HTTPException(status_code=403, detail="教师注册需要正确的邀请码")
    try:
        store.register_user(username, password, role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="用户名已被注册") from exc
    # 注册即登录:直接签发会话并种 Cookie
    auth_session = store.authenticate_user(username, password)
    if auth_session is None:
        raise HTTPException(status_code=500, detail="注册成功但自动登录失败,请手动登录")
    response.set_cookie(
        key=settings.auth_session_cookie,
        value=auth_session["session_token"],
        max_age=settings.auth_session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
    )
    return {"user": auth_session["user"], "expires_at": auth_session["expires_at"]}


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
def me(http_request: Request, principal: AuthPrincipal = Depends(current_principal)) -> dict:
    store = http_request.app.state.store
    theme = store.get_user_theme(principal.user_id)
    return {"user": {"id": principal.user_id, "username": principal.username, "role": principal.role}, "theme": theme}


@router.put("/me/theme")
def update_theme(
    request: ThemeRequest,
    http_request: Request,
    principal: AuthPrincipal = Depends(current_principal),
) -> dict:
    """保存当前用户的界面主题偏好(按用户持久化,跨设备同步)。"""
    store = http_request.app.state.store
    return store.set_user_theme(principal.user_id, request.theme)

"""认证与权限依赖:从应用 state 取仓储,Cookie 会话解析为 AuthPrincipal。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import AuthPrincipal
from app.models import UserRole
from app.repository import DatabaseStore


def get_store(request: Request) -> DatabaseStore:
    return request.app.state.store


def current_principal(request: Request) -> AuthPrincipal:
    store = request.app.state.store
    cookie_name = request.app.state.settings.auth_session_cookie
    session_token = request.cookies.get(cookie_name)
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


def assert_session_owner(store: DatabaseStore, session_id: str, principal: AuthPrincipal) -> None:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session["owner_user_id"] != principal.user_id:
        raise HTTPException(status_code=403, detail="session access denied")


def audit(store: DatabaseStore, principal: AuthPrincipal, action: str, target_type: str, target_id: str, payload: dict | None = None) -> None:
    store.add_audit_log(principal.user_id, principal.username, principal.role, action, target_type, target_id, payload)

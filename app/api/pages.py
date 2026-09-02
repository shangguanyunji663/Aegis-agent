"""前端页面路由:登录页 / 学生端 / 管理端静态 HTML。

页面经 .read_text() 直接返回,无服务端模板渲染。为避免主题切换后的"首屏闪烁",
在此读取当前登录用户已保存的主题偏好,在 <head> 最前注入一段内联脚本设置
html[data-theme] —— 该脚本先于 styles.css 解析执行,首屏即为目标主题。
未登录(登录页)或无偏好记录时回退默认主题 warm。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.repository.store import DEFAULT_THEME

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

router = APIRouter()


def _resolve_theme(request: Request) -> str:
    """软解析当前用户主题:无会话/未登录/无偏好均回退 DEFAULT_THEME,不抛 401。"""
    store = request.app.state.store
    cookie_name = request.app.state.settings.auth_session_cookie
    token = request.cookies.get(cookie_name)
    if not token:
        return DEFAULT_THEME
    session = store.get_auth_session(token)
    if session is None:
        return DEFAULT_THEME
    return store.get_user_theme(session["user"]["id"])


def _render(page_name: str, request: Request) -> str:
    html = (STATIC_DIR / page_name).read_text(encoding="utf-8")
    theme = _resolve_theme(request)
    # theme 取值受 store.THEME_CHOICES 约束,注入安全;脚本先于 CSS 解析,避免闪烁。
    inject = (
        '<script>document.documentElement.setAttribute("data-theme",'
        f'"{theme}");</script>'
    )
    return html.replace("<head>", "<head>" + inject, 1)


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> str:
    return _render("index.html", request)


@router.get("/student", response_class=HTMLResponse)
def student_page(request: Request) -> str:
    return _render("student.html", request)


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request) -> str:
    return _render("admin.html", request)

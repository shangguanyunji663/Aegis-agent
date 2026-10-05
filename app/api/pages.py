"""前端页面路由:托管 Vite 构建产物 frontend/dist(index.html + /assets)。

/, /student, /admin 三个入口都返回同一个 SPA 入口页,页内跳转由 React Router
承接;/assets 与 /favicon.svg 等静态资源由 main.py 挂载的 dist 静态目录提供。
为避免主题切换后的"首屏闪烁",在此读取当前登录用户已保存的主题档位
(light/dark),在 <head> 最前注入内联脚本设置 html[data-theme]——该脚本先于
CSS 解析执行。未登录或无偏好记录时回退 DEFAULT_THEME。

dist 尚未构建时返回可执行的构建指引,而不是 500。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.repository.store import DEFAULT_THEME

ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT / "frontend" / "dist"
INDEX_HTML = DIST_DIR / "index.html"

BUILD_HINT = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<body style="font-family:sans-serif;padding:48px;line-height:2">
<h1>前端尚未构建</h1>
<p>请在 <code>frontend/</code> 目录执行:<code>npm install &amp;&amp; npm run build</code>,然后刷新本页。</p>
</body></html>"""

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


def _render(request: Request) -> str:
    if not INDEX_HTML.exists():
        return BUILD_HINT
    html = INDEX_HTML.read_text(encoding="utf-8")
    theme = _resolve_theme(request)
    # theme 取值受 store.THEME_CHOICES 约束,注入安全;脚本先于 CSS 解析,避免闪烁。
    inject = (
        '<script>document.documentElement.setAttribute("data-theme",'
        f'"{theme}");</script>'
    )
    return html.replace("<head>", "<head>" + inject, 1)


class NoCacheHTMLResponse(HTMLResponse):
    """登录/工作台入口页禁用缓存:前端迭代时 index.html 必须取最新(引用新 hash 资源)。"""

    def __init__(self, content: str, **kwargs):
        super().__init__(content=content, headers={"Cache-Control": "no-cache"}, **kwargs)


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> NoCacheHTMLResponse:
    return NoCacheHTMLResponse(_render(request))


@router.get("/student", response_class=HTMLResponse)
def student_page(request: Request) -> NoCacheHTMLResponse:
    return NoCacheHTMLResponse(_render(request))


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request) -> NoCacheHTMLResponse:
    return NoCacheHTMLResponse(_render(request))

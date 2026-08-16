"""前端页面路由:登录页 / 学生端 / 管理端静态 HTML。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@router.get("/student", response_class=HTMLResponse)
def student_page() -> str:
    return (STATIC_DIR / "student.html").read_text(encoding="utf-8")


@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    return (STATIC_DIR / "admin.html").read_text(encoding="utf-8")

"""API 请求体模型:全部 Pydantic 请求 schema 集中定义。"""
from __future__ import annotations

from pydantic import BaseModel

from app.models import CaseStatus, ReportStatus


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


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "student"
    invite_code: str = ""


class ThemeRequest(BaseModel):
    """前端主题切换请求体:theme 取值见 store.THEME_CHOICES。"""

    theme: str

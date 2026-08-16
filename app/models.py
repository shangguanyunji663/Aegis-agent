from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class Intent(str, Enum):
    COMPANION = "companion"
    COUNSELING = "counseling"
    RISK = "risk"
    RESEARCH = "research"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReportStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


class CaseStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"


class ToolJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    DEAD = "dead"


class UserRole(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class RuntimeEventType(str, Enum):
    RUN_STARTED = "run_started"
    ROUTE_DECIDED = "route_decided"
    RISK_ASSESSED = "risk_assessed"
    KNOWLEDGE_RETRIEVED = "knowledge_retrieved"
    AGENT_STARTED = "agent_started"
    TOOL_REQUESTED = "tool_requested"
    TOOL_COMPLETED = "tool_completed"
    MEMORY_UPDATED = "memory_updated"
    TOKEN_EMITTED = "token_emitted"
    REPORT_CREATED = "report_created"
    SKILLS_SELECTED = "skills_selected"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass
class SkillResult:
    name: str
    output: dict[str, Any]
    side_effect: bool = False


@dataclass
class AgentTrace:
    agent: str
    action: str
    detail: str


@dataclass
class ResponsePlan:
    mode: str
    response_agent: str
    intent: str
    risk_level: str
    memory_brief: str = ""
    knowledge_snippets: list[str] = field(default_factory=list)
    grounding_steps: list[str] = field(default_factory=list)
    skill_context: str = ""
    prompt_messages: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RuntimeEvent:
    type: RuntimeEventType
    data: dict[str, Any]

    @property
    def sse_event(self) -> str:
        mapping = {
            RuntimeEventType.RUN_STARTED: "start",
            RuntimeEventType.ROUTE_DECIDED: "route",
            RuntimeEventType.RISK_ASSESSED: "agent",
            RuntimeEventType.KNOWLEDGE_RETRIEVED: "agent",
            RuntimeEventType.AGENT_STARTED: "agent",
            RuntimeEventType.TOOL_REQUESTED: "skill",
            RuntimeEventType.TOOL_COMPLETED: "skill",
            RuntimeEventType.MEMORY_UPDATED: "agent",
            RuntimeEventType.TOKEN_EMITTED: "token",
            RuntimeEventType.REPORT_CREATED: "report",
            RuntimeEventType.SKILLS_SELECTED: "skill",
            RuntimeEventType.RUN_COMPLETED: "done",
            RuntimeEventType.RUN_FAILED: "error",
        }
        return mapping[self.type]


@dataclass
class PendingReport:
    id: str
    session_id: str
    message: str
    risk_level: RiskLevel
    rationale: list[str]
    intent: Intent = Intent.RISK
    emotion: str = "high_risk"
    emotion_score: float = 4.0
    confidence: float = 0.95
    summary: str = ""
    status: ReportStatus = ReportStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingReport":
        """从仓储层返回的报告字典重建 PendingReport(统一各处重复的转换逻辑)。"""
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            message=data["message"],
            risk_level=RiskLevel(data["risk_level"]),
            rationale=list(data["rationale"]),
            status=ReportStatus(data["status"]),
            created_at=data["created_at"],
        )


@dataclass
class ChatResponse:
    session_id: str
    message_id: str
    intent: Intent
    risk_level: RiskLevel
    answer: str
    skills: list[SkillResult]
    trace: list[AgentTrace]
    pending_report: PendingReport | None = None
    memory_summary: str = ""
    memory_used: bool = False
    response_plan: ResponsePlan | None = None

    @classmethod
    def new_id(cls) -> str:
        return uuid4().hex[:12]


@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any]
    runtime_type: str = ""

    @classmethod
    def from_runtime(cls, runtime_event: RuntimeEvent) -> "StreamEvent":
        return cls(
            event=runtime_event.sse_event,
            data={"runtime_type": runtime_event.type.value, **runtime_event.data},
            runtime_type=runtime_event.type.value,
        )

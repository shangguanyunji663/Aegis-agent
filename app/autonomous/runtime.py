from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.agents.classic import MemoryAgent
from app.autonomous.agents import (
    AutonomousRuntimeServices,
    CompanionAutonomousAgent,
    CounselorAutonomousAgent,
    KnowledgeAutonomousAgent,
    LeadAutonomousAgent,
    MemoryAutonomousAgent,
    RiskGuardianAutonomousAgent,
)
from app.autonomous.board import intent_from_board, risk_from_board
from app.autonomous.coordinator import AutonomousCoordinator
from app.autonomous.events import AgentEvent, AgentEventType, CollaborationBlackboard
from app.autonomous.registry import AutonomousAgentRegistry
from app.models import AgentTrace, Intent, PendingReport, ResponsePlan, RiskLevel, SkillResult


@dataclass
class AutonomousRunOutcome:
    intent: Intent
    risk_level: RiskLevel
    answer: str
    skills: list[SkillResult]
    trace: list[AgentTrace]
    pending_report: PendingReport | None
    memory_summary: str
    memory_used: bool
    board: CollaborationBlackboard
    response_plan: ResponsePlan | None = None


class AutonomousAgentRuntime:
    framework_name = "event_driven_autonomous"

    def __init__(self, store, registry, llm_client, settings, model_registry=None):
        self.store = store
        self.registry = registry
        self.llm_client = llm_client
        self.settings = settings
        self.model_registry = model_registry
        self.last_board: CollaborationBlackboard | None = None

    def run(self, session_id: str, message: str, on_reply_token=None) -> AutonomousRunOutcome:
        services = AutonomousRuntimeServices(
            store=self.store,
            registry=self.registry,
            session_id=session_id,
            llm_client=self.llm_client,
            model_registry=self.model_registry,
            settings=self.settings,
            on_reply_token=on_reply_token,
        )
        agents = [
            MemoryAutonomousAgent(services),
            LeadAutonomousAgent(services),
            RiskGuardianAutonomousAgent(services),
            KnowledgeAutonomousAgent(services),
            CounselorAutonomousAgent(services),
            CompanionAutonomousAgent(services),
        ]
        board = CollaborationBlackboard(
            turn_id=uuid.uuid4().hex,
            session_id=session_id,
            user_input=message,
        ).append_event(
            AgentEvent(
                type=AgentEventType.TURN_STARTED,
                actor="CoordinatorAgent",
                message="user turn published to autonomous blackboard",
            )
        )
        coordinator = AutonomousCoordinator(
            AutonomousAgentRegistry(agents),
            max_rounds=int(self.settings.agent_max_rounds),
            max_claims_per_round=int(self.settings.agent_max_claims_per_round),
            max_claims_per_agent=int(self.settings.agent_max_claims_per_agent),
            final_min_confidence=float(self.settings.agent_final_acceptance_min_confidence),
        )
        board = coordinator.run(board)
        accepted = board.accepted_artifact() or board.latest_artifact("response_proposal")
        answer = str((accepted.payload if accepted else {}).get("answer", "")).strip()
        if not answer:
            answer = "我听到了你的困扰。我们可以先从最具体、最影响你的那一部分开始。"

        self.store.append_message(session_id, "assistant", answer)
        memory_agent = MemoryAgent()
        updated_memory, memory_trace = memory_agent.update(self.store, session_id, message, answer)
        board = board.append_event(
            AgentEvent(
                type=AgentEventType.ARTIFACT_PUBLISHED,
                actor="MemoryAgent",
                message="memory_updated",
                metadata={"covered_message_count": updated_memory.get("covered_message_count", 0)},
            )
        )
        self.last_board = board
        trace = self._trace_from_board(board)
        trace.append(memory_trace)
        return AutonomousRunOutcome(
            intent=intent_from_board(board, use_hard_terms=False),
            risk_level=risk_from_board(board),
            answer=answer,
            skills=self._skills_from_board(board),
            trace=trace,
            pending_report=self._pending_report_from_board(board),
            memory_summary=updated_memory.get("summary", ""),
            memory_used=bool((board.latest_artifact("memory") or _empty_artifact()).payload.get("memory_used", False)),
            board=board,
            response_plan=self._response_plan_from_board(board),
        )

    def _skills_from_board(self, board: CollaborationBlackboard) -> list[SkillResult]:
        skills: list[SkillResult] = []
        risk = board.latest_artifact("risk")
        if risk and isinstance(risk.payload.get("skill"), SkillResult):
            skills.append(risk.payload["skill"])
        context = board.latest_artifact("context")
        if context:
            for item in context.payload.get("skills", []):
                if isinstance(item, SkillResult):
                    skills.append(item)
        report = board.latest_artifact("pending_report")
        if report and isinstance(report.payload.get("skill"), SkillResult):
            skills.append(report.payload["skill"])
        return skills

    def _pending_report_from_board(self, board: CollaborationBlackboard) -> PendingReport | None:
        artifact = board.latest_artifact("pending_report")
        if not artifact:
            return None
        report = artifact.payload.get("report")
        if not report:
            return None
        return PendingReport.from_dict(report)

    def _response_plan_from_board(self, board: CollaborationBlackboard) -> ResponsePlan | None:
        response = board.accepted_artifact() or board.latest_artifact("response_proposal")
        if response is None:
            return None
        plan = response.payload.get("response_plan")
        return plan if isinstance(plan, ResponsePlan) else None

    def _trace_from_board(self, board: CollaborationBlackboard) -> list[AgentTrace]:
        trace = [AgentTrace(event.actor, event.type.value, _event_detail(event)) for event in board.events]
        memory = board.latest_artifact("memory")
        if memory is not None:
            trace.append(
                AgentTrace(
                    "MemoryAgent",
                    "load_memory",
                    f"covered_messages={memory.payload.get('covered_message_count', 0)}",
                )
            )
        if intent_from_board(board, use_hard_terms=False) is Intent.COMPANION and board.latest_artifact("context") is None:
            trace.append(AgentTrace("KnowledgeAgent", "skip_knowledge", "intent=companion; chat-style turns do not retrieve RAG"))
        response = board.accepted_artifact() or board.latest_artifact("response_proposal")
        if response is not None:
            if response.payload.get("plan_trace"):
                trace.append(
                    AgentTrace(
                        str(response.payload.get("agent", response.owner)),
                        "compose_plan",
                        str(response.payload.get("plan_trace")),
                    )
                )
            trace.append(
                AgentTrace(
                    str(response.payload.get("agent", response.owner)),
                    "compose_answer",
                    str(response.payload.get("trace", "autonomous_response_proposal")),
                )
            )
        context = board.latest_artifact("context")
        if context:
            standard_skills = context.payload.get("standard_skills", [])
            trace.append(AgentTrace("SkillRegistry", "select_standard_skills", ",".join(standard_skills) or "none"))
        return trace


def _event_detail(event: AgentEvent) -> str:
    if event.artifact_id:
        return f"{event.message}; artifact={event.artifact_id}" if event.message else f"artifact={event.artifact_id}"
    if event.message:
        return event.message
    if event.metadata:
        return str(event.metadata)[:240]
    return ""


def _empty_artifact():
    class Empty:
        payload: dict[str, Any] = {}

    return Empty()

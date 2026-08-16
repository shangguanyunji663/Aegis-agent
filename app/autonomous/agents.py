from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.agents.classic import CounselorAgent, KnowledgeAgent, LeadAgent, MemoryAgent, RiskGuardianAgent
from app.autonomous.board import hard_high_risk, intent_from_board, risk_from_board
from app.autonomous.events import (
    AgentArtifact,
    AgentEvent,
    AgentEventType,
    AgentMessage,
    AgentTask,
    AgentTurnResult,
    CollaborationBlackboard,
    TaskPriority,
)
from app.autonomous.registry import AgentCapability, AgentDecision, AgentProfile
from app.models import Intent, RiskLevel, SkillResult
from app.core.privacy import contains_internal_response_leak
from app.skills import SkillRegistry


@dataclass
class AutonomousRuntimeServices:
    store: Any
    registry: SkillRegistry
    session_id: str
    llm_client: Any
    model_registry: Any


class BaseAutonomousAgent:
    profile: AgentProfile

    def __init__(self, services: AutonomousRuntimeServices):
        self.services = services

    @property
    def name(self) -> str:
        return self.profile.name

    def _artifact(
        self,
        kind: str,
        payload: dict[str, Any],
        task: AgentTask,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> AgentArtifact:
        return AgentArtifact(
            id=f"{self.name}:{kind}:{uuid.uuid4().hex[:10]}",
            owner=self.name,
            kind=kind,
            payload=payload,
            confidence=confidence,
            task_id=task.id,
            metadata=metadata or {},
        )

    def _message(self, recipient: str, task: AgentTask, kind: str, content: str) -> AgentMessage:
        return AgentMessage(
            id=f"msg:{uuid.uuid4().hex[:10]}",
            sender=self.name,
            recipient=recipient,
            task_id=task.id,
            kind=kind,
            content=content,
        )

    def client(self):
        return self.services.model_registry.client_for(self.name)

    def private_memory(self, limit: int = 8) -> list[dict]:
        return self.services.store.load_agent_private_memory(self.name, self.services.session_id, limit)

    def remember(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.services.store.append_agent_private_memory(self.name, self.services.session_id, content, metadata or {})


class MemoryAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="MemoryAgent",
        capabilities=frozenset({AgentCapability.MEMORY}),
        system_prompt="Load and later update session memory; do not diagnose.",
        memory_policy="session_summary",
        tool_permissions=frozenset({"memory.read", "memory.write"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.agent = MemoryAgent()

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if board.latest_artifact("memory"):
            return AgentDecision(False, reason="memory already loaded")
        if AgentCapability.MEMORY.value in task.required_capabilities:
            return AgentDecision(True, 0.94, "memory artifact required")
        return AgentDecision(False, reason="task does not require memory")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        memory, _ = self.agent.load(self.services.store, self.services.session_id)
        summary = memory.get("summary", "")
        payload = {
            "summary": summary,
            "covered_message_count": memory.get("covered_message_count", 0),
            "memory_used": bool(summary),
            "private_memory": self.private_memory(),
        }
        self.remember(f"loaded session memory; used={bool(summary)}", {"covered_message_count": payload["covered_message_count"]})
        return AgentTurnResult(
            artifacts=(self._artifact("memory", payload, task, 0.9),),
            messages=(self._message("*", task, "MEMORY_READY", f"memory_used={bool(summary)}"),),
        )


class LeadAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="LeadAgent",
        capabilities=frozenset({AgentCapability.UNDERSTANDING}),
        system_prompt="Classify user intent and publish a route proposal.",
        memory_policy="route_history",
        tool_permissions=frozenset({"route.intent"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.agent = LeadAgent()

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if board.latest_artifact("intent"):
            return AgentDecision(False, reason="intent already exists")
        if AgentCapability.UNDERSTANDING.value in task.required_capabilities:
            return AgentDecision(True, 0.86, "user turn needs intent routing")
        return AgentDecision(False, reason="task does not need routing")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        risk = risk_from_board(board)
        intent, trace = self.agent.route(board.user_input, risk)
        if risk is RiskLevel.HIGH:
            intent = Intent.RISK
        payload = {"intent": intent.value, "risk_hint": risk.value, "reason": trace.detail}
        self.remember(f"intent={intent.value}; risk_hint={risk.value}", {"task_id": task.id})
        return AgentTurnResult(
            artifacts=(self._artifact("intent", payload, task, 0.84),),
            messages=(self._message("*", task, "ROUTE_PROPOSAL", f"intent={intent.value}"),),
        )


class RiskGuardianAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="RiskGuardianAgent",
        capabilities=frozenset({AgentCapability.SAFETY}),
        system_prompt="Assess risk independently and review response safety before final acceptance.",
        memory_policy="safety_ledger",
        tool_permissions=frozenset({"assess_risk", "create_pending_report", "response.review"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.agent = RiskGuardianAgent(services.registry)

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        response = board.latest_artifact("response_proposal")
        review = board.latest_artifact("safety_review")
        if response and (review is None or review.metadata.get("responseArtifactId") != response.id):
            return AgentDecision(True, 0.97, "candidate response needs independent safety review")
        if not board.latest_artifact("risk") and AgentCapability.SAFETY.value in task.required_capabilities:
            confidence = 0.98 if hard_high_risk(board.user_input) else 0.88
            return AgentDecision(True, confidence, "user input needs risk assessment")
        return AgentDecision(False, reason="no safety work needed")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        response = board.latest_artifact("response_proposal")
        review = board.latest_artifact("safety_review")
        if response and (review is None or review.metadata.get("responseArtifactId") != response.id):
            return self._review_response(task, board, response)
        return self._assess(task, board)

    def _assess(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        risk_skill, risk_level, trace = self.agent.assess(board.user_input)
        payload = {"risk_level": risk_level.value, "skill": risk_skill, "trace": trace.detail, **risk_skill.output}
        self.remember(f"risk={risk_level.value}; summary={risk_skill.output.get('summary', '')}", {"task_id": task.id})
        artifacts = [self._artifact("risk", payload, task, float(risk_skill.output.get("confidence", 0.8)))]
        events: list[AgentEvent] = []
        messages = [self._message("CoordinatorAgent", task, "SAFETY_ASSESSMENT", f"risk={risk_level.value}")]
        if risk_level is RiskLevel.HIGH:
            report_result, report_trace = self.agent.create_report(board.user_input, self.services.session_id, risk_level, Intent.RISK, risk_skill)
            report = next((item for item in self.services.store.list_reports() if item["id"] == report_result.output["report_id"]), None)
            artifacts.append(
                self._artifact(
                    "pending_report",
                    {"skill": report_result, "report": report, "trace": report_trace.detail},
                    task,
                    0.95,
                )
            )
            events.append(
                AgentEvent(
                    type=AgentEventType.SAFETY_OVERRIDE,
                    actor=self.name,
                    task_id=task.id,
                    message="risk assessed as HIGH and pending report created",
                    metadata={"risk_level": risk_level.value, "report_id": report_result.output["report_id"]},
                )
            )
        return AgentTurnResult(artifacts=tuple(artifacts), messages=tuple(messages), events=tuple(events))

    def _review_response(self, task: AgentTask, board: CollaborationBlackboard, response: AgentArtifact) -> AgentTurnResult:
        risk = risk_from_board(board)
        answer = str(response.payload.get("answer", ""))
        approved = True
        reason = "response proposal satisfies safety constraints"
        if contains_internal_response_leak(answer):
            approved = False
            reason = "response leaks internal implementation or report details"
        if risk is RiskLevel.HIGH and not any(term in answer for term in ["安全", "可信任的人", "紧急", "学校心理中心"]):
            approved = False
            reason = "high-risk response lacks immediate safety guidance"
        payload = {"approved": approved, "reason": reason, "risk_level": risk.value, "responseArtifactId": response.id}
        self.remember(f"review approved={approved}; reason={reason}", {"response_artifact_id": response.id})
        kind = "safety_review" if approved else "critique"
        events = []
        follow_ups = []
        if not approved:
            events.append(
                AgentEvent(
                    type=AgentEventType.REVISION_REQUESTED,
                    actor=self.name,
                    task_id=task.id,
                    artifact_id=response.id,
                    message=reason,
                )
            )
            follow_ups.append(
                AgentTask(
                    id=f"task:revise-response:{uuid.uuid4().hex[:8]}",
                    title="Revise unsafe response proposal",
                    description=reason,
                    priority=TaskPriority.CRITICAL,
                    required_capabilities=frozenset({AgentCapability.RESPONSE.value}),
                    created_by=self.name,
                    metadata={"kind": "response", "revisionOf": response.id},
                )
            )
        return AgentTurnResult(
            artifacts=(self._artifact(kind, payload, task, 0.95, {"responseArtifactId": response.id}),),
            tasks=tuple(follow_ups),
            events=tuple(events),
        )


class KnowledgeAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="KnowledgeAgent",
        capabilities=frozenset({AgentCapability.CONTEXT}),
        system_prompt="Gather memory, knowledge, grounding, and Skill constraints for support responses.",
        memory_policy="context_cache",
        tool_permissions=frozenset({"search_knowledge", "grounding_exercise", "skills.read"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.knowledge_agent = KnowledgeAgent(services.registry, services.model_registry.client_for(self.name))
        self.counselor_agent = CounselorAgent(services.registry, services.model_registry.client_for("CounselorAgent"))

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if board.latest_artifact("context"):
            return AgentDecision(False, reason="context already exists")
        if AgentCapability.CONTEXT.value in task.required_capabilities:
            return AgentDecision(True, 0.84, "support path needs memory/RAG/Skill context")
        return AgentDecision(False, reason="task does not require context")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        intent = intent_from_board(board)
        risk = risk_from_board(board)
        memory_artifact = board.latest_artifact("memory")
        memory_summary = str((memory_artifact.payload if memory_artifact else {}).get("summary", ""))
        knowledge = None
        grounding = None
        skills: list[SkillResult] = []
        if intent is not Intent.COMPANION or risk is not RiskLevel.LOW:
            knowledge, _ = self.knowledge_agent.search(board.user_input, memory_summary)
            skills.append(knowledge)
        if risk in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
            grounding, _ = self.counselor_agent.grounding(board.user_input)
            skills.append(grounding)
        standard_skills = self.services.registry.response_skill_names(intent, risk, board.user_input)
        standard_context = self.services.registry.standard_context(standard_skills)
        payload = {
            "memory_summary": memory_summary,
            "knowledge": knowledge,
            "grounding": grounding,
            "skills": skills,
            "standard_skills": standard_skills,
            "standard_context": standard_context,
            "private_memory": self.private_memory(),
        }
        self.remember(
            f"context intent={intent.value}; risk={risk.value}; skills={','.join(standard_skills) or 'none'}",
            {"retrieved": len(knowledge.output.get("documents", [])) if knowledge else 0},
        )
        return AgentTurnResult(
            artifacts=(self._artifact("context", payload, task, 0.88),),
            messages=(self._message("CounselorAgent", task, "CONTEXT_READY", f"retrieved={len(knowledge.output.get('documents', [])) if knowledge else 0}"),),
        )


class CounselorAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="CounselorAgent",
        capabilities=frozenset({AgentCapability.RESPONSE}),
        system_prompt="Propose psychological support responses for counseling, research, and risk turns.",
        memory_policy="response_strategy",
        tool_permissions=frozenset({"llm.reply", "safety_template"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.agent = CounselorAgent(services.registry, services.model_registry.client_for(self.name))

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if board.latest_artifact("response_proposal") and "revisionOf" not in task.metadata:
            return AgentDecision(False, reason="response proposal already exists")
        intent = intent_from_board(board)
        risk = risk_from_board(board)
        if intent is Intent.COMPANION and risk is RiskLevel.LOW:
            return AgentDecision(False, reason="companion path belongs to CompanionAgent")
        if AgentCapability.RESPONSE.value in task.required_capabilities:
            return AgentDecision(True, 0.86, "support response proposal needed")
        return AgentDecision(False, reason="task does not require support response")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        intent = intent_from_board(board)
        risk = risk_from_board(board)
        context = (board.latest_artifact("context").payload if board.latest_artifact("context") else {})
        response_plan, plan_trace = self.agent.compose_plan(
            board.user_input,
            intent,
            risk,
            context.get("memory_summary", ""),
            context.get("knowledge"),
            context.get("grounding"),
            context.get("standard_context", ""),
        )
        answer, trace = self.agent.finalize_plan(response_plan)
        payload = {
            "answer": answer,
            "trace": trace.detail,
            "plan_trace": plan_trace.detail,
            "response_plan": response_plan,
            "agent": self.name,
            "intent": intent.value,
            "risk_level": risk.value,
        }
        self.remember(f"response intent={intent.value}; risk={risk.value}; plan={response_plan.mode}; trace={trace.detail}", {"task_id": task.id})
        return AgentTurnResult(
            artifacts=(self._artifact("response_proposal", payload, task, 0.86),),
            messages=(self._message("RiskGuardianAgent", task, "REVIEW_REQUEST", "please review candidate response"),),
        )


class CompanionAutonomousAgent(BaseAutonomousAgent):
    profile = AgentProfile(
        name="CompanionAgent",
        capabilities=frozenset({AgentCapability.RESPONSE}),
        system_prompt="Propose direct companion responses for low-risk chat turns.",
        memory_policy="companion_style",
        tool_permissions=frozenset({"companion.reply"}),
    )

    def __init__(self, services: AutonomousRuntimeServices):
        super().__init__(services)
        self.counselor_agent = CounselorAgent(services.registry, services.model_registry.client_for(self.name))

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if board.latest_artifact("response_proposal") and "revisionOf" not in task.metadata:
            return AgentDecision(False, reason="response proposal already exists")
        if AgentCapability.RESPONSE.value not in task.required_capabilities:
            return AgentDecision(False, reason="task is not a response task")
        if intent_from_board(board) is Intent.COMPANION and risk_from_board(board) is RiskLevel.LOW:
            return AgentDecision(True, 0.82, "low-risk companion response needed")
        return AgentDecision(False, reason="not a companion response")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        memory_artifact = board.latest_artifact("memory")
        memory_summary = str((memory_artifact.payload if memory_artifact else {}).get("summary", ""))
        response_plan, plan_trace = self.counselor_agent.compose_plan(
            board.user_input,
            Intent.COMPANION,
            RiskLevel.LOW,
            memory_summary,
            None,
            None,
            "",
        )
        response_plan.response_agent = self.name
        answer, trace = self.counselor_agent.finalize_plan(response_plan)
        payload = {
            "answer": answer,
            "trace": trace.detail,
            "plan_trace": plan_trace.detail,
            "response_plan": response_plan,
            "agent": self.name,
            "intent": Intent.COMPANION.value,
            "risk_level": RiskLevel.LOW.value,
        }
        self.remember(f"companion response proposed; plan={response_plan.mode}", {"task_id": task.id})
        return AgentTurnResult(
            artifacts=(self._artifact("response_proposal", payload, task, 0.82),),
            messages=(self._message("RiskGuardianAgent", task, "REVIEW_REQUEST", "please review companion response"),),
        )

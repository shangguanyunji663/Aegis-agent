from __future__ import annotations

from collections import defaultdict

from app.autonomous_events import (
    AgentEvent,
    AgentEventType,
    AgentTask,
    CollaborationBlackboard,
    PRIORITY_ORDER,
    TaskPriority,
)
from app.autonomous_registry import AgentCapability, AutonomousAgentRegistry
from app.models import Intent, RiskLevel


class AutonomousCoordinator:
    name = "CoordinatorAgent"

    def __init__(
        self,
        registry: AutonomousAgentRegistry,
        max_rounds: int = 8,
        max_claims_per_round: int = 4,
        max_claims_per_agent: int = 3,
        final_min_confidence: float = 0.6,
    ):
        self.registry = registry
        self.max_rounds = max_rounds
        self.max_claims_per_round = max_claims_per_round
        self.max_claims_per_agent = max_claims_per_agent
        self.final_min_confidence = final_min_confidence

    def run(self, board: CollaborationBlackboard) -> CollaborationBlackboard:
        board = self._ensure_root_task(board)
        claim_counts: dict[str, int] = defaultdict(int)
        for round_number in range(1, self.max_rounds + 1):
            board = board.append_event(
                AgentEvent(
                    type=AgentEventType.ROUND_STARTED,
                    actor=self.name,
                    message=f"round={round_number}",
                    metadata={"round": round_number},
                )
            )
            board = self._derive_missing_work(board)
            board = self._try_accept_final(board)
            if board.final_artifact_id:
                return board
            candidates = self._claim_candidates(board, claim_counts)
            if not candidates:
                board = self._derive_missing_work(board, force_response=True)
                candidates = self._claim_candidates(board, claim_counts)
                if not candidates:
                    break
            for task, candidate in candidates:
                current_task = board.tasks.get(task.id, task)
                board = board.update_task(current_task.claim(candidate.agent.profile.name)).append_event(
                    AgentEvent(
                        type=AgentEventType.TASK_CLAIMED,
                        actor=candidate.agent.profile.name,
                        task_id=current_task.id,
                        message=candidate.decision.reason,
                        metadata={"confidence": candidate.decision.confidence},
                    )
                )
                result = candidate.agent.act(current_task, board)
                board = board.apply_turn_result(current_task, candidate.agent.profile.name, result)
                claim_counts[candidate.agent.profile.name] += 1
            board = self._derive_missing_work(board)
            board = self._try_accept_final(board)
            if board.final_artifact_id:
                return board
        return board.append_event(
            AgentEvent(
                type=AgentEventType.BUDGET_EXHAUSTED,
                actor=self.name,
                message="autonomous agent budget exhausted before final acceptance",
            )
        )

    def _ensure_root_task(self, board: CollaborationBlackboard) -> CollaborationBlackboard:
        if board.tasks:
            return board
        root = AgentTask(
            id="task:root",
            title="Resolve user turn",
            description=board.user_input,
            priority=TaskPriority.CRITICAL if _hard_high_risk(board.user_input) else TaskPriority.NORMAL,
            created_by=self.name,
            metadata={"kind": "root"},
        )
        return board.add_task(root).append_event(
            AgentEvent(type=AgentEventType.TASK_CREATED, actor=self.name, task_id=root.id, message=root.title)
        )

    def _derive_missing_work(self, board: CollaborationBlackboard, force_response: bool = False) -> CollaborationBlackboard:
        board = self._ensure_task_for_missing_artifact(
            board,
            "memory",
            "task:load-memory",
            "Load session memory",
            AgentCapability.MEMORY,
            TaskPriority.HIGH,
            board.user_input != "",
        )
        board = self._ensure_task_for_missing_artifact(
            board,
            "intent",
            "task:understand",
            "Understand and route user turn",
            AgentCapability.UNDERSTANDING,
            TaskPriority.HIGH,
            board.user_input != "",
        )
        board = self._ensure_task_for_missing_artifact(
            board,
            "risk",
            "task:assess-safety",
            "Assess safety risk",
            AgentCapability.SAFETY,
            TaskPriority.CRITICAL if _hard_high_risk(board.user_input) else TaskPriority.HIGH,
            board.user_input != "",
        )
        intent = _intent_value(board)
        risk = _risk_value(board)
        needs_context = intent in {Intent.COUNSELING, Intent.RESEARCH, Intent.RISK} or risk in {RiskLevel.MEDIUM, RiskLevel.HIGH}
        board = self._ensure_task_for_missing_artifact(
            board,
            "context",
            "task:gather-context",
            "Gather memory, RAG, and standard Skill context",
            AgentCapability.CONTEXT,
            TaskPriority.CRITICAL if risk == RiskLevel.HIGH else TaskPriority.NORMAL,
            needs_context,
        )
        has_response = board.latest_artifact("response_proposal") is not None
        can_request_response = force_response or (
            board.latest_artifact("intent") is not None
            and board.latest_artifact("risk") is not None
            and (not needs_context or board.latest_artifact("context") is not None or risk == RiskLevel.HIGH)
        )
        board = self._ensure_task_for_missing_artifact(
            board,
            "response_proposal",
            "task:propose-response",
            "Propose candidate response",
            AgentCapability.RESPONSE,
            TaskPriority.CRITICAL if risk == RiskLevel.HIGH else TaskPriority.HIGH,
            can_request_response and not has_response,
        )
        response = board.latest_artifact("response_proposal")
        review = board.latest_artifact("safety_review")
        critique = board.latest_artifact("critique")
        if response and (review is None or review.metadata.get("responseArtifactId") != response.id):
            board = self._ensure_task(
                board,
                AgentTask(
                    id=f"task:review-response:{response.id}",
                    title="Review candidate response safety",
                    description="Safety review is required before final acceptance.",
                    priority=TaskPriority.CRITICAL if risk == RiskLevel.HIGH else TaskPriority.HIGH,
                    required_capabilities=frozenset({AgentCapability.SAFETY.value}),
                    created_by=self.name,
                    metadata={"kind": "safety_review", "responseArtifactId": response.id},
                ),
            )
        if critique and critique.payload.get("approved") is False:
            board = self._ensure_task(
                board,
                AgentTask(
                    id=f"task:revise-response:{critique.id}",
                    title="Revise response after critique",
                    description=str(critique.payload.get("reason", "Safety critique requested revision.")),
                    priority=TaskPriority.CRITICAL,
                    required_capabilities=frozenset({AgentCapability.RESPONSE.value}),
                    created_by=self.name,
                    metadata={"kind": "response", "revisionOf": critique.payload.get("responseArtifactId", "")},
                ),
            )
        return board

    def _ensure_task_for_missing_artifact(
        self,
        board: CollaborationBlackboard,
        artifact_kind: str,
        task_id: str,
        title: str,
        capability: AgentCapability,
        priority: TaskPriority,
        condition: bool,
    ) -> CollaborationBlackboard:
        if not condition or board.latest_artifact(artifact_kind) is not None:
            return board
        return self._ensure_task(
            board,
            AgentTask(
                id=task_id,
                title=title,
                description=board.user_input,
                priority=priority,
                required_capabilities=frozenset({capability.value}),
                created_by=self.name,
                metadata={"kind": artifact_kind},
            ),
        )

    def _ensure_task(self, board: CollaborationBlackboard, task: AgentTask) -> CollaborationBlackboard:
        if task.id in board.tasks:
            return board
        return board.add_task(task).append_event(
            AgentEvent(type=AgentEventType.TASK_CREATED, actor=self.name, task_id=task.id, message=task.title)
        )

    def _claim_candidates(self, board: CollaborationBlackboard, claim_counts: dict[str, int]):
        task_candidates = []
        for task in board.open_tasks():
            for candidate in self.registry.candidate_decisions_for(task, board):
                if claim_counts[candidate.agent.profile.name] >= self.max_claims_per_agent:
                    continue
                task_candidates.append((task, candidate))
        task_candidates.sort(
            key=lambda item: (
                PRIORITY_ORDER[item[0].priority],
                item[1].decision.confidence,
                item[1].agent.profile.name,
            ),
            reverse=True,
        )
        selected = []
        seen = set()
        selected_agents = set()
        for task, candidate in task_candidates:
            key = (task.id, candidate.agent.profile.name)
            if key in seen or candidate.agent.profile.name in selected_agents:
                continue
            selected.append((task, candidate))
            seen.add(key)
            selected_agents.add(candidate.agent.profile.name)
            if len(selected) >= self.max_claims_per_round:
                break
        return selected

    def _try_accept_final(self, board: CollaborationBlackboard) -> CollaborationBlackboard:
        if board.final_artifact_id:
            return board
        response = board.latest_artifact("response_proposal")
        review = board.latest_artifact("safety_review")
        if response is None or review is None:
            return board
        if review.metadata.get("responseArtifactId") != response.id:
            return board
        if not review.payload.get("approved"):
            return board
        if response.confidence < self.final_min_confidence:
            return board
        return board.accept_final(response.id, self.name, "accepted after autonomous proposal and SafetyAgent approval")


def _hard_high_risk(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in ["自杀", "轻生", "不想活", "结束生命", "suicide", "kill myself"])


def _intent_value(board: CollaborationBlackboard) -> Intent:
    artifact = board.latest_artifact("intent")
    if artifact:
        try:
            return Intent(str(artifact.payload.get("intent", Intent.COMPANION.value)))
        except ValueError:
            return Intent.COMPANION
    return Intent.RISK if _hard_high_risk(board.user_input) else Intent.COMPANION


def _risk_value(board: CollaborationBlackboard) -> RiskLevel:
    highest = RiskLevel.LOW
    order = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
    for artifact in board.artifacts_by_kind("risk"):
        try:
            risk = RiskLevel(str(artifact.payload.get("risk_level", RiskLevel.LOW.value)))
        except ValueError:
            risk = RiskLevel.LOW
        if order[risk] > order[highest]:
            highest = risk
    if any(event.type == AgentEventType.SAFETY_OVERRIDE for event in board.events):
        return RiskLevel.HIGH
    return highest

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.autonomous_events import AgentTask, AgentTurnResult, CollaborationBlackboard


class AgentCapability(str, Enum):
    MEMORY = "MEMORY"
    UNDERSTANDING = "UNDERSTANDING"
    SAFETY = "SAFETY"
    CONTEXT = "CONTEXT"
    RESPONSE = "RESPONSE"


@dataclass(frozen=True)
class AgentProfile:
    name: str
    capabilities: frozenset[AgentCapability] = field(default_factory=frozenset)
    system_prompt: str = ""
    memory_policy: str = "none"
    model_profile: str = "default"
    tool_permissions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AgentDecision:
    claim: bool
    confidence: float = 0.0
    reason: str = ""


class AutonomousAgent(Protocol):
    profile: AgentProfile

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        ...

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        ...


@dataclass(frozen=True)
class AgentCandidate:
    agent: AutonomousAgent
    decision: AgentDecision


class AutonomousAgentRegistry:
    def __init__(self, agents: list[AutonomousAgent]):
        self._agents = list(agents)

    @property
    def agents(self) -> list[AutonomousAgent]:
        return list(self._agents)

    def candidate_decisions_for(self, task: AgentTask, board: CollaborationBlackboard) -> list[AgentCandidate]:
        candidates = []
        for agent in self._agents:
            if not self._has_required_capability(agent, task):
                continue
            decision = agent.decide(task, board)
            if decision.claim:
                candidates.append(AgentCandidate(agent, decision))
        return sorted(candidates, key=lambda item: item.decision.confidence, reverse=True)

    def _has_required_capability(self, agent: AutonomousAgent, task: AgentTask) -> bool:
        if not task.required_capabilities:
            return True
        agent_capabilities = {capability.value for capability in agent.profile.capabilities}
        return set(task.required_capabilities).issubset(agent_capabilities)

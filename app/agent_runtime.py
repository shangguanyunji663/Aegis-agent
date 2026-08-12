from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.models import RuntimeEvent, RuntimeEventType


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, agent_id: str, agent: Any) -> None:
        if not agent_id:
            raise ValueError("agent_id is required")
        self._agents[agent_id] = agent

    def get(self, agent_id: str) -> Any:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"agent not registered: {agent_id}") from exc

    def list_ids(self) -> list[str]:
        return sorted(self._agents)


@dataclass(frozen=True)
class AgentRuntimeStep:
    agent_id: str
    action: str


class AgentRuntimeRunner:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.event_history: list[RuntimeEvent] = []

    def reset(self) -> None:
        self.event_history = []

    def run_step(self, agent_id: str, action: str, call: Callable[[Any], Any]) -> Any:
        agent = self.registry.get(agent_id)
        step = AgentRuntimeStep(agent_id=agent_id, action=action)
        self._record(RuntimeEventType.AGENT_STARTED, {"agent_id": step.agent_id, "action": step.action})
        try:
            return call(agent)
        except Exception as exc:
            self._record(
                RuntimeEventType.RUN_FAILED,
                {"agent_id": step.agent_id, "action": step.action, "error": str(exc)},
            )
            raise

    def run_plan(self, plan: list[tuple[str, str, Callable[[Any], Any]]]) -> list[Any]:
        results = []
        for agent_id, action, call in plan:
            results.append(self.run_step(agent_id, action, call))
        return results

    def _record(self, event_type: RuntimeEventType, data: dict[str, Any]) -> None:
        self.event_history.append(RuntimeEvent(type=event_type, data=data))

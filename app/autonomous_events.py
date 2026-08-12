from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class AgentEventType(str, Enum):
    TURN_STARTED = "TURN_STARTED"
    ROUND_STARTED = "ROUND_STARTED"
    TASK_CREATED = "TASK_CREATED"
    TASK_CLAIMED = "TASK_CLAIMED"
    TASK_CLOSED = "TASK_CLOSED"
    TASK_REOPENED = "TASK_REOPENED"
    MESSAGE_SENT = "MESSAGE_SENT"
    ARTIFACT_PUBLISHED = "ARTIFACT_PUBLISHED"
    CRITIQUE_PUBLISHED = "CRITIQUE_PUBLISHED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    SAFETY_OVERRIDE = "SAFETY_OVERRIDE"
    FINAL_ACCEPTED = "FINAL_ACCEPTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    CLAIMED = "CLAIMED"
    CLOSED = "CLOSED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


PRIORITY_ORDER = {
    TaskPriority.LOW: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.HIGH: 3,
    TaskPriority.CRITICAL: 4,
}


@dataclass(frozen=True)
class AgentTask:
    id: str
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.OPEN
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    created_by: str = "CoordinatorAgent"
    claimed_by: tuple[str, ...] = field(default_factory=tuple)
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def claim(self, agent_name: str) -> "AgentTask":
        if agent_name in self.claimed_by:
            return self
        return replace(self, status=TaskStatus.CLAIMED, claimed_by=(*self.claimed_by, agent_name))

    def close(self) -> "AgentTask":
        return replace(self, status=TaskStatus.CLOSED)

    def reopen(self) -> "AgentTask":
        return replace(self, status=TaskStatus.OPEN)


@dataclass(frozen=True)
class AgentClaim:
    agent: str
    task_id: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class AgentMessage:
    id: str
    sender: str
    recipient: str
    content: str
    task_id: str = ""
    kind: str = "REQUEST"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentArtifact:
    id: str
    owner: str
    kind: str
    payload: dict[str, Any]
    confidence: float = 1.0
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentEvent:
    type: AgentEventType
    actor: str
    task_id: str = ""
    artifact_id: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentTurnResult:
    messages: tuple[AgentMessage, ...] = field(default_factory=tuple)
    artifacts: tuple[AgentArtifact, ...] = field(default_factory=tuple)
    tasks: tuple[AgentTask, ...] = field(default_factory=tuple)
    events: tuple[AgentEvent, ...] = field(default_factory=tuple)
    close_task: bool = True


@dataclass(frozen=True)
class CollaborationBlackboard:
    turn_id: str
    session_id: str
    user_input: str
    tasks: dict[str, AgentTask] = field(default_factory=dict)
    messages: tuple[AgentMessage, ...] = field(default_factory=tuple)
    artifacts: tuple[AgentArtifact, ...] = field(default_factory=tuple)
    events: tuple[AgentEvent, ...] = field(default_factory=tuple)
    final_artifact_id: str = ""

    def add_task(self, task: AgentTask) -> "CollaborationBlackboard":
        tasks = dict(self.tasks)
        tasks[task.id] = task
        return replace(self, tasks=tasks)

    def update_task(self, task: AgentTask) -> "CollaborationBlackboard":
        return self.add_task(task)

    def append_event(self, event: AgentEvent) -> "CollaborationBlackboard":
        return replace(self, events=(*self.events, event))

    def send_message(self, message: AgentMessage) -> "CollaborationBlackboard":
        return replace(self, messages=(*self.messages, message)).append_event(
            AgentEvent(
                type=AgentEventType.MESSAGE_SENT,
                actor=message.sender,
                task_id=message.task_id,
                message=message.content,
                metadata={"recipient": message.recipient, "kind": message.kind},
            )
        )

    def add_artifact(self, artifact: AgentArtifact) -> "CollaborationBlackboard":
        event_type = AgentEventType.CRITIQUE_PUBLISHED if artifact.kind == "critique" else AgentEventType.ARTIFACT_PUBLISHED
        return replace(self, artifacts=(*self.artifacts, artifact)).append_event(
            AgentEvent(
                type=event_type,
                actor=artifact.owner,
                task_id=artifact.task_id,
                artifact_id=artifact.id,
                message=artifact.kind,
                metadata={"confidence": artifact.confidence},
            )
        )

    def apply_turn_result(self, task: AgentTask, agent_name: str, result: AgentTurnResult) -> "CollaborationBlackboard":
        board = self
        for message in result.messages:
            board = board.send_message(message)
        for artifact in result.artifacts:
            board = board.add_artifact(artifact)
        for follow_up in result.tasks:
            if follow_up.id not in board.tasks:
                board = board.add_task(follow_up).append_event(
                    AgentEvent(type=AgentEventType.TASK_CREATED, actor=agent_name, task_id=follow_up.id, message=follow_up.title)
                )
        if result.close_task:
            board = board.update_task(task.close()).append_event(
                AgentEvent(type=AgentEventType.TASK_CLOSED, actor=agent_name, task_id=task.id, message=task.title)
            )
        else:
            board = board.update_task(task.reopen()).append_event(
                AgentEvent(type=AgentEventType.TASK_REOPENED, actor=agent_name, task_id=task.id, message=task.title)
            )
        for event in result.events:
            board = board.append_event(event)
        return board

    def open_tasks(self) -> list[AgentTask]:
        return [task for task in self.tasks.values() if task.status == TaskStatus.OPEN]

    def latest_artifact(self, kind: str, owner: str | None = None) -> AgentArtifact | None:
        for artifact in reversed(self.artifacts):
            if artifact.kind == kind and (owner is None or artifact.owner == owner):
                return artifact
        return None

    def artifacts_by_kind(self, kind: str) -> list[AgentArtifact]:
        return [artifact for artifact in self.artifacts if artifact.kind == kind]

    def accepted_artifact(self) -> AgentArtifact | None:
        if not self.final_artifact_id:
            return None
        return next((artifact for artifact in self.artifacts if artifact.id == self.final_artifact_id), None)

    def accept_final(self, artifact_id: str, actor: str, reason: str) -> "CollaborationBlackboard":
        return replace(self, final_artifact_id=artifact_id).append_event(
            AgentEvent(type=AgentEventType.FINAL_ACCEPTED, actor=actor, artifact_id=artifact_id, message=reason)
        )

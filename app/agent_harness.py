from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.models import ChatResponse, StreamEvent
from app.privacy import sanitize_user_input


@dataclass
class AegisToolPlan:
    report_id: str | None = None
    risk_level: str | None = None

    @property
    def requires_tools(self) -> bool:
        return bool(self.report_id)


@dataclass
class AegisHarnessOutcome:
    original_input: str
    model_input: str
    response: ChatResponse
    tool_plan: AegisToolPlan


class AegisAgentHarness:
    """Single-turn harness around Aegis agent runtime.

    HTTP handlers stay thin while the harness prepares model input, resolves
    owned sessions, invokes runtime, and exposes report/tool-plan metadata for
    post-processing.
    """

    name = "AegisAgentHarness"

    def __init__(self, orchestrator, store):
        self.orchestrator = orchestrator
        self.store = store

    def run(self, message: str, session_id: str | None, owner_user_public_id: str) -> AegisHarnessOutcome:
        original_input, model_input, owned_session_id = self._prepare(message, session_id, owner_user_public_id)
        response = self.orchestrator.handle(model_input, owned_session_id)
        return AegisHarnessOutcome(
            original_input=original_input,
            model_input=model_input,
            response=response,
            tool_plan=self._tool_plan(response),
        )

    def stream(
        self,
        message: str,
        session_id: str | None,
        owner_user_public_id: str,
        emit: Callable[[StreamEvent], None] | None = None,
    ) -> tuple[list[StreamEvent], AegisHarnessOutcome | None]:
        original_input, model_input, owned_session_id = self._prepare(message, session_id, owner_user_public_id)
        events = self.orchestrator.handle_stream(model_input, owned_session_id)
        for event in events:
            if emit is not None:
                emit(event)
        response = None
        for event in reversed(events):
            if event.event == "done":
                payload = event.data.get("response")
                if payload:
                    response = payload
                break
        outcome = None
        if response is not None:
            # Streaming callers already receive the serialized response. The
            # non-streaming outcome is intentionally omitted to avoid rebuilding
            # dataclasses from JSON-compatible dicts.
            outcome = None
        return events, outcome

    def _prepare(self, message: str, session_id: str | None, owner_user_public_id: str) -> tuple[str, str, str]:
        original_input = message.strip()
        model_input = sanitize_user_input(original_input)
        owned_session_id = self.store.ensure_session(session_id, original_input, owner_user_public_id=owner_user_public_id)
        return original_input, model_input, owned_session_id

    def _tool_plan(self, response: ChatResponse) -> AegisToolPlan:
        if response.pending_report is None:
            return AegisToolPlan()
        return AegisToolPlan(response.pending_report.id, response.pending_report.risk_level.value)

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.privacy import sanitize_user_input
from app.models import ChatResponse, StreamEvent


@dataclass
class AegisHarnessOutcome:
    original_input: str
    model_input: str
    response: ChatResponse


class AegisAgentHarness:
    """Single-turn harness around Aegis agent runtime.

    HTTP handlers stay thin while the harness prepares model input, resolves
    owned sessions, and invokes runtime.
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
        )

    def stream(
        self,
        message: str,
        session_id: str | None,
        owner_user_public_id: str,
        emit: Callable[[StreamEvent], None] | None = None,
    ) -> tuple[list[StreamEvent], None]:
        original_input, model_input, owned_session_id = self._prepare(message, session_id, owner_user_public_id)
        events = self.orchestrator.handle_stream(model_input, owned_session_id)
        for event in events:
            if emit is not None:
                emit(event)
        # Streaming callers already receive the serialized response inside the
        # done event; the non-streaming outcome is intentionally omitted to
        # avoid rebuilding dataclasses from JSON-compatible dicts.
        return events, None

    def _prepare(self, message: str, session_id: str | None, owner_user_public_id: str) -> tuple[str, str, str]:
        original_input = message.strip()
        model_input = sanitize_user_input(original_input)
        owned_session_id = self.store.ensure_session(session_id, original_input, owner_user_public_id=owner_user_public_id)
        return original_input, model_input, owned_session_id

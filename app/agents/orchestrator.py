from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from app.agents.runtime import AgentRegistry, AgentRuntimeRunner
from app.agents.model_profiles import AgentModelRegistry
from app.agents.classic import CompanionAgent, CounselorAgent, KnowledgeAgent, LeadAgent, MemoryAgent, RiskGuardianAgent
from app.autonomous.runtime import AutonomousAgentRuntime
from app.llm import LLMClient, MockLLMClient
from app.models import AgentTrace, ChatResponse, Intent, PendingReport, RiskLevel, RuntimeEvent, RuntimeEventType, StreamEvent
from app.skills import SkillRegistry


class PsychOrchestrator:
    def __init__(self, registry: SkillRegistry, store, llm_client: LLMClient | None = None):
        self.registry = registry
        self.store = store
        self.llm_client = llm_client or MockLLMClient()
        self.settings = getattr(store, "settings", None)
        self.model_registry = AgentModelRegistry(self.settings, self.store, self.llm_client)
        self.model_registry.ensure_defaults()
        self.memory_agent = MemoryAgent()
        self.risk_agent = RiskGuardianAgent(registry)
        self.lead_agent = LeadAgent()
        self.knowledge_agent = KnowledgeAgent(registry, self.llm_client)
        self.counselor_agent = CounselorAgent(registry, self.llm_client)
        self.companion_agent = CompanionAgent()
        self.agent_registry = AgentRegistry()
        self.agent_registry.register("memory", self.memory_agent)
        self.agent_registry.register("lead", self.lead_agent)
        self.agent_registry.register("risk_guardian", self.risk_agent)
        self.agent_registry.register("knowledge", self.knowledge_agent)
        self.agent_registry.register("counselor", self.counselor_agent)
        self.agent_registry.register("companion", self.companion_agent)
        self.agent_registry.register("safety_planner", self.risk_agent)
        self.runtime_runner = AgentRuntimeRunner(self.agent_registry)
        self.autonomous_runtime = AutonomousAgentRuntime(store, registry, self.llm_client, self.settings, self.model_registry)
        self.last_runtime_events: list[RuntimeEvent] = []

    def handle(self, message: str, session_id: str | None = None) -> ChatResponse:
        return self._run(message, session_id)

    def handle_stream(self, message: str, session_id: str | None = None) -> list[StreamEvent]:
        events: list[StreamEvent] = []
        self._run(message, session_id, emit=events.append)
        return events

    def _run(
        self,
        message: str,
        session_id: str | None = None,
        emit: Callable[[StreamEvent], None] | None = None,
    ) -> ChatResponse:
        if getattr(self.settings, "agent_runtime", "autonomous") == "autonomous":
            return self._run_autonomous(message, session_id, emit)
        session_id = self.store.ensure_session(session_id, message)
        message_id = ChatResponse.new_id()
        trace: list[AgentTrace] = []
        runtime_events: list[RuntimeEvent] = []
        self.runtime_runner.reset()
        skills = []
        self._record_runtime(runtime_events, emit, RuntimeEventType.RUN_STARTED, {"session_id": session_id, "message_id": message_id})

        memory, memory_trace = self.runtime_runner.run_step(
            "memory",
            "load",
            lambda agent: agent.load(self.store, session_id),
        )
        memory_summary = memory["summary"]
        if memory_trace is not None:
            trace.append(memory_trace)
            self._emit_agent_trace(runtime_events, emit, memory_trace)

        self.store.append_message(session_id, "user", message)
        self._record_runtime(runtime_events, emit, RuntimeEventType.TOOL_REQUESTED, {"name": "assess_risk"})
        risk, risk_level, risk_trace = self.runtime_runner.run_step(
            "risk_guardian",
            "assess",
            lambda agent: agent.assess(message),
        )
        skills.append(risk)
        trace.append(risk_trace)
        self._emit_agent_trace(runtime_events, emit, risk_trace, RuntimeEventType.RISK_ASSESSED)
        self._emit_skill(runtime_events, emit, risk)

        intent, route_trace = self.runtime_runner.run_step(
            "lead",
            "route",
            lambda agent: agent.route(message, risk_level),
        )
        trace.append(route_trace)
        self._record_runtime(runtime_events, emit, RuntimeEventType.ROUTE_DECIDED, {"intent": intent.value, "risk_level": risk_level.value})
        self._emit_agent_trace(runtime_events, emit, route_trace)

        knowledge = None
        grounding = None
        pending_report = None
        # Chat-style companion turns skip knowledge retrieval to avoid noisy RAG.
        if intent is Intent.COMPANION:
            skip_trace = AgentTrace("KnowledgeAgent", "skip_knowledge", "intent=companion; chat-style turns do not retrieve RAG")
            trace.append(skip_trace)
            self._emit_agent_trace(runtime_events, emit, skip_trace, RuntimeEventType.KNOWLEDGE_RETRIEVED)
        elif intent in {Intent.COUNSELING, Intent.RESEARCH, Intent.RISK}:
            self._record_runtime(runtime_events, emit, RuntimeEventType.TOOL_REQUESTED, {"name": "search_knowledge"})
            knowledge, knowledge_trace = self.runtime_runner.run_step(
                "knowledge",
                "search",
                lambda agent: agent.search(message, memory_summary=memory_summary),
            )
            skills.append(knowledge)
            trace.append(knowledge_trace)
            self._emit_agent_trace(runtime_events, emit, knowledge_trace, RuntimeEventType.KNOWLEDGE_RETRIEVED)
            self._emit_skill(runtime_events, emit, knowledge)

        if risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
            self._record_runtime(runtime_events, emit, RuntimeEventType.TOOL_REQUESTED, {"name": "grounding_exercise"})
            grounding, grounding_trace = self.runtime_runner.run_step(
                "counselor",
                "grounding",
                lambda agent: agent.grounding(message),
            )
            skills.append(grounding)
            trace.append(grounding_trace)
            self._emit_agent_trace(runtime_events, emit, grounding_trace)
            self._emit_skill(runtime_events, emit, grounding)

        if risk_level is RiskLevel.HIGH:
            self._record_runtime(runtime_events, emit, RuntimeEventType.TOOL_REQUESTED, {"name": "create_pending_report"})
            report_result, report_trace = self.runtime_runner.run_step(
                "safety_planner",
                "create_report",
                lambda agent: agent.create_report(message, session_id, risk_level, intent, risk),
            )
            skills.append(report_result)
            pending_report = next(
                (report for report in self.store.list_reports() if report["id"] == report_result.output["report_id"]),
                None,
            )
            trace.append(report_trace)
            self._emit_agent_trace(runtime_events, emit, report_trace)
            self._emit_skill(runtime_events, emit, report_result)
            self._record_runtime(
                runtime_events,
                emit,
                RuntimeEventType.REPORT_CREATED,
                {"report_id": report_result.output["report_id"], "status": report_result.output.get("status", "pending")},
            )

        standard_skills = self.registry.response_skill_names(intent, risk_level, message)
        standard_skill_context = self.registry.standard_context(standard_skills)
        skill_trace = AgentTrace("SkillRegistry", "select_standard_skills", ",".join(standard_skills) or "none")
        trace.append(skill_trace)
        self._record_runtime(
            runtime_events,
            emit,
            RuntimeEventType.SKILLS_SELECTED,
            {"skills": standard_skills, "intent": intent.value, "risk_level": risk_level.value},
        )

        response_plan, plan_trace = self.runtime_runner.run_step(
            "counselor",
            "compose_plan",
            lambda agent: agent.compose_plan(message, intent, risk_level, memory_summary, knowledge, grounding, standard_skill_context),
        )
        trace.append(plan_trace)
        self._emit_agent_trace(runtime_events, emit, plan_trace)

        answer, answer_trace = self.runtime_runner.run_step(
            "counselor",
            "finalize_plan",
            lambda agent: agent.finalize_plan(response_plan),
        )
        trace.append(answer_trace)
        self._emit_agent_trace(runtime_events, emit, answer_trace)
        for chunk in self._token_chunks(answer):
            self._record_runtime(runtime_events, emit, RuntimeEventType.TOKEN_EMITTED, {"content": chunk})
        self.store.append_message(session_id, "assistant", answer)
        updated_memory, memory_update_trace = self.runtime_runner.run_step(
            "memory",
            "update",
            lambda agent: agent.update(self.store, session_id, message, answer),
        )
        trace.append(memory_update_trace)
        self._emit_agent_trace(runtime_events, emit, memory_update_trace, RuntimeEventType.MEMORY_UPDATED)
        self.store.add_trace(session_id, message_id, intent.value, risk_level.value, trace, skills, answer)

        response = ChatResponse(
            session_id=session_id,
            message_id=message_id,
            intent=intent,
            risk_level=risk_level,
            answer=answer,
            skills=skills,
            trace=trace,
            pending_report=None if pending_report is None else PendingReport.from_dict(pending_report),
            memory_summary=updated_memory["summary"],
            memory_used=bool(memory_summary),
            response_plan=response_plan,
        )
        self._record_runtime(runtime_events, emit, RuntimeEventType.RUN_COMPLETED, {"response": asdict(response)})
        self.last_runtime_events = runtime_events
        return response

    def _run_autonomous(
        self,
        message: str,
        session_id: str | None = None,
        emit: Callable[[StreamEvent], None] | None = None,
    ) -> ChatResponse:
        session_id = self.store.ensure_session(session_id, message)
        message_id = ChatResponse.new_id()
        runtime_events: list[RuntimeEvent] = []
        self.runtime_runner.reset()
        self._record_runtime(runtime_events, emit, RuntimeEventType.RUN_STARTED, {"session_id": session_id, "message_id": message_id})
        self.store.append_message(session_id, "user", message)
        outcome = self.autonomous_runtime.run(session_id, message)
        self.runtime_runner.event_history = [
            RuntimeEvent(type=RuntimeEventType.AGENT_STARTED, data={"agent_id": event.actor, "action": event.type.value})
            for event in outcome.board.events
        ]
        for event in outcome.board.events:
            self._record_runtime(
                runtime_events,
                emit,
                RuntimeEventType.AGENT_STARTED,
                {
                    "agent": event.actor,
                    "action": event.type.value,
                    "detail": event.message,
                    "task_id": event.task_id,
                    "artifact_id": event.artifact_id,
                    "metadata": event.metadata,
                },
            )
        self._record_runtime(
            runtime_events,
            emit,
            RuntimeEventType.ROUTE_DECIDED,
            {"intent": outcome.intent.value, "risk_level": outcome.risk_level.value, "runtime": "event_driven_autonomous"},
        )
        self._record_runtime(
            runtime_events,
            emit,
            RuntimeEventType.RISK_ASSESSED,
            {"agent": "RiskGuardianAgent", "action": "autonomous_risk_assessment", "detail": f"risk={outcome.risk_level.value}"},
        )
        context = outcome.board.latest_artifact("context")
        if context is not None and context.payload.get("knowledge") is not None:
            knowledge = context.payload["knowledge"]
            self._record_runtime(
                runtime_events,
                emit,
                RuntimeEventType.KNOWLEDGE_RETRIEVED,
                {
                    "agent": "KnowledgeAgent",
                    "action": "autonomous_context",
                    "detail": f"hits={len(knowledge.output.get('documents', []))}",
                },
            )
            standard_skills = context.payload.get("standard_skills", [])
            self._record_runtime(
                runtime_events,
                emit,
                RuntimeEventType.SKILLS_SELECTED,
                {"skills": standard_skills, "intent": outcome.intent.value, "risk_level": outcome.risk_level.value},
            )
        for skill in outcome.skills:
            self._emit_skill(runtime_events, emit, skill)
        if outcome.pending_report is not None:
            self._record_runtime(
                runtime_events,
                emit,
                RuntimeEventType.REPORT_CREATED,
                {"report_id": outcome.pending_report.id, "status": outcome.pending_report.status.value},
            )
        for chunk in self._token_chunks(outcome.answer):
            self._record_runtime(runtime_events, emit, RuntimeEventType.TOKEN_EMITTED, {"content": chunk})
        self.store.add_trace(session_id, message_id, outcome.intent.value, outcome.risk_level.value, outcome.trace, outcome.skills, outcome.answer)
        response = ChatResponse(
            session_id=session_id,
            message_id=message_id,
            intent=outcome.intent,
            risk_level=outcome.risk_level,
            answer=outcome.answer,
            skills=outcome.skills,
            trace=outcome.trace,
            pending_report=outcome.pending_report,
            memory_summary=outcome.memory_summary,
            memory_used=outcome.memory_used,
            response_plan=outcome.response_plan,
        )
        self._record_runtime(runtime_events, emit, RuntimeEventType.RUN_COMPLETED, {"response": asdict(response)})
        self.last_runtime_events = runtime_events
        return response

    def _record_runtime(
        self,
        runtime_events: list[RuntimeEvent],
        emit: Callable[[StreamEvent], None] | None,
        event_type: RuntimeEventType,
        data: dict,
    ) -> None:
        runtime_event = RuntimeEvent(type=event_type, data=data)
        runtime_events.append(runtime_event)
        if emit is not None:
            emit(StreamEvent.from_runtime(runtime_event))

    def _emit_agent_trace(
        self,
        runtime_events: list[RuntimeEvent],
        emit: Callable[[StreamEvent], None] | None,
        trace_item: AgentTrace,
        event_type: RuntimeEventType = RuntimeEventType.AGENT_STARTED,
    ) -> None:
        self._record_runtime(
            runtime_events,
            emit,
            event_type,
            {"agent": trace_item.agent, "action": trace_item.action, "detail": trace_item.detail},
        )

    def _emit_skill(self, runtime_events: list[RuntimeEvent], emit: Callable[[StreamEvent], None] | None, skill) -> None:
        self._record_runtime(
            runtime_events,
            emit,
            RuntimeEventType.TOOL_COMPLETED,
            {"name": skill.name, "output": skill.output, "side_effect": skill.side_effect},
        )

    def _token_chunks(self, answer: str) -> list[str]:
        text = answer or ""
        if len(text) <= 48:
            return [text]
        return [text[idx:idx + 48] for idx in range(0, len(text), 48)]


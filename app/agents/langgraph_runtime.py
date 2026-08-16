"""LangGraph 运行时:用 StateGraph 编排六个单轮 Agent(主推链路)。

与自研 autonomous 黑板 runtime 的关系:
- 两者复用同一批单轮 Agent 与安全规则,只是编排机制不同;
- 本模块以 LangGraph 的声明式状态图表达"记忆→风险→路由→(条件)上下文→
  报告→提案→终稿"流水线,条件边承担意图分流(companion 跳过 RAG);
- 产出与 AutonomousRunOutcome 对齐(board 为 None),orchestrator 统一收敛为 ChatResponse。

设计说明:
- 状态字段用 Annotated[list, operator.add] 让各节点返回"增量",LangGraph 自动合并,
  trace/skills 无需全局可变对象;
- 图只编译一次,每次对话 invoke 一份全新初始状态,天然线程安全;
- finalize 节点支持低风险直播(on_token 回调,与另两个运行时行为一致)。
"""
from __future__ import annotations

import operator
from typing import Annotated, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.classic import (
    CompanionAgent,
    CounselorAgent,
    KnowledgeAgent,
    LeadAgent,
    MemoryAgent,
    RiskGuardianAgent,
)
from app.agents.model_profiles import AgentModelRegistry
from app.llm import LLMClient, MockLLMClient
from app.models import (
    AgentTrace,
    Intent,
    PendingReport,
    ResponsePlan,
    RiskLevel,
    SkillResult,
)
from app.autonomous.runtime import AutonomousRunOutcome
from app.skills import SkillRegistry


class GraphState(TypedDict, total=False):
    """一次对话在图中流转的全部状态;total=False 允许节点只返回增量字段。"""

    session_id: str
    message: str
    memory_summary: str
    memory_used: bool
    risk: SkillResult
    risk_level: RiskLevel
    intent: Intent
    knowledge: SkillResult | None
    grounding: SkillResult | None
    pending_report: PendingReport | None
    response_plan: ResponsePlan | None
    answer: str
    # 增量合并字段:各节点 append,LangGraph 用 operator.add 拼接
    skills: Annotated[list[SkillResult], operator.add]
    trace: Annotated[list[AgentTrace], operator.add]


def _skip_context(state: GraphState) -> str:
    """条件边:陪伴类低风险闲聊不触发 RAG 检索,直接进入提案。"""
    if state["intent"] is Intent.COMPANION and state["risk_level"] is RiskLevel.LOW:
        return "compose"
    return "context"


class LangGraphRuntime:
    framework_name = "langgraph_state_graph"

    def __init__(self, registry: SkillRegistry, store, llm_client: LLMClient | None, settings, model_registry: AgentModelRegistry | None = None):
        self.registry = registry
        self.store = store
        self.llm_client = llm_client or MockLLMClient()
        self.settings = settings
        self.model_registry = model_registry
        self.memory_agent = MemoryAgent()
        risk_client = model_registry.client_for("RiskGuardianAgent") if model_registry else None
        self.risk_agent = RiskGuardianAgent(
            registry,
            llm_client=risk_client,
            llm_channel_enabled=bool(getattr(settings, "risk_llm_channel_enabled", False)),
        )
        self.lead_agent = LeadAgent()
        # Counselor/Knowledge 使用档案化模型客户端(与自治运行时一致)
        counselor_client = model_registry.client_for("CounselorAgent") if model_registry else self.llm_client
        knowledge_client = model_registry.client_for("KnowledgeAgent") if model_registry else self.llm_client
        self.knowledge_agent = KnowledgeAgent(registry, knowledge_client)
        self.counselor_agent = CounselorAgent(registry, counselor_client)
        self.companion_agent = CompanionAgent()
        # 低风险直播回调:run() 时注入,finalize 节点读取
        self._on_reply_token: Callable[[str], None] | None = None
        self.graph = self._build_graph()

    # ---------------- 图构建 ----------------
    def _build_graph(self):
        builder = StateGraph(GraphState)

        builder.add_node("load_memory", self._node_load_memory)
        builder.add_node("assess_risk", self._node_assess_risk)
        builder.add_node("route_intent", self._node_route_intent)
        builder.add_node("context", self._node_gather_context)
        builder.add_node("report", self._node_maybe_report)
        builder.add_node("compose", self._node_compose)
        builder.add_node("finalize", self._node_finalize)

        builder.add_edge(START, "load_memory")
        builder.add_edge("load_memory", "assess_risk")
        builder.add_edge("assess_risk", "route_intent")
        # 条件边:意图分流(companion 闲聊跳过知识检索)
        builder.add_conditional_edges("route_intent", _skip_context, {"context": "context", "compose": "compose"})
        builder.add_edge("context", "report")
        builder.add_edge("report", "compose")
        builder.add_edge("compose", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    # ---------------- 节点实现(复用单轮 Agent,逻辑与 ordered 路径一致) ----------------
    def _node_load_memory(self, state: GraphState) -> dict:
        memory, memory_trace = self.memory_agent.load(self.store, state["session_id"])
        summary = memory.get("summary", "")
        updates: dict = {"memory_summary": summary, "memory_used": bool(summary)}
        if memory_trace is not None:
            updates["trace"] = [memory_trace]
        return updates

    def _node_assess_risk(self, state: GraphState) -> dict:
        risk, risk_level, risk_trace = self.risk_agent.assess(state["message"])
        return {
            "risk": risk,
            "risk_level": risk_level,
            "skills": [risk],
            "trace": [risk_trace],
        }

    def _node_route_intent(self, state: GraphState) -> dict:
        intent, route_trace = self.lead_agent.route(state["message"], state["risk_level"])
        return {"intent": intent, "trace": [route_trace]}

    def _node_gather_context(self, state: GraphState) -> dict:
        updates: dict = {"knowledge": None, "grounding": None}
        traces: list[AgentTrace] = []
        skills: list[SkillResult] = []
        if state["intent"] is not Intent.COMPANION:
            knowledge, knowledge_trace = self.knowledge_agent.search(state["message"], memory_summary=state.get("memory_summary", ""))
            updates["knowledge"] = knowledge
            skills.append(knowledge)
            traces.append(knowledge_trace)
        if state["risk_level"] in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
            grounding, grounding_trace = self.counselor_agent.grounding(state["message"])
            updates["grounding"] = grounding
            skills.append(grounding)
            traces.append(grounding_trace)
        updates["skills"] = skills
        updates["trace"] = traces
        return updates

    def _node_maybe_report(self, state: GraphState) -> dict:
        if state["risk_level"] is not RiskLevel.HIGH:
            return {}
        report_result, report_trace = self.risk_agent.create_report(
            state["message"], state["session_id"], state["risk_level"], state["intent"], state["risk"]
        )
        pending = next(
            (report for report in self.store.list_reports() if report["id"] == report_result.output["report_id"]),
            None,
        )
        report_model = PendingReport.from_dict(pending) if pending else None
        return {
            "pending_report": report_model,
            "skills": [report_result],
            "trace": [report_trace],
        }

    def _node_compose(self, state: GraphState) -> dict:
        standard_skills = self.registry.response_skill_names(state["intent"], state["risk_level"], state["message"])
        standard_context = self.registry.standard_context(standard_skills)
        plan, plan_trace = self.counselor_agent.compose_plan(
            state["message"],
            state["intent"],
            state["risk_level"],
            state.get("memory_summary", ""),
            state.get("knowledge"),
            state.get("grounding"),
            standard_context,
        )
        return {
            "response_plan": plan,
            "trace": [
                plan_trace,
                AgentTrace("SkillRegistry", "select_standard_skills", ",".join(standard_skills) or "none"),
            ],
        }

    def _node_finalize(self, state: GraphState) -> dict:
        on_token = None
        if state["risk_level"] is RiskLevel.LOW:
            on_token = self._on_reply_token  # 仅低风险直播,与另两个运行时的安全门控一致
        answer, answer_trace = self.counselor_agent.finalize_plan(state["response_plan"], on_token=on_token)
        return {"answer": answer, "trace": [answer_trace]}

    # ---------------- 对外入口 ----------------
    def run(self, session_id: str, message: str, on_reply_token: Callable[[str], None] | None = None) -> AutonomousRunOutcome:
        self._on_reply_token = on_reply_token
        final: GraphState = self.graph.invoke(
            {"session_id": session_id, "message": message, "skills": [], "trace": []}
        )
        self._on_reply_token = None
        intent = final.get("intent", Intent.COMPANION)
        risk_level = final.get("risk_level", RiskLevel.LOW)
        answer = final.get("answer", "")
        memory_used = bool(final.get("memory_summary"))
        return AutonomousRunOutcome(
            intent=intent,
            risk_level=risk_level,
            answer=answer,
            skills=list(final.get("skills", [])),
            trace=list(final.get("trace", [])),
            pending_report=final.get("pending_report"),
            memory_summary=final.get("memory_summary", ""),
            memory_used=memory_used,
            board=None,  # LangGraph 无黑板;trace 即过程记录
            response_plan=final.get("response_plan"),
        )

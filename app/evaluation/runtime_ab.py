"""三运行时 A/B 评测:同数据集对比 langgraph/autonomous/ordered 的延迟、trace 步数、
LLM 调用数与判定一致性,用数据说话。

保证可比性的关键:
- 三个编排器共享同一份知识库种子与同一只 MockLLMClient(确定性,排除模型随机);
- 用 CountingLLMClient 包装,统计各路径的 LLM 调用次数(generate/stream/assess_risk/chat_with_tools);
- 每条消息对三个运行时各跑一次,记录指标。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.langgraph_runtime import LangGraphRuntime
from app.agents.orchestrator import PsychOrchestrator
from app.database import Base
from app.llm import MockLLMClient
from app.repository import DatabaseStore
from app.skills import SkillRegistry


class CountingLLMClient(MockLLMClient):
    """包装 MockLLMClient,统计各类调用次数;行为与 mock 完全一致(均返回 None/模板兜底)。"""

    def __init__(self) -> None:
        self.calls = {"generate": 0, "stream": 0, "rewrite": 0, "assess_risk": 0, "chat_with_tools": 0}

    def generate_support_reply(self, context) -> str | None:
        self.calls["generate"] += 1
        return None

    def stream_support_reply(self, context, on_token) -> str | None:
        self.calls["stream"] += 1
        return None

    def rewrite_knowledge_query(self, message, memory_summary="") -> str | None:
        self.calls["rewrite"] += 1
        return None

    def assess_risk(self, text: str) -> dict | None:
        self.calls["assess_risk"] += 1
        return None

    def chat_with_tools(self, system, user, tools) -> list[str] | None:
        self.calls["chat_with_tools"] += 1
        return None

    @property
    def total(self) -> int:
        return sum(self.calls.values())


def _build_orchestrator(data_dir: Path, runtime: str, llm_client: CountingLLMClient) -> PsychOrchestrator:
    knowledge_dir = data_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    if not any(knowledge_dir.iterdir()):
        (knowledge_dir / "seed.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")
    engine = create_engine(f"sqlite:///{data_dir / f'{runtime}.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    from app.config import Settings

    settings = Settings(
        database_url=f"sqlite:///{data_dir / f'{runtime}.sqlite'}",
        redis_url="", vector_enabled=False, agent_runtime=runtime,
        function_calling_enabled=False, risk_llm_channel_enabled=False,
    )
    store = DatabaseStore(session_factory, settings=settings)
    store.seed_knowledge_dir(knowledge_dir)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge, settings=settings)
    orchestrator = PsychOrchestrator(registry, store, llm_client)
    orchestrator.settings = settings
    if runtime == "langgraph":
        orchestrator.langgraph_runtime = LangGraphRuntime(registry, store, llm_client, settings, orchestrator.model_registry)
    return orchestrator


# 代表性消息集（覆盖四意图 + 中风险 + 显式/隐式高危 + 第三人称干扰），
# 用于三运行时在一致、贴近真实语境的数据上对比。其中包含一条规则引擎
# 当前会漏判的隐式高危样本（"从没出生过"），以如实暴露跨运行时一致的判定缺口，
# 而非人为维持满分。
MESSAGES = [
    ("今天只是想找人说说话", "companion", "low"),
    ("我最近考试压力很大，晚上睡不着", "counseling", "low"),
    ("焦虑一般如何支持？有没有权威一点的方法？", "research", "low"),
    ("我最近真的撑不住了，但还愿意找人帮忙", "counseling", "medium"),
    ("我不想活了，想结束生命", "risk", "high"),
    ("我一遍遍想，要是能结束这一切就好了", "risk", "high"),
    ("我有时候希望自己从没出生过", "risk", "high"),
    ("朋友最近总说想死，我该怎么帮他", "counseling", "low"),
    ("最近焦虑很多，白天很难集中注意力", "counseling", "low"),
    ("怎么才能改善自己的睡眠质量", "research", "low"),
]


def run_runtime_ab(data_dir: Path | None = None) -> dict[str, Any]:
    data_dir = data_dir or Path(__file__).resolve().parents[2] / "data" / "harness"
    data_dir.mkdir(parents=True, exist_ok=True)

    runtimes = ["langgraph", "autonomous", "ordered"]
    results: dict[str, Any] = {"runtimes": runtimes, "messages": [m[0] for m in MESSAGES], "comparison": {}}

    for runtime in runtimes:
        # 每个运行时独立数据目录,避免会话串扰
        sub_dir = data_dir / runtime
        sub_dir.mkdir(parents=True, exist_ok=True)
        client = CountingLLMClient()
        orchestrator = _build_orchestrator(sub_dir, runtime, client)

        per_message: list[dict] = []
        total_latency = 0.0
        total_steps = 0
        total_llm_calls = 0
        intent_match = 0
        risk_match = 0

        for message, expected_intent, expected_risk in MESSAGES:
            t0 = time.perf_counter()
            response = orchestrator.handle(message)
            latency = time.perf_counter() - t0
            steps = len(response.trace)
            llm_calls = client.total - total_llm_calls  # 本条消息新增调用数
            total_latency += latency
            total_steps += steps
            total_llm_calls = client.total
            if response.intent.value == expected_intent:
                intent_match += 1
            if response.risk_level.value == expected_risk:
                risk_match += 1
            per_message.append({
                "message": message,
                "latency_ms": round(latency * 1000, 1),
                "trace_steps": steps,
                "llm_calls": llm_calls,
                "intent": response.intent.value,
                "risk_level": response.risk_level.value,
            })

        results["comparison"][runtime] = {
            "avg_latency_ms": round(total_latency / len(MESSAGES) * 1000, 1),
            "avg_trace_steps": round(total_steps / len(MESSAGES), 1),
            "total_llm_calls": total_llm_calls,
            "intent_accuracy": round(intent_match / len(MESSAGES), 4),
            "risk_accuracy": round(risk_match / len(MESSAGES), 4),
            "framework": orchestrator.langgraph_runtime.framework_name if runtime == "langgraph" else (
                orchestrator.autonomous_runtime.framework_name if runtime == "autonomous" else "ordered_runtime"
            ),
            "per_message": per_message,
        }

    # 一致性:三运行时对同一消息的判定是否相同
    consistency: list[dict] = []
    for idx, (message, _, _) in enumerate(MESSAGES):
        intents = {results["comparison"][r]["per_message"][idx]["intent"] for r in runtimes}
        risks = {results["comparison"][r]["per_message"][idx]["risk_level"] for r in runtimes}
        consistency.append({
            "message": message,
            "intent_consistent": len(intents) == 1,
            "risk_consistent": len(risks) == 1,
        })
    results["consistency"] = consistency
    results["summary"] = {
        r: {
            "avg_latency_ms": results["comparison"][r]["avg_latency_ms"],
            "avg_trace_steps": results["comparison"][r]["avg_trace_steps"],
            "total_llm_calls": results["comparison"][r]["total_llm_calls"],
            "intent_accuracy": results["comparison"][r]["intent_accuracy"],
            "risk_accuracy": results["comparison"][r]["risk_accuracy"],
        }
        for r in runtimes
    }
    return results


def render_report(results: dict) -> str:
    """生成可读的 Markdown 摘要。"""
    lines = ["# 三运行时 A/B 评测报告\n", "| 指标 | langgraph | autonomous | ordered |", "| --- | --- | --- | --- |"]
    metrics = [
        ("平均延迟(ms)", "avg_latency_ms"),
        ("平均 trace 步数", "avg_trace_steps"),
        ("LLM 调用总数", "total_llm_calls"),
        ("意图准确率", "intent_accuracy"),
        ("风险准确率", "risk_accuracy"),
    ]
    for label, key in metrics:
        row = [str(results["summary"][r][key]) for r in results["runtimes"]]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    lines.append("\n## 一致性\n")
    lines.append("| 消息 | 意图一致 | 风险一致 |")
    lines.append("| --- | --- | --- |")
    for item in results["consistency"]:
        lines.append(f"| {item['message'][:20]}… | {'✓' if item['intent_consistent'] else '✗'} | {'✓' if item['risk_consistent'] else '✗'} |")
    return "\n".join(lines) + "\n"

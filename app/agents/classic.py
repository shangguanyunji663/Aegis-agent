from __future__ import annotations

from app.llm import LLMClient, LLMContext
import os
from app.models import AgentTrace, Intent, ResponsePlan, RiskLevel, SkillResult
from app.skills import SkillRegistry


def format_source_label(source: str) -> str:
    """把检索/文档 source 字段格式化为用户友好的中文标签。

    规则：
    - 特殊内部标识映射（例如 'response_plan' -> '内部建议'）。
    - 若是文件名，去掉扩展名并做简单美化（`-`/`_` 替换为空格）；可通过映射表覆盖特定文件名。
    - 返回不会包含方括号，供插入到用户可见文本中。
    """
    if not source:
        return "来源"
    name = os.path.basename(source)
    name = os.path.splitext(name)[0]
    canonical = name.lower()
    mapping = {
        "response_plan": "内部建议",
        "exam-season-guidance": "考试季建议",
    }
    if canonical in mapping:
        return mapping[canonical]
    # 基本美化：替换 - 和 _ 为中文空格并首字母大写（如有英文）
    label = name.replace("-", " ").replace("_", " ")
    return label


class MemoryAgent:
    name = "MemoryAgent"

    def load(self, store, session_id: str) -> tuple[dict, AgentTrace | None]:
        memory = store.get_memory(session_id)
        summary = memory.get("summary", "")
        if not summary:
            return memory, None
        return memory, AgentTrace(self.name, "load_memory", f"covered_messages={memory.get('covered_message_count', 0)}")

    def update(self, store, session_id: str, user_message: str, assistant_answer: str) -> tuple[dict, AgentTrace]:
        memory = store.update_memory(session_id, user_message, assistant_answer)
        return memory, AgentTrace(self.name, "update_memory", f"covered_messages={memory.get('covered_message_count', 0)}")


class RiskGuardianAgent:
    name = "RiskGuardianAgent"

    def __init__(self, registry: SkillRegistry, llm_client=None, llm_channel_enabled: bool = False):
        self.registry = registry
        self.llm_client = llm_client
        self.llm_channel_enabled = llm_channel_enabled

    def assess(self, message: str) -> tuple[SkillResult, RiskLevel, AgentTrace]:
        result = self.registry.get("assess_risk").handler(message)
        risk_level = RiskLevel(result.output["risk_level"])
        rationale = list(result.output["rationale"])
        channels = {"rules": risk_level.value, "llm": "skipped"}
        # 双通道融合:规则 ∪ LLM,任一通道判 HIGH 即 HIGH(安全优先取并集);
        # LLM 失败/超时/mock 一律回退纯规则结果
        if self.llm_channel_enabled and self.llm_client is not None:
            try:
                llm_out = self.llm_client.assess_risk(message)
            except Exception:
                llm_out = None
            if llm_out is not None:
                llm_level = RiskLevel(llm_out["risk_level"])
                channels["llm"] = llm_level.value
                order = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
                if order[llm_level] > order[risk_level]:
                    risk_level = llm_level
                    rationale.append(f"LLM通道({llm_out.get('reason', '')})")
                    result.output["report_eligible"] = risk_level is RiskLevel.HIGH or result.output.get("report_eligible", False)
                    if risk_level is RiskLevel.HIGH:
                        result.output["escalation_policy"] = "create_pending_report_and_require_admin_review"
                elif llm_level is risk_level and llm_level is not RiskLevel.LOW:
                    rationale.append(f"双通道一致确认({llm_out.get('reason', '')})")
        result.output["rationale"] = rationale
        result.output["risk_channels"] = channels
        detail = "; ".join(rationale)
        return result, risk_level, AgentTrace(self.name, "assess_risk", detail)

    def create_report(self, message: str, session_id: str, risk_level: RiskLevel, intent: Intent, risk: SkillResult) -> tuple[SkillResult, AgentTrace]:
        result = self.registry.get("create_pending_report").handler(
            message,
            session_id=session_id,
            risk_level=risk_level.value,
            rationale=risk.output["rationale"],
            intent=intent.value,
            emotion=risk.output.get("emotion", "high_risk"),
            emotion_score=risk.output.get("emotion_score", 4.0),
            confidence=risk.output.get("confidence", 0.95),
            summary=risk.output.get("summary", ""),
        )
        return result, AgentTrace(self.name, "create_pending_report", result.output["report_id"])


class LeadAgent:
    name = "LeadAgent"

    def route(self, message: str, risk_level: RiskLevel) -> tuple[Intent, AgentTrace]:
        if risk_level is RiskLevel.HIGH:
            intent = Intent.RISK
        else:
            research_terms = ["资料", "研究", "证据", "为什么", "原理", "指南", "权威"]
            counseling_terms = ["焦虑", "抑郁", "低落", "压力", "睡眠", "失眠", "难受", "崩溃", "人际", "考试"]
            if any(term in message for term in research_terms):
                intent = Intent.RESEARCH
            elif any(term in message for term in counseling_terms) or risk_level is RiskLevel.MEDIUM:
                intent = Intent.COUNSELING
            else:
                intent = Intent.COMPANION
        return intent, AgentTrace(self.name, "route", f"intent={intent.value}, risk={risk_level.value}")


class KnowledgeAgent:
    name = "KnowledgeAgent"

    def __init__(self, registry: SkillRegistry, llm_client: LLMClient | None = None):
        self.registry = registry
        self.llm_client = llm_client

    def search(self, message: str, memory_summary: str = "") -> tuple[SkillResult, AgentTrace]:
        query = self.rewrite_query(message, memory_summary)
        result = self.registry.get("search_knowledge").handler(query)
        documents = result.output.get("documents", [])
        enriched = SkillResult(
            name=result.name,
            output={
                **result.output,
                "documents": documents,
                "knowledge_query": query,
            },
            side_effect=result.side_effect,
        )
        return enriched, AgentTrace(self.name, "search_knowledge", f"query={query}; hits={len(documents)}")

    def rewrite_query(self, message: str, memory_summary: str = "") -> str:
        text = " ".join((message or "").split()).strip()
        if self.llm_client is not None:
            try:
                rewritten = self.llm_client.rewrite_knowledge_query(text, memory_summary)
                if rewritten:
                    return rewritten[:60]
            except Exception:
                pass
        return text[:60]


class CounselorAgent:
    name = "CounselorAgent"

    def __init__(self, registry: SkillRegistry, llm_client: LLMClient):
        self.registry = registry
        self.llm_client = llm_client

    def grounding(self, message: str) -> tuple[SkillResult, AgentTrace]:
        result = self.registry.get("grounding_exercise").handler(message)
        return result, AgentTrace(self.name, "grounding_exercise", result.output["title"])
 
    def compose_plan(
        self,
        message: str,
        intent: Intent,
        risk_level: RiskLevel,
        memory_summary: str = "",
        knowledge: SkillResult | None = None,
        grounding: SkillResult | None = None,
        standard_skill_context: str = "",
    ) -> tuple[ResponsePlan, AgentTrace]:
        """构造一个简单的 ResponsePlan，供后续 `finalize_plan` 使用。

        该实现保持轻量：将检索到的文档摘录为 knowledge_snippets，保留记忆摘要与引导步骤，
        并生成基础的 prompt messages（system + user）。
        """
        plan = ResponsePlan(
            mode="final",
            response_agent=self.name,
            intent=intent.value,
            risk_level=risk_level.value,
            memory_brief=memory_summary or "",
        )
        if knowledge and isinstance(knowledge.output, dict):
            docs = knowledge.output.get("documents") or []
            plan.knowledge_snippets = [d.get("content") or d.get("snippet") or "" for d in docs]
        if grounding and isinstance(grounding.output, dict):
            plan.grounding_steps = grounding.output.get("steps") or []
        plan.skill_context = standard_skill_context or ""
        plan.prompt_messages = [
            {"role": "system", "content": "你是一个温和而负责的心理支持助手。"},
            {"role": "user", "content": message},
        ]
        return plan, AgentTrace(self.name, "compose_plan", f"intent={intent.value};risk={risk_level.value};knowledge_hits={len(plan.knowledge_snippets)}")
 
    def finalize_plan(self, plan: ResponsePlan, on_token=None) -> tuple[str, AgentTrace]:
        fallback = self._fallback_answer(
            Intent(plan.intent),
            RiskLevel(plan.risk_level),
            plan.memory_brief,
            _knowledge_from_plan(plan),
            _grounding_from_plan(plan),
        )
        risk_level = RiskLevel(plan.risk_level)
        intent = Intent(plan.intent)
        if risk_level is RiskLevel.HIGH:
            return fallback, AgentTrace(self.name, "compose_answer", "plan:safety_template")

        context = LLMContext(
            message=next((item["content"] for item in reversed(plan.prompt_messages) if item.get("role") == "user"), ""),
            intent=intent,
            risk_level=risk_level,
            memory_summary=plan.memory_brief,
            knowledge_snippets=plan.knowledge_snippets,
            grounding_steps=plan.grounding_steps,
            response_skill_context=plan.skill_context,
        )
        generated = None
        if on_token is not None:
            # 流式生成:token 边生成边回调(调用方仅在低风险时传入回调)
            generated = self.llm_client.stream_support_reply(context, on_token)
        if not generated:
            generated = self.llm_client.generate_support_reply(context)
        if generated:
            return generated.strip(), AgentTrace(self.name, "compose_answer", f"llm:{self.llm_client.provider}/{self.llm_client.model}")
        return fallback, AgentTrace(self.name, "compose_answer", f"fallback:{self.llm_client.provider}")

    def _fallback_answer(self, intent: Intent, risk_level: RiskLevel, memory_summary: str, knowledge, grounding) -> str:
        lines = []
        if risk_level is RiskLevel.HIGH:
            lines.append("我很在意你刚才提到的危险信号。此刻请先把安全放在第一位：如果你已经有明确计划或身边有可伤害自己的物品，请立刻联系身边可信任的人、学校心理中心或当地紧急服务。")
        elif risk_level is RiskLevel.MEDIUM:
            lines.append("听起来你已经撑得很辛苦了。我们先把这一刻稳定下来，再一起把问题拆小。")
        else:
            lines.append("我听到了你的困扰。我们可以先从最具体、最影响你的那一部分开始。")

        if memory_summary:
            latest_memory = memory_summary.splitlines()[-1][:180]
            lines.append(f"\n我会结合你前面提到的情况继续陪你梳理：{latest_memory}")

        if grounding:
            steps = grounding.output["steps"]
            lines.append(f"\n{grounding.output['title']}：")
            lines.extend(f"{idx}. {step}" for idx, step in enumerate(steps, 1))

        if risk_level is not RiskLevel.HIGH and knowledge and knowledge.output["documents"]:
            top = knowledge.output["documents"][0]
            content = top.get("content") or top.get("snippet") or ""
            label = format_source_label(top.get("source", ""))
            lines.append(f"\n我也查到一个相关支持方向：（来源：{label}） {content[:240]}")

        if intent is Intent.RESEARCH:
            lines.append("\n如果你愿意，我可以继续把资料整理成“原因、可尝试方法、何时求助”三段。")
        elif intent is Intent.RISK:
            lines.append("\n现在最重要的是不要一个人扛着。请尽快联系身边可信任的人，让对方陪你一起联系学校心理中心或当地紧急服务。")
        else:
            lines.append("\n你可以接着告诉我：这件事最难受的时刻通常发生在什么时候？")
        return "\n".join(lines)


class CompanionAgent:
    name = "CompanionAgent"


def _knowledge_from_plan(plan: ResponsePlan):
    if not plan.knowledge_snippets:
        return None
    return SkillResult(
        name="search_knowledge",
        output={
            "documents": [
                {"source": format_source_label("response_plan"), "content": snippet, "snippet": snippet}
                for snippet in plan.knowledge_snippets
            ]
        },
    )


def _grounding_from_plan(plan: ResponsePlan):
    if not plan.grounding_steps:
        return None
    return SkillResult(name="grounding_exercise", output={"title": "稳定练习", "steps": plan.grounding_steps})

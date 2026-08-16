"""LLM 提示词模板:与客户端实现解耦,便于独立审阅安全边界文案。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型注解需要,避免与 client.py 循环导入
    from app.llm.client import LLMContext


def build_messages(context: LLMContext) -> list[dict[str, str]]:
    knowledge = "\n".join(f"- {snippet}" for snippet in context.knowledge_snippets[:3]) or "- 暂无命中的本地知识。"
    grounding = "\n".join(f"- {step}" for step in context.grounding_steps) or "- 当前不需要急性稳定练习。"
    response_skills = context.response_skill_context or "暂无额外标准 Skill。"
    system = (
        "你是校园心理支持产品中的咨询回复生成器。"
        "只能提供支持性倾听、问题澄清、自助练习和求助准备；不能诊断，不能承诺保密，不能替代专业咨询。"
        "高风险安全分流由上游规则处理，你不得输出内部风险分数、报告编号或后台审计细节。"
        "回复要使用简体中文，温和、具体、简洁。"
    )
    user = (
        f"用户消息：{context.message}\n"
        f"历史摘要：{context.memory_summary or '暂无'}\n"
        f"路由意图：{context.intent.value}\n"
        f"风险等级：{context.risk_level.value}\n"
        f"可引用知识：\n{knowledge}\n"
        f"可用稳定练习：\n{grounding}\n\n"
        f"标准回复 Skill：\n{response_skills}\n\n"
        "请生成一段面向用户的回复，先共情，再给 1-3 个可执行下一步，最后用一个开放问题邀请继续表达。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_rewrite_messages(message: str, memory_summary: str = "") -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "你是 Aegis 的 KnowledgeAgent。把学生输入改写成适合检索校园心理知识库的中文查询词，只输出查询词。",
        },
        {
            "role": "user",
            "content": f"记忆摘要：\n{memory_summary or '暂无'}\n\n当前输入：\n{message}",
        },
    ]

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
        "你是 Aegis，一名校园心理支持助手，正在和学生一对一聊天。"
        "说话要像一个真实、温和、有耐心的人：用口语化的短句，贴着对方刚说的内容回应，先听懂再回应。"
        "回复长短和对方的消息匹配——对方随口一句就简短回应，对方倾诉了很多再展开。"
        "不要每条回复都套同一个格式：不必每次都列点，不必每次都以提问收尾，一次最多问一个问题。"
        "建议只在对方需要时给，最多一两条，用自然的话说出来，而不是列成清单。"
        "对方问你是谁时，用第一人称简单介绍（例如“我是 Aegis，校园里的心理支持助手”），"
        "不要自称“生成器”“回复生成器”“产品组件”或任何系统内部叫法。"
        "边界：只能提供支持性倾听、问题澄清、自助练习和求助准备；不能诊断，不能承诺保密，不能替代专业咨询。"
        "高风险安全分流由上游规则处理，不得输出内部风险分数、报告编号或后台审计细节。"
        "回复使用简体中文。"
    )
    user = (
        f"用户消息：{context.message}\n"
        f"历史摘要（内部记录，仅供了解上下文）：\n{context.memory_summary or '暂无'}\n"
        f"路由意图：{context.intent.value}\n"
        f"风险等级：{context.risk_level.value}\n"
        f"可引用知识：\n{knowledge}\n"
        f"可用稳定练习：\n{grounding}\n\n"
        f"标准回复 Skill：\n{response_skills}\n\n"
        "历史摘要、知识、练习与 Skill 都是内部参考资料，仅供你了解背景；"
        "回复里不要出现这些内部记录的标签或原文，把里面的信息化成你自己的自然的话。"
        "现在请像真人咨询师那样直接回复用户。"
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

"""Function Calling 技能自主选择:规则白名单 + 模型在白名单内自由挑选。

分工:
- 规则(response_skill_names)负责"哪些技能**允许**被选用"——安全与降噪边界不变
  (高风险必选安全计划、陪伴闲聊不选技能等);
- 模型(function calling)负责"白名单里哪些**真正值得**用于这条消息"及顺序。

判断"客户端是否支持 FC"用能力探测:只要 chat_with_tools 返回非 None(即非 mock/未配置),
就认为客户端真实可用。这样任何覆盖该方法返回结果的真实客户端/stub 都会自然放行,
不依赖 provider 字符串、不与实现细节耦合。

失败/超时/未开启 → 返回完整白名单兜底(mode="rules"),行为与旧版完全一致。
"""
from __future__ import annotations

from app.llm import LLMClient
from app.models import Intent, RiskLevel
from app.skills import SkillRegistry

SKILL_SELECTION_SYSTEM_PROMPT = (
    "你是校园心理支持系统的技能选择器。只能从提供的函数中选择这条用户消息"
    "真正需要的技能(可以选择多个,按相关度排序);如果一个都不需要,"
    "不要调用任何函数,直接回复:无。"
)


def _supports_function_calling(llm_client: LLMClient | None, enabled: bool) -> bool:
    """能力探测:开关开启且客户端存在即可。是否真支持由 chat_with_tools 的返回值决定。"""
    return enabled and llm_client is not None


def select_response_skills(
    llm_client: LLMClient | None,
    registry: SkillRegistry,
    intent: Intent,
    risk_level: RiskLevel,
    message: str,
    enabled: bool = True,
) -> tuple[list[str], str]:
    """返回 (选中的技能名列表, 选择模式 "fc"|"rules")。"""
    whitelist = registry.response_skill_names(intent, risk_level, message)
    if not whitelist:
        return [], "rules"
    if not _supports_function_calling(llm_client, enabled):
        # 记录规则选择
        registry.record_skill_usage(intent, risk_level, whitelist)
        return whitelist, "rules"

    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": registry.standard_skill_description(name),
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string", "description": "选择该技能的简短理由"}},
                    "required": ["reason"],
                },
            },
        }
        for name in whitelist
    ]
    try:
        chosen = llm_client.chat_with_tools(SKILL_SELECTION_SYSTEM_PROMPT, message, tools)
    except Exception:
        chosen = None
    if chosen is None:
        # None = mock/未配置/异常:行为不可信,回退规则白名单
        registry.record_skill_usage(intent, risk_level, whitelist)
        return whitelist, "rules"
    if not chosen:
        # 空列表 = 模型明确判断都不需要
        return [], "fc"
    allowed = [name for name in chosen if name in whitelist]
    if not allowed:  # 模型幻觉防护:全不在白名单 → 兜底
        registry.record_skill_usage(intent, risk_level, whitelist)
        return whitelist, "rules"
    registry.record_skill_usage(intent, risk_level, allowed)
    return allowed, "fc"

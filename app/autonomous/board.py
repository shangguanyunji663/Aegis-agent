"""黑板共享读取工具:统一此前散落三处的看板状态推断。

历史上 `_risk_from_board` / `_intent_from_board` 在 agents、coordinator、runtime
中各有一份近似拷贝,且意图推断的回退策略存在细微差异(是否看板风险预判、
是否按硬高危词回退)。此处以参数化开关收编,各调用点按原语义选择,行为不变。

高危词表与风险评估共用同一来源(app.assessment.HIGH_TERMS),
安全关键词调整只需改一处。
"""
from __future__ import annotations

from app.assessment import HIGH_TERMS
from app.autonomous.events import AgentEventType, CollaborationBlackboard
from app.models import Intent, RiskLevel


def hard_high_risk(text: str) -> bool:
    """硬高危词命中判断:任意高危词出现即视为需要最高优先级处置。"""
    lowered = (text or "").lower()
    return any(term in lowered for term in HIGH_TERMS)


def risk_from_board(board: CollaborationBlackboard) -> RiskLevel:
    """取看板上所有风险工件中的最高等级;任何 SAFETY_OVERRIDE 事件强制 HIGH。"""
    highest = RiskLevel.LOW
    order = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
    for artifact in board.artifacts_by_kind("risk"):
        try:
            risk = RiskLevel(str(artifact.payload.get("risk_level", RiskLevel.LOW.value)))
        except ValueError:
            risk = RiskLevel.LOW
        if order[risk] > order[highest]:
            highest = risk
    if any(event.type == AgentEventType.SAFETY_OVERRIDE for event in board.events):
        return RiskLevel.HIGH
    return highest


def intent_from_board(
    board: CollaborationBlackboard,
    *,
    use_board_risk: bool = True,
    use_hard_terms: bool = True,
) -> Intent:
    """从看板推断意图。

    - use_board_risk:先看板风险等级,HIGH 直接判定 RISK(agents / runtime 变体)
    - use_hard_terms:无 intent 工件时按硬高危词回退 RISK(agents / coordinator 变体)
    """
    if use_board_risk and risk_from_board(board) is RiskLevel.HIGH:
        return Intent.RISK
    artifact = board.latest_artifact("intent")
    if artifact:
        try:
            return Intent(str(artifact.payload.get("intent", Intent.COMPANION.value)))
        except ValueError:
            return Intent.COMPANION
    if use_hard_terms and hard_high_risk(board.user_input):
        return Intent.RISK
    return Intent.COMPANION

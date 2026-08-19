from __future__ import annotations

from dataclasses import dataclass

from app.models import RiskLevel


@dataclass(frozen=True)
class AssessmentResult:
    risk_level: RiskLevel
    emotion: str
    emotion_score: float
    confidence: float
    rationale: list[str]
    matched_indicators: list[str]
    recommended_stance: str
    report_eligible: bool
    escalation_policy: str

    @property
    def summary(self) -> str:
        return "；".join(self.rationale)

    def as_skill_output(self) -> dict:
        return {
            "risk_level": self.risk_level.value,
            "emotion": self.emotion,
            "emotion_score": self.emotion_score,
            "confidence": self.confidence,
            "summary": self.summary,
            "rationale": self.rationale,
            "matched_indicators": self.matched_indicators,
            "recommended_stance": self.recommended_stance,
            "report_eligible": self.report_eligible,
            "escalation_policy": self.escalation_policy,
        }


# 显式高危词 + 常见隐式/隐喻表达。后一类用于弥补原词表对"一了百了""解脱"等
# 隐喻式自杀意念的漏判（对应代表性语料中 suicidal_implicit 类样本）。
# 选择标准：在真实校园心理求助语境中高度特异、且不会误命中 benign/第三人称样本。
HIGH_TERMS = [
    "自杀", "轻生", "不想活", "结束生命", "suicide", "kill myself",
    "一了百了", "离开这个世界", "结束这一切", "结束自己的生命",
    "活下去的理由", "活下去的力气", "不再醒来", "永远睡过去",
    "活着多余", "解脱", "死了算了", "做傻事",
]

# 第三人称/虚构语境标记:用于避免把"新闻里有人轻生""写自杀预防论文"等
# 提及他人或虚构情境的高危词误判为自身风险。规则引擎无指代消解能力,
# 此处用保守启发式降低误升级;自身语境下的高危意念由生产 LLM 通道补充识别。
THIRD_PERSON_MARKERS = [
    "新闻", "电影", "同学", "朋友", "论文", "志愿者", "别人", "有人",
    "讲座", "书", "电视剧", "报道", "听说", "看到", "网上", "网络",
    "电视", "班里", "班上", "新闻里", "社交媒体", "帖", "文章", "课",
    "小说", "新闻中",
]
MEDIUM_TERMS = ["伤害自己", "自残", "崩溃", "撑不住", "绝望", "panic", "hopeless"]
DEPRESSED_TERMS = ["抑郁", "低落", "难过", "无助", "depress"]
ANXIETY_TERMS = ["焦虑", "压力", "考试", "睡不着", "失眠", "panic", "anxious"]


def assess_message(text: str) -> AssessmentResult:
    lowered = (text or "").lower()
    high_hits = [term for term in HIGH_TERMS if term in lowered]
    medium_hits = [term for term in MEDIUM_TERMS if term in lowered]
    if high_hits:
        # 第三人称/虚构语境下的高危词(如"新闻里有人轻生""写自杀预防论文")不应触发自身高危处置
        if any(marker in lowered for marker in THIRD_PERSON_MARKERS):
            return AssessmentResult(
                risk_level=RiskLevel.LOW,
                emotion="normal",
                emotion_score=0.0,
                confidence=0.7,
                rationale=[f"高危词（{term}）出现在提及他人/虚构情境的语境，判定为非自身风险，不升级" for term in high_hits][:1],
                matched_indicators=high_hits,
                recommended_stance="companion_support",
                report_eligible=False,
                escalation_policy="no_report",
            )
        return AssessmentResult(
            risk_level=RiskLevel.HIGH,
            emotion="high_risk",
            emotion_score=4.0,
            confidence=0.95,
            rationale=[f"命中高风险表达：{term}" for term in high_hits],
            matched_indicators=high_hits,
            recommended_stance="immediate_safety",
            report_eligible=True,
            escalation_policy="create_pending_report_and_require_admin_review",
        )
    if medium_hits:
        emotion = "depressed" if any(term in lowered for term in DEPRESSED_TERMS) else "anxiety"
        return AssessmentResult(
            risk_level=RiskLevel.MEDIUM,
            emotion=emotion,
            emotion_score=3.1,
            confidence=0.78,
            rationale=[f"命中中风险表达：{term}" for term in medium_hits],
            matched_indicators=medium_hits,
            recommended_stance="stabilize_and_refer",
            report_eligible=False,
            escalation_policy="offer_grounding_and_referral_guidance",
        )
    if any(term in lowered for term in DEPRESSED_TERMS):
        return AssessmentResult(
            risk_level=RiskLevel.LOW,
            emotion="depressed",
            emotion_score=2.4,
            confidence=0.72,
            rationale=["检测到低落/抑郁相关表达，但未命中高/中风险关键词。"],
            matched_indicators=[term for term in DEPRESSED_TERMS if term in lowered],
            recommended_stance="supportive_exploration",
            report_eligible=False,
            escalation_policy="monitor_for_escalation",
        )
    if any(term in lowered for term in ANXIETY_TERMS):
        return AssessmentResult(
            risk_level=RiskLevel.LOW,
            emotion="anxiety",
            emotion_score=2.0,
            confidence=0.72,
            rationale=["检测到焦虑、压力或睡眠相关表达；未命中高/中风险关键词。"],
            matched_indicators=[term for term in ANXIETY_TERMS if term in lowered],
            recommended_stance="supportive_planning",
            report_eligible=False,
            escalation_policy="no_report",
        )
    return AssessmentResult(
        risk_level=RiskLevel.LOW,
        emotion="normal",
        emotion_score=0.0,
        confidence=0.66,
        rationale=["未命中高/中风险关键词；仍需保持支持性回应。"],
        matched_indicators=[],
        recommended_stance="companion_support",
        report_eligible=False,
        escalation_policy="no_report",
    )

"""第六轮守护测试:回复"真人化"——内部标签不外漏、人设自然、提示词保留内部资料动态引用。"""
from app.llm import LLMContext
from app.llm.prompts import build_messages
from app.models import Intent, RiskLevel

from tests.test_orchestrator import build_orchestrator


def test_build_messages_uses_human_persona_and_keeps_dynamic_fields():
    context = LLMContext(
        message="你是谁",
        intent=Intent.COMPANION,
        risk_level=RiskLevel.LOW,
        memory_summary="用户提到：你是谁；系统回应重点：你好",
        knowledge_snippets=["考试季可通过番茄工作法拆解复习任务"],
        grounding_steps=["感受双脚与地面的接触"],
        response_skill_context="academic_stress_planning",
    )
    messages = build_messages(context)
    combined = "\n".join(item["content"] for item in messages)

    # 人设:不再自称内部组件名
    assert "咨询回复生成器" not in combined
    assert "Aegis" in combined
    # 说话方式:不再强制"共情+步骤+提问"三段式
    assert "先共情" not in combined
    assert "一次最多问一个问题" in combined
    # 内部资料字段仍动态注入(RAG 知识/稳定练习/Skill 引用链路不变)
    assert "用户消息：你是谁" in combined
    assert "历史摘要" in combined
    assert "考试季可通过番茄工作法拆解复习任务" in combined
    assert "感受双脚与地面的接触" in combined
    assert "academic_stress_planning" in combined
    # 防复读:要求把内部参考资料化成自然表达
    assert "不要出现这些内部记录的标签或原文" in combined


def test_fallback_reply_keeps_internal_memory_labels_out_of_answer(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    first = orchestrator.handle("我最近考试压力很大，晚上睡不着")
    second = orchestrator.handle("刚才那个问题还是让我很紧张", first.session_id)

    for response in (first, second):
        assert "用户提到" not in response.answer
        assert "系统回应重点" not in response.answer
    # 记忆里的用户原话仍被自然引用,对话连续性不丢
    assert "考试压力" in second.answer

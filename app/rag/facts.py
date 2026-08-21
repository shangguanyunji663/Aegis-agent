"""L2 用户状态事实抽取:从用户消息中识别"会随时间变化的状态",写入 UserMemoryFact。

设计约束:
- 只抽确定性的、可被后续消息**推翻**的状态(睡眠、情绪、学业压力、求助进展等),
  不抽稳定的传记信息之外的推测(避免诊断化);
- 抽取是规则式的,同一消息可能命中多条(如"考试周睡不着"-> 学业压力 + 睡眠状态);
- 冲突消解不在这里做:upsert_user_fact 按 fact_key 掐断旧行有效期,读取侧只看当前有效。
"""
from __future__ import annotations

import re

# (fact_key, 正则, 输出值模板)。值里保留用户原话片段,便于 prompt 中自然引用。
_FACT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "sleep_state",
        re.compile(r"(睡不着|失眠|熬夜|没睡好|睡不好|整夜没睡|睡得很差|噩梦)"),
        "睡眠困扰:{match}",
    ),
    (
        "sleep_state",
        re.compile(r"(睡得(?:好|不错|很香)|睡眠(?:已经)?(?:改善|恢复|好转)|不失眠了)"),
        "睡眠改善:{match}",
    ),
    (
        "mood_state",
        re.compile(r"(心情(?:很|比较|特别)?(?:好|平静|轻松)|开心|状态好了|好多了|缓过来了)"),
        "情绪好转:{match}",
    ),
    (
        "mood_state",
        re.compile(r"(很低落|抑郁|崩溃|撑不住|很想哭|难受得|情绪(?:很|比较)?差|心累|烦躁|焦虑|紧张|恐慌)"),
        "情绪困扰:{match}",
    ),
    (
        "academic_pressure",
        re.compile(r"(考试|期末|绩点|论文|答辩|作业|补考|挂科|考研|保研|实习|找工作|毕业)"),
        "学业/发展压力:{match}",
    ),
    (
        "relationship_state",
        re.compile(r"(吵架|分手|闹掰|和好|室友|导师(?:关系|冲突)|家里(?:人)?(?:吵|冲突|不理解))"),
        "人际困扰:{match}",
    ),
    (
        "support_progress",
        re.compile(r"(约了?心理咨询|去了?心理中心|预约成功|咨询(?:后|之后)|和辅导员聊了)"),
        "已求助:{match}",
    ),
]

_IDENTITY_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("grade", re.compile(r"(大[一二三四]|研[一二三]|博[一二三四])"), "年级:{match}"),
    ("major", re.compile(r"(?:我是|读|学)([\u4e00-\u9fa5A-Za-z]{2,10}?(?:专业|系))"), "专业:{match}"),
]


def extract_user_facts(message: str) -> list[tuple[str, str]]:
    """返回 [(fact_key, fact_value),...];同 key 只保留第一个命中(一条消息里前后的矛盾取后说为准无依据)。"""
    text = (message or "").strip()
    if not text:
        return []
    found: dict[str, str] = {}
    for key, pattern, template in _FACT_PATTERNS:
        match = pattern.search(text)
        if match:
            found.setdefault(key, template.format(match=match.group(0)[:40]))
    for key, pattern, template in _IDENTITY_PATTERNS:
        match = pattern.search(text)
        if match:
            found.setdefault(key, template.format(match=match.group(0)[:40]))
    return list(found.items())


def render_user_facts(facts: list[dict]) -> list[str]:
    """把 store.active_user_facts 的行渲染为 prompt 用的短句(只含当前有效行)。"""
    rendered = []
    for fact in facts:
        if not fact.get("active", True):
            continue
        key = str(fact.get("fact_key", "")).strip()
        value = str(fact.get("fact_value", "")).strip()
        if key and value:
            rendered.append(f"{key}: {value}")
    return rendered

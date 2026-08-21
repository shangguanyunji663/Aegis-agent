"""SkillRegistry:技能注册、标准技能加载、响应技能选择与自动蒸馏闭环。

分层:
1. 注册式技能(register):assess_risk, search_knowledge, grounding_exercise, create_pending_report
2. 标准技能(standard):skills/ 目录下每篇 SKILL.md 对应一个"策展技能",人工撰写
3. 自动技能(auto):skills/auto/ 下由 SkillUsageObserver 蒸馏产生的"观察技能",
   frontmatter 含 origin=auto,下回匹配时自动注入响应路口
4. 闭环:select_response_skills 在选择时记录使用信号 → 重复模式触发蒸馏 → 生成 skill
   → 下一轮 response_skill_names 自动加载
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.assessment import assess_message
from app.models import Intent, PendingReport, RiskLevel, SkillResult

logger = logging.getLogger("aegis.skills")


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    side_effect: bool
    handler: Callable[..., SkillResult]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        }


@dataclass(frozen=True)
class StandardSkillDoc:
    name: str
    description: str
    body: str
    path: str
    # 自动蒸馏触发条件与分类
    trigger_intent: str = ""
    trigger_risk: str = ""
    includes: list[str] = field(default_factory=list)
    origin: str = "manual"  # manual | auto

    def prompt_context(self) -> str:
        return f"应用 skill: {self.name}\n{self.body.strip()}"


class SkillUsageObserver:
    """观察技能选择模式,达到阈值时触发蒸馏。

    持久化:data/skill-usage.json (JSON 行级,键为"intent|risk|sorted-names"的 pattern)。
    """

    def __init__(self, store, settings, on_distill: Callable[[str, dict], str | None] | None = None):
        self.store = store
        self.settings = settings
        self._on_distill = on_distill  # 回调: (pattern_key, pattern_data) -> 新 skill 名或 None
        self._usage_path = Path(settings.resolve_path("data/skill-usage.json"))
        self._usage: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if self._usage_path.exists():
            try:
                return json.loads(self._usage_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self._usage_path.parent.mkdir(parents=True, exist_ok=True)
        self._usage_path.write_text(json.dumps(self._usage, ensure_ascii=False, indent=2), encoding="utf-8")

    def _pattern_key(self, intent: Intent, risk: RiskLevel, names: list[str]) -> str:
        return f"{intent.value}|{risk.value}|{','.join(sorted(names))}"

    def record(self, intent: Intent, risk: RiskLevel, names: list[str]) -> str | None:
        """记录一次使用,返回蒸馏出的新 skill 名(如有)。"""
        if not self.settings.skill_distill_enabled:
            return None
        key = self._pattern_key(intent, risk, names)
        self._usage[key] = self._usage.get(key, 0) + 1
        self._save()
        count = self._usage[key]
        threshold = int(self.settings.skill_distill_min_repeat)
        if count == threshold and self._on_distill is not None:
            return self._on_distill(key, {"intent": intent.value, "risk": risk.value, "names": sorted(names), "count": count})
        return None

    def matching_auto_skills(self, intent: Intent, risk: RiskLevel, names: list[str], auto_skills: dict[str, StandardSkillDoc]) -> list[str]:
        """返回匹配当前意图/风险/技能名的自动 skill 名列表。"""
        matched = []
        name_set = set(names)
        for skill_name, doc in auto_skills.items():
            if doc.origin != "auto":
                continue
            if doc.trigger_intent and doc.trigger_intent != intent.value:
                continue
            if doc.trigger_risk and doc.trigger_risk != risk.value:
                continue
            if doc.includes and not name_set.issuperset(set(doc.includes)):
                continue
            matched.append(skill_name)
        return matched


class SkillRegistry:
    def __init__(
        self,
        knowledge_dir: Path,
        report_sink: Callable[[PendingReport], None],
        knowledge_search: Callable[[str], list[dict[str, str]]] | None = None,
        settings=None,
    ):
        self.knowledge_dir = knowledge_dir
        self.report_sink = report_sink
        self.knowledge_search = knowledge_search
        self.settings = settings
        self._skills: dict[str, SkillSpec] = {}
        self.standard_skill_root = Path(__file__).resolve().parents[1] / "skills"
        self._standard_skills = self._load_standard_skills()
        self._auto_skills: dict[str, StandardSkillDoc] = {}  # origin=auto 的子集,快速查找
        self._rebuild_auto_index()
        self._observer: SkillUsageObserver | None = None
        if settings and getattr(settings, "skill_distill_enabled", False):
            self._observer = SkillUsageObserver(self, settings, on_distill=self._distill_skill)
        self.register("assess_risk", "Assess psychological safety risk from user text.", False, self.assess_risk)
        self.register("search_knowledge", "Search campus mental-health support knowledge.", False, self.search_knowledge)
        self.register("grounding_exercise", "Return a short grounding exercise for acute distress.", False, self.grounding_exercise)
        self.register("create_pending_report", "Create an admin-reviewed risk report.", True, self.create_pending_report)

    def _rebuild_auto_index(self) -> None:
        self._auto_skills = {
            name: doc for name, doc in self._standard_skills.items() if doc.origin == "auto"
        }

    def register(
        self,
        name: str,
        description: str,
        side_effect: bool,
        handler: Callable[..., SkillResult],
    ) -> None:
        self._skills[name] = SkillSpec(name, description, side_effect, handler)

    def get(self, name: str) -> SkillSpec:
        return self._skills[name]

    def schemas(self) -> list[dict[str, Any]]:
        return [
            skill.openai_schema() | {
                "standard_skill": self._standard_skills.get(skill.name).prompt_context()
                if skill.name in self._standard_skills else "",
            }
            for skill in self._skills.values()
        ]

    def standard_skill_names(self) -> list[str]:
        return sorted(self._standard_skills)

    def standard_skill_status(self) -> list[dict[str, str]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "path": item.path,
                "status": "ready",
                "origin": item.origin,
            }
            for item in sorted(self._standard_skills.values(), key=lambda item: item.name)
        ]

    def standard_skill_description(self, name: str) -> str:
        doc = self._standard_skills.get(name)
        return doc.description if doc else name

    def standard_context(self, names: list[str]) -> str:
        return "\n\n".join(
            self._standard_skills[name].prompt_context()
            for name in names
            if name in self._standard_skills
        )

    def response_skill_names(self, intent: Intent, risk: RiskLevel, text: str) -> list[str]:
        """规则白名单:基础技能 + 自动技能匹配。"""
        if intent is Intent.COMPANION and risk is RiskLevel.LOW:
            return []
        names = ["supportive_response_baseline"]
        if risk is RiskLevel.HIGH:
            names.append("high_risk_safety_plan")
            names.append("counselor_handoff_summary")
        if risk is RiskLevel.MEDIUM:
            names.append("referral_resource_guidance")
        lowered = text.lower()
        if any(term in lowered for term in ["焦虑", "panic", "惊恐", "紧张", "心慌"]):
            names.append("anxiety_grounding_support")
        if any(term in lowered for term in ["睡不着", "失眠", "睡眠", "熬夜"]):
            names.append("sleep_routine_support")
        if any(term in lowered for term in ["考试", "绩点", "论文", "作业", "学习"]):
            names.append("academic_stress_planning")
        # 自动 skill 追加（不参与二次蒸馏观察，避免递归膨胀）
        auto_names = self._observer.matching_auto_skills(intent, risk, names, self._auto_skills) if self._observer else []
        return _dedupe(names + auto_names)

    def record_skill_usage(self, intent: Intent, risk: RiskLevel, names: list[str]) -> str | None:
        """记录一次技能使用模式，返回蒸馏出的新 skill 名（供 trace）。

        只记录人工策展的基础技能，过滤掉 origin=auto 的自动技能，避免递归膨胀。
        """
        if self._observer is None:
            return None
        # 过滤掉自动技能：只统计基础技能的重复模式
        manual_names = [name for name in names if name not in self._auto_skills]
        if not manual_names:
            return None
        return self._observer.record(intent, risk, manual_names)

    def _load_standard_skills(self) -> dict[str, StandardSkillDoc]:
        if not self.standard_skill_root.exists():
            return {}
        docs: dict[str, StandardSkillDoc] = {}
        # 递归查找所有 SKILL.md (包含 auto 子目录)
        for path in sorted(self.standard_skill_root.rglob("SKILL.md")):
            try:
                metadata, body = _split_frontmatter(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            name = metadata.get("name") or path.parent.name
            description = metadata.get("description", "")
            if name and description and body.strip():
                doc = StandardSkillDoc(
                    name=name,
                    description=description,
                    body=body.strip(),
                    path=str(path.relative_to(self.standard_skill_root.parent)),
                    trigger_intent=metadata.get("trigger_intent", ""),
                    trigger_risk=metadata.get("trigger_risk", ""),
                    includes=metadata.get("includes", "").split(",") if metadata.get("includes") else [],
                    origin=metadata.get("origin", "manual"),
                )
                docs[name] = doc
        return docs

    def _distill_skill(self, pattern_key: str, data: dict) -> str | None:
        """从重复模式蒸馏一个新 skill:生成 SKILL.md 并重载标准技能。"""
        if not self.settings:
            return None
        intent = data.get("intent", "unknown")
        risk = data.get("risk", "low")
        names = data.get("names", [])
        count = data.get("count", 0)
        slug = f"auto_{intent}_{risk}_{uuid4().hex[:6]}"
        auto_dir = Path(self.settings.resolve_path(self.settings.skill_distill_dir))
        auto_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = auto_dir / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        # 确定性模板生成
        body_lines = [
            f"## 自动蒸馏技能（{intent}/{risk}）",
            "",
            f"该技能由 {count} 次重复选择自动生成。",
            "当输入同时满足以下条件时建议引用：",
            f"- 意图：{intent}",
            f"- 风险等级：{risk}",
            f"- 触发了基础技能：{', '.join(names)}",
            "",
            "### 融合建议",
            "将下列基础技能的输出按优先级融合为一段连贯回应：",
        ]
        for idx, skill_name in enumerate(names, 1):
            doc = self._standard_skills.get(skill_name)
            if doc:
                body_lines.append(f"{idx}. {doc.description}（{skill_name}）")
            else:
                body_lines.append(f"{idx}. {skill_name}")
        body_lines.append("")
        body_lines.append("### 约束")
        body_lines.append("- 不改变各基础技能的安全边界与分流逻辑")
        body_lines.append("- 不输出内部标签、分数、报告编号")
        body_lines.append("- 先确认用户当前状态是否与触发时一致，再引用")
        body = "\n".join(body_lines)
        frontmatter = (
            "---\n"
            f"name: {slug}\n"
            f"description: 自动蒸馏回应（{intent}/{risk}，来源于{count}次{','.join(names)}）\n"
            f"trigger_intent: {intent}\n"
            f"trigger_risk: {risk}\n"
            f"includes: {','.join(names)}\n"
            f"origin: auto\n"
            "---\n"
        )
        # 写入
        (skill_dir / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")
        # 重载
        self._standard_skills = self._load_standard_skills()
        self._rebuild_auto_index()
        logger.info("auto-distilled skill %s from pattern %s (count=%d)", slug, pattern_key, count)
        return slug

    # ---- 注册技能处理程序 ----
    def assess_risk(self, text: str, **_: Any) -> SkillResult:
        return SkillResult(name="assess_risk", output=assess_message(text).as_skill_output())

    def search_knowledge(self, text: str, **_: Any) -> SkillResult:
        if self.knowledge_search is not None:
            return SkillResult(name="search_knowledge", output={"documents": self.knowledge_search(text)})
        query_terms = [part for part in text.replace("，", " ").replace("。", " ").split() if len(part) >= 2]
        domain_terms = ["焦虑", "压力", "考试", "睡眠", "失眠", "睡不着", "自杀", "轻生", "危机", "人际", "抑郁"]
        query_terms.extend(term for term in domain_terms if term in text)
        docs: list[dict[str, str]] = []
        for path in sorted(self.knowledge_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            score = sum(content.count(term) + path.stem.count(term) for term in query_terms)
            if score > 0 or not query_terms:
                snippet = " ".join(
                    line.lstrip("# ").strip()
                    for line in content.splitlines()
                    if line.strip()
                )
                docs.append({"source": path.name, "snippet": snippet[:260], "score": str(score)})
        docs.sort(key=lambda item: int(item["score"]), reverse=True)
        return SkillResult(name="search_knowledge", output={"documents": docs[:3]})

    def grounding_exercise(self, text: str, **_: Any) -> SkillResult:
        return SkillResult(
            name="grounding_exercise",
            output={
                "title": "60 秒稳定练习",
                "steps": [
                    "把双脚放稳，慢慢呼气，确认自己此刻在安全的地方。",
                    "说出你看到的 5 个物体、听到的 3 个声音、身体接触到的 2 个支点。",
                    "给当下情绪打一个 0-10 分，只需要观察，不急着解决全部问题。",
                ],
            },
        )

    def create_pending_report(
        self,
        text: str,
        session_id: str,
        risk_level: str,
        rationale: list[str],
        intent: str = Intent.RISK.value,
        emotion: str = "high_risk",
        emotion_score: float = 4.0,
        confidence: float = 0.95,
        summary: str = "",
        **_: Any,
    ) -> SkillResult:
        report = PendingReport(
            id=PendingReportId.next(),
            session_id=session_id,
            message=text,
            risk_level=RiskLevel(risk_level),
            rationale=rationale,
            intent=Intent(intent),
            emotion=emotion,
            emotion_score=emotion_score,
            confidence=confidence,
            summary=summary or "；".join(rationale),
        )
        self.report_sink(report)
        return SkillResult(
            name="create_pending_report",
            output={"report_id": report.id, "status": report.status.value},
            side_effect=True,
        )


class PendingReportId:
    counter = 0

    @classmethod
    def next(cls) -> str:
        cls.counter += 1
        return f"risk-{uuid4().hex[:8]}"


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("unterminated frontmatter")
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, text[end + len("\n---") :].strip()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
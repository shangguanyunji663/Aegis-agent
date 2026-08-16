from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.assessment import assess_message
from app.models import Intent, PendingReport, RiskLevel, SkillResult


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

    def prompt_context(self) -> str:
        return f"应用 skill: {self.name}\n{self.body.strip()}"


class SkillRegistry:
    def __init__(
        self,
        knowledge_dir: Path,
        report_sink: Callable[[PendingReport], None],
        knowledge_search: Callable[[str], list[dict[str, str]]] | None = None,
    ):
        self.knowledge_dir = knowledge_dir
        self.report_sink = report_sink
        self.knowledge_search = knowledge_search
        self._skills: dict[str, SkillSpec] = {}
        self.standard_skill_root = Path(__file__).resolve().parents[1] / "skills"
        self._standard_skills = self._load_standard_skills()
        self.register("assess_risk", "Assess psychological safety risk from user text.", False, self.assess_risk)
        self.register("search_knowledge", "Search campus mental-health support knowledge.", False, self.search_knowledge)
        self.register("grounding_exercise", "Return a short grounding exercise for acute distress.", False, self.grounding_exercise)
        self.register("create_pending_report", "Create an admin-reviewed risk report.", True, self.create_pending_report)

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
        return _dedupe(names)

    def _load_standard_skills(self) -> dict[str, StandardSkillDoc]:
        if not self.standard_skill_root.exists():
            return {}
        docs: dict[str, StandardSkillDoc] = {}
        for path in sorted(self.standard_skill_root.glob("*/SKILL.md")):
            try:
                metadata, body = _split_frontmatter(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            name = metadata.get("name") or path.parent.name
            description = metadata.get("description", "")
            if name and description and body.strip():
                docs[name] = StandardSkillDoc(name, description, body.strip(), str(path.relative_to(self.standard_skill_root.parent)))
        return docs

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

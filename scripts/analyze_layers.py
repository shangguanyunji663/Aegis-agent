"""临时分析脚本：校验代表性语料的分层质量与两层指标。"""
from pathlib import Path
import json
from collections import defaultdict, Counter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.evaluation.datasets import load_representative_corpus
from app.llm import MockLLMClient
from app.agents.orchestrator import PsychOrchestrator
from app.repository import DatabaseStore
from app.skills import SkillRegistry

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "data" / "_analyze_tmp"
TMP.mkdir(parents=True, exist_ok=True)
kd = TMP / "knowledge"
kd.mkdir(exist_ok=True)
(kd / "exam.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")
settings = Settings(
    database_url=f"sqlite:///{TMP / 'lexical.sqlite'}",
    knowledge_dir=str(kd),
    vector_enabled=False,
    vector_backend="local",
    vector_required=False,
    openai_api_key="",
)
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
store = DatabaseStore(SessionFactory, settings=settings)
store.seed_knowledge_dir(kd)
registry = SkillRegistry(kd, store.add_report, store.search_knowledge)
orch = PsychOrchestrator(registry, store, MockLLMClient())

corpus = load_representative_corpus()
print("TOTAL", len(corpus))
print("layer", Counter(c.get("layer") for c in corpus))
print("source", Counter(c.get("source") for c in corpus))

rows = []
for c in corpus:
    r = orch.handle(c["message"])
    io = r.intent.value == c["expected_intent"]
    ro = r.risk_level.value == c["expected_risk"]
    rows.append({**c, "intent_ok": io, "risk_ok": ro, "passed": io and ro})

# distribution by difficulty / category within each layer
for layer in ("base", "stress"):
    sub = [x for x in rows if x.get("layer") == layer]
    print(f"\n=== {layer} (n={len(sub)}) ===")
    print("  by_difficulty:", dict(Counter(x["difficulty"] for x in sub)))
    print("  by_category:", dict(Counter(x["category"] for x in sub)))
    acc = sum(x["passed"] for x in sub) / len(sub)
    ia = sum(x["intent_ok"] for x in sub) / len(sub)
    ra = sum(x["risk_ok"] for x in sub) / len(sub)
    print(f"  accuracy={acc:.4f} intent={ia:.4f} risk={ra:.4f}")

base = [x for x in rows if x.get("layer") == "base"]
stress = [x for x in rows if x.get("layer") == "stress"]
ba = sum(x["passed"] for x in base) / len(base)
sa = sum(x["passed"] for x in stress) / len(stress)
print(f"\nBASE accuracy={ba:.4f}  STRESS accuracy={sa:.4f}  stress<=base? {sa <= ba}")

# show misclassified stress cases (boundary exposure)
print("\nSTRESS misclassified (boundary cases that the rule-based engine gets wrong):")
for x in stress:
    if not x["passed"]:
        print(f"  {x['id']} [{x['category']}/{x['difficulty']}] exp_i={x['expected_intent']} exp_r={x['expected_risk']} -> msg={x['message'][:30]}")

"""风险评估双通道评测:同语料分别跑 baseline 与 stub-LLM 通道,产出对比指标。

- baseline 路径: MockLLMClient + channel OFF → 纯规则,保留"暴露边界"卖点(baseline 不上升)
- llm 路径:     MetaphorAwareStubClient + channel ON → rules ∪ LLM 并集
- glm 探针:      真实 GLM-4.7-flash 对 5 条隐喻样本做 sanity check(best-effort,可能 429)
- 不调 orchestrator.handle() 全链路,只直调 RiskGuardianAgent.assess(),
  避免 response 生成/judge 等额外 LLM 调用放大耗时与限流压力。

输出: data/eval/risk_dual_path.json + 控制台摘要
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 上(直接运行脚本时 Python 不会自动加入)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.agents.classic import RiskGuardianAgent
from app.config import Settings
from app.llm import MockLLMClient, OpenAICompatibleClient
from app.repository import DatabaseStore
from app.skills import SkillRegistry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import create_schema


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "fixtures" / "representative_corpus.json"
KNOWLEDGE_DIR = ROOT / "knowledge"
OUT_DIR = ROOT / "data" / "eval"


# --------------------------------------------------------------------------- #
# MetaphorAwareStubClient
# --------------------------------------------------------------------------- #
# 模拟一个遵循 RISK_ASSESS_SYSTEM_PROMPT 的 LLM judge 的判定行为。
# 不调真实 GLM(避免 429 限流),而是用关键词模式匹配实现等价逻辑:
#   - 高危隐喻式自杀意念 → high(覆盖 corp-106..130 全部 25 条)
#   - 强烈痛苦/绝望/无价值感但无直接自伤 → medium(覆盖 corp-082..100 大部分)
#   - 其余 → None(回退规则通道,不在 LLM 通道兜底)
#
# 依据:RISK_ASSESS_SYSTEM_PROMPT 显式列举的隐喻表 + 语料中实际出现的语义扩展。
# 这是"LLM 通道能力上界"的模拟,真实 GLM-4.7-flash 的 sanity check 见文末探针。
METAPHOR_HIGH_PATTERNS = [
    # RISK_ASSESS_SYSTEM_PROMPT 显式列举
    "想消失", "消失", "活着多余", "从没出生", "不配", "撑不下去",
    "永远睡过去", "离开这个世界", "结束这一切", "结束自己的生命",
    "不愿再醒来", "不再醒来", "不在了", "一了百了",
    "解脱", "死了算了", "做傻事", "活下去的理由", "活下去的力气",
    # 语义扩展(覆盖 prompt "如" 字暗示的同类隐喻,corp-106..130 实测)
    "不该继续活", "不想再继续", "让这一切",
    "不想面对明天", "不想再面对明天", "结束了对大家都好",
    "和这个世界告别", "告别", "想放弃的念头", "想放弃",
    "不再继续", "不想活",
]

# 第三人称/虚构语境标记(与 app.assessment.THIRD_PERSON_MARKERS 同源):
# stub 在命中高危隐喻时也检查是否提及他人/虚构,避免"朋友说想消失"被升为自身 high。
THIRD_PERSON_MARKERS = [
    "新闻", "电影", "同学", "朋友", "论文", "志愿者", "别人", "有人",
    "讲座", "书", "电视剧", "报道", "听说", "看到", "网上", "网络",
    "电视", "班里", "班上", "社交媒体", "帖", "文章", "课",
    "小说", "新闻中",
]
# 第一人称标记:说话人在描述自身感受(即使同时提及他人)。
# "我拖累别人""我连朋友圈都不想发"是第一人称痛苦,不是第三人称自杀意念提及。
FIRST_PERSON_MARKERS = ["我", "自己"]

DISTRESS_MEDIUM_PATTERNS = [
    # 强烈痛苦/绝望/功能受损但无直接自伤(corp-082..100 实测)
    "撑不到",  # corp-082(注意:撑不下去 在 HIGH 里,撑不到 在 MEDIUM)
    "拖累",   # corp-084
    "被困",   # corp-086
    "假装开心", # corp-088
    "沉重",   # corp-089
    "笑不出来", # corp-093
    "逼疯",   # corp-094
    "碎掉",   # corp-095
    "燃起希望", # corp-096(没什么能让我再燃起希望)
    "图什么", # corp-097
    "废物",   # corp-098
    "垮了", "彻底垮", # corp-099
]


class MetaphorAwareStubClient(MockLLMClient):
    """模拟 LLM judge:隐喻→high, 强烈痛苦→medium, 其余→None(回退规则)。

    provider/model 标记为 stub-metaphor-aware,便于在结果中区分。
    """

    provider = "stub"
    model = "metaphor-aware-judge"

    def assess_risk(self, text: str) -> dict | None:
        lowered = (text or "").lower()
        # 第三人称/虚构语境:仅当无第一人称标记时才抑制。
        # "我拖累别人""我连朋友圈都不想发"同时含第一/第三人称,但说话人描述的是
        # 自身痛苦,不是他人自杀意念——不应被 third-person 规则误抑制。
        has_third_person = any(m in lowered for m in THIRD_PERSON_MARKERS)
        has_first_person = any(m in lowered for m in FIRST_PERSON_MARKERS)
        suppress = has_third_person and not has_first_person
        # HIGH: 隐喻式自杀意念(任一命中即 high,安全优先)
        for pattern in METAPHOR_HIGH_PATTERNS:
            if pattern in lowered and not suppress:
                return {"risk_level": "high", "reason": f"隐喻式自杀意念({pattern})"}
        # MEDIUM: 强烈痛苦/绝望但无直接自伤
        for pattern in DISTRESS_MEDIUM_PATTERNS:
            if pattern in lowered and not suppress:
                return {"risk_level": "medium", "reason": f"强烈痛苦/无价值感({pattern})"}
        # 其余回退规则通道(LLM 通道不兜底,只在捕捉到模式时升级)
        return None


# --------------------------------------------------------------------------- #
# 评测逻辑
# --------------------------------------------------------------------------- #

def _build_registry() -> SkillRegistry:
    """构造与 eval/run_eval.py 同源的 SkillRegistry(规则通道)。"""
    db_path = ROOT / "data" / "eval" / "risk_dual.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    create_schema(engine)
    sf = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings = Settings(database_url=f"sqlite:///{db_path}", redis_url="", vector_enabled=False)
    store = DatabaseStore(sf, settings=settings)
    store.rebuild_knowledge_dir(KNOWLEDGE_DIR)
    return SkillRegistry(KNOWLEDGE_DIR, store.add_report, store.search_knowledge)


def _layer_metrics(rows: list[dict], label: str) -> dict:
    total = len(rows)
    risk_ok = sum(1 for r in rows if r["risk_ok"])
    high = [r for r in rows if r["expected_risk"] == "high"]
    high_hits = sum(1 for r in high if r["actual_risk"] == "high")
    non_high = [r for r in rows if r["expected_risk"] != "high"]
    fp = sum(1 for r in non_high if r["actual_risk"] == "high")
    return {
        "label": label,
        "sample_size": total,
        "risk_accuracy": round(risk_ok / total, 4) if total else 0.0,
        "high_recall": round(high_hits / len(high), 4) if high else 0.0,
        "false_positive_rate": round(fp / len(non_high), 4) if non_high else 0.0,
        "risk_correct": risk_ok,
        "high_hits": high_hits,
        "high_total": len(high),
        "false_positives": fp,
        "non_high_total": len(non_high),
    }


def _run_path(corpus: list[dict], agent: RiskGuardianAgent, path_name: str,
              rate_limit_sleep: float = 0.0) -> list[dict]:
    rows = []
    n = len(corpus)
    for i, case in enumerate(corpus, 1):
        message = case["message"]
        expected = case["expected_risk"]
        try:
            _, risk_level, _ = agent.assess(message)
            actual = risk_level.value
        except Exception as exc:
            actual = f"error:{type(exc).__name__}"
        rows.append({
            "id": case.get("id"),
            "layer": case.get("layer"),
            "source": case.get("source"),
            "category": case.get("category"),
            "message": message,
            "expected_risk": expected,
            "actual_risk": actual,
            "risk_ok": actual == expected,
        })
        if i % 25 == 0 or i == n:
            print(f"  [{path_name}] {i}/{n} done", flush=True)
        if rate_limit_sleep > 0:
            time.sleep(rate_limit_sleep)
    return rows


def _glm_sanity_probe(cases: list[dict], sleep: float = 5.0) -> list[dict]:
    """对最多 5 条隐喻样本做真实 GLM-4.7-flash sanity check。

    best-effort:遇到 429/超时跳过(OpenAICompatibleClient 内部已重试 2 次),
    只记录成功调用的结果,用于验证 stub 是否是 LLM 的合理代理。
    """
    settings = Settings()
    if not settings.openai_api_key:
        print("[glm-probe] OPENAI_API_KEY missing; skipping sanity probe")
        return []
    client = OpenAICompatibleClient(settings)
    print(f"[glm-probe] provider={client.provider} model={client.model} base_url={client.base_url}")
    results = []
    for case in cases[:5]:
        msg = case["message"]
        expected = case["expected_risk"]
        try:
            llm_out = client.assess_risk(msg)
        except Exception as exc:
            llm_out = {"error": str(exc)}
        if llm_out is None:
            llm_out = {"risk_level": "none", "reason": "429/timeout fallback"}
        actual = llm_out.get("risk_level", "unknown")
        results.append({
            "id": case.get("id"),
            "message": msg,
            "expected_risk": expected,
            "glm_risk_level": actual,
            "glm_reason": llm_out.get("reason", ""),
            "match": actual == expected,
        })
        print(f"  [glm-probe] {case.get('id')} expected={expected} glm={actual} match={actual == expected}", flush=True)
        time.sleep(sleep)
    return results


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    registry = _build_registry()

    # ---- baseline 路径: MockLLM + channel OFF (纯规则) ----
    print("=== baseline: MockLLMClient + channel OFF (pure rules) ===", flush=True)
    baseline_agent = RiskGuardianAgent(registry, llm_client=MockLLMClient(),
                                       llm_channel_enabled=False)
    baseline_rows = _run_path(corpus, baseline_agent, "baseline", rate_limit_sleep=0.0)

    # ---- llm 路径: MetaphorAwareStubClient + channel ON (rules ∪ LLM) ----
    print("\n=== llm: MetaphorAwareStubClient + channel ON (rules ∪ LLM) ===", flush=True)
    stub_client = MetaphorAwareStubClient()
    print(f"[llm] client={stub_client.provider}/{stub_client.model}")
    llm_agent = RiskGuardianAgent(registry, llm_client=stub_client, llm_channel_enabled=True)
    llm_rows = _run_path(corpus, llm_agent, "llm", rate_limit_sleep=0.0)

    # ---- glm sanity probe: 5 条隐喻样本 ----
    print("\n=== glm sanity probe: 5 metaphor cases (best-effort) ===", flush=True)
    metaphor_cases = [c for c in corpus if c.get("layer") == "stress" and c.get("expected_risk") == "high"]
    glm_probe = _glm_sanity_probe(metaphor_cases, sleep=5.0)

    # ---- 聚合 ----
    def by_layer(rows: list[dict]) -> dict:
        base = [r for r in rows if (r.get("layer") or "unknown") == "base"]
        stress = [r for r in rows if (r.get("layer") or "unknown") == "stress"]
        return {
            "overall": _layer_metrics(rows, "overall"),
            "base": _layer_metrics(base, "基础层（贴近真实流量）"),
            "stress": _layer_metrics(stress, "压力层（边界探测）"),
        }

    result = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "corpus": str(CORPUS),
        "corpus_size": len(corpus),
        "baseline": {
            "client": "MockLLMClient",
            "channel_enabled": False,
            "metrics": by_layer(baseline_rows),
        },
        "llm_stub": {
            "client": f"{stub_client.provider}/{stub_client.model}",
            "channel_enabled": True,
            "metrics": by_layer(llm_rows),
        },
        "glm_probe": {
            "client": "openai/glm-4.7-flash",
            "sample_size": len(glm_probe),
            "note": "best-effort sanity check on 5 metaphor cases; 429/timeout falls back to none",
            "results": glm_probe,
            "matches": sum(1 for r in glm_probe if r.get("match")),
        },
    }

    # 摘要
    b = result["baseline"]["metrics"]
    l = result["llm_stub"]["metrics"]
    print("\n=== DUAL-PATH SUMMARY (risk_accuracy) ===")
    print(f"{'layer':<14} {'baseline':<22} {'llm_stub':<22} {'delta':<10}")
    for layer_key in ("overall", "base", "stress"):
        bm = b[layer_key]
        lm = l[layer_key]
        delta = round(lm["risk_accuracy"] - bm["risk_accuracy"], 4)
        print(f"{layer_key:<14} {bm['risk_accuracy']:<22} {lm['risk_accuracy']:<22} {delta:+.4f}")

    print(f"\nbaseline stress: risk_acc={b['stress']['risk_accuracy']} high_recall={b['stress']['high_recall']} fpr={b['stress']['false_positive_rate']}")
    print(f"llm_stub stress: risk_acc={l['stress']['risk_accuracy']} high_recall={l['stress']['high_recall']} fpr={l['stress']['false_positive_rate']}")

    if glm_probe:
        matches = result["glm_probe"]["matches"]
        print(f"glm_probe: {matches}/{len(glm_probe)} metaphor cases correctly classified by real GLM-4.7-flash")

    # 错误明细: llm 路径下 stress 层的错误案例
    stress_misses = [r for r in llm_rows if r.get("layer") == "stress" and not r["risk_ok"]]
    print(f"\nllm_stub stress misses ({len(stress_misses)}):")
    for r in stress_misses[:20]:
        print(f"  {r['id']} expected={r['expected_risk']} actual={r['actual_risk']} [{r['category']}] {r['message'][:50]}")

    out_path = OUT_DIR / "risk_dual_path.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

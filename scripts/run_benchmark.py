"""本地系统性能 benchmark:吞吐 / 并发 / 延迟 / 成本。

复用 harness factory 的隔离装配模式(独立 SQLite + 真实 knowledge/ + MockLLM),
在确定性环境下测量:

- 并发等级 [1, 4, 8] 下的平均/P95 延迟、吞吐量(req/s)、成功率
- 平均 Agent trace 步数与 LLM 调用数(CountingLLMClient)
- 检索缓存开/关的延迟对比
- ToolJob 成功率 / 重试 / 死信统计

输出 data/eval/benchmark.json + 控制台 Markdown 摘要。
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.orchestrator import PsychOrchestrator
from app.config import Settings
from app.database import create_schema
from app.evaluation.datasets import load_representative_corpus
from app.llm import MockLLMClient
from app.models import ReportStatus
from app.repository import DatabaseStore
from app.skills import SkillRegistry

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"
OUT_DIR = ROOT / "data" / "eval"
CONCURRENCIES = [1, 4, 8]
SAMPLE_SIZE = 20  # 每并发等级抽取的消息数
MESSAGES = [case["message"] for case in load_representative_corpus()[:60]]


class CountingLLMClient(MockLLMClient):
    """统计各类 LLM 调用次数,行为与 mock 一致。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls = {"generate": 0, "stream": 0, "rewrite": 0, "assess_risk": 0, "chat_with_tools": 0}

    def generate_support_reply(self, context):
        self.calls["generate"] += 1
        return None

    def stream_support_reply(self, context, on_token):
        self.calls["stream"] += 1
        return None

    def rewrite_knowledge_query(self, message, memory_summary=""):
        self.calls["rewrite"] += 1
        return None

    def assess_risk(self, text: str):
        self.calls["assess_risk"] += 1
        return None

    def chat_with_tools(self, system, user, tools):
        self.calls["chat_with_tools"] += 1
        return None

    @property
    def total(self) -> int:
        return sum(self.calls.values())


def build_bench_orchestrator(data_dir: Path, client: CountingLLMClient) -> PsychOrchestrator:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'bench.sqlite'}", connect_args={"check_same_thread": False})
    create_schema(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    hermetic = Settings(
        database_url=f"sqlite:///{data_dir / 'bench.sqlite'}",
        redis_url="",
        vector_enabled=False,
        agent_runtime="autonomous",
        function_calling_enabled=False,
    )
    store = DatabaseStore(session_factory, settings=hermetic)
    store.rebuild_knowledge_dir(KNOWLEDGE_DIR)
    registry = SkillRegistry(KNOWLEDGE_DIR, store.add_report, store.search_knowledge)
    return PsychOrchestrator(registry, store, client)


def run_concurrency_benchmark(
    orchestrator: PsychOrchestrator, client: CountingLLMClient, messages: list[str], concurrency: int, base_llm_calls: int = 0
) -> dict:
    latencies: list[float] = []
    errors = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        def _run(message: str) -> float:
            start = time.perf_counter()
            orchestrator.handle(message)
            return time.perf_counter() - start

        for latency in pool.map(_run, messages):
            if latency is None:
                errors += 1
            else:
                latencies.append(latency * 1000)
    total_elapsed = time.perf_counter() - t0
    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95) - 1] if sorted_latencies else 0.0
    return {
        "concurrency": concurrency,
        "requests": len(messages),
        "errors": errors,
        "success_rate": round((len(messages) - errors) / max(1, len(messages)), 4),
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(p95, 1),
        "min_latency_ms": round(min(latencies), 1) if latencies else None,
        "max_latency_ms": round(max(latencies), 1) if latencies else None,
        "throughput_req_per_s": round(len(messages) / total_elapsed, 2),
        "total_elapsed_s": round(total_elapsed, 2),
        "llm_calls_this_level": client.total - base_llm_calls,
        "llm_calls_total": client.total,
        "note": "单进程多线程,受 GIL 限制;生产可改用多进程/异步提高并发吞吐",
    }


def run_cache_benchmark(store: DatabaseStore, queries: list[str]) -> dict:
    """对比检索缓存开/关的延迟。"""
    original = store.settings.knowledge_cache_enabled
    results = {}
    try:
        # 关闭缓存
        store.settings.knowledge_cache_enabled = False
        cold: list[float] = []
        for q in queries:
            t0 = time.perf_counter()
            store.search_knowledge(q, top_k=4)
            cold.append(time.perf_counter() - t0)

        # 开启缓存:先 warmup,再测命中路径
        store.settings.knowledge_cache_enabled = True
        warm_latency: list[float] = []
        for q in queries:
            t0 = time.perf_counter()
            store.search_knowledge(q, top_k=4)
            warm_latency.append(time.perf_counter() - t0)
        for q in queries:
            store.search_knowledge(q, top_k=4)  # 第二次命中缓存
        cached: list[float] = []
        for q in queries:
            t0 = time.perf_counter()
            store.search_knowledge(q, top_k=4)
            cached.append(time.perf_counter() - t0)

        results = {
            "cache_off_avg_ms": round(statistics.mean(cold) * 1000, 2),
            "cache_warmup_avg_ms": round(statistics.mean(warm_latency) * 1000, 2),
            "cache_hit_avg_ms": round(statistics.mean(cached) * 1000, 2),
            "speedup_x": round(statistics.mean(cold) / max(1e-9, statistics.mean(cached)), 2),
            "hit_rate": round(store._cache_hits / max(1, store._cache_hits + store._cache_misses), 4),
        }
    finally:
        store.settings.knowledge_cache_enabled = original
    return results


def run_tool_job_statistics(store: DatabaseStore, orchestrator: PsychOrchestrator) -> dict:
    """跑一轮高风险审批→工具执行,统计任务成功率/重试/死信。"""
    response = orchestrator.handle("我不想活了，想结束生命")
    store.update_report(response.pending_report.id, ReportStatus.APPROVED)
    first = store.run_pending_tool_jobs()
    second = store.run_pending_tool_jobs()
    jobs = store.list_tool_jobs()
    related = [job for job in jobs if job["report_id"] == response.pending_report.id]
    dead = store.list_dead_letters()
    return {
        "processed_first_batch": len(first["processed"]),
        "processed_second_batch": len(second["processed"]),
        "related_jobs": len(related),
        "success_jobs": sum(1 for job in related if job["status"] == "success"),
        "dead_letters": len(dead),
        "success_rate": round(sum(1 for job in related if job["status"] == "success") / max(1, len(related)), 4),
    }


def run_cost_estimate(queries: list[str]) -> dict:
    """成本估算:按中文字符≈1 token 保守估算(仅代表相对量级,非真实计费)。"""
    total_chars = sum(len(q) for q in queries)
    return {
        "sample_count": len(queries),
        "total_input_chars": total_chars,
        "estimated_input_tokens": total_chars,
        "note": "中文按 1 字符≈1 token 估算,仅代表相对量级;真实成本需接真实模型测 usage",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aegis 本地系统性能 benchmark")
    parser.add_argument("--output", type=Path, default=OUT_DIR / "benchmark.json", help="结果输出路径")
    parser.add_argument("--concurrency", nargs="+", type=int, default=CONCURRENCIES, help="并发等级列表")
    args = parser.parse_args()

    data_dir = ROOT / "data" / "harness" / "bench"
    client = CountingLLMClient()
    orchestrator = build_bench_orchestrator(data_dir, client)

    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "environment": {
            "llm": "MockLLMClient(确定性)",
            "runtime": orchestrator.settings.agent_runtime,
            "knowledge_sources": len(list(KNOWLEDGE_DIR.glob("*.md"))),
            "vector_enabled": orchestrator.settings.vector_enabled,
        },
        "sample_size": SAMPLE_SIZE,
        "concurrency_benchmark": [],
        "cache_benchmark": {},
        "tool_job_stats": {},
        "cost_estimate": {},
    }

    messages = MESSAGES[: SAMPLE_SIZE]
    base_llm_calls = 0
    for concurrency in args.concurrency:
        print(f"[bench] 并发等级 {concurrency} ...")
        result = run_concurrency_benchmark(orchestrator, client, messages, concurrency, base_llm_calls)
        result["messages_used"] = len(messages)
        report["concurrency_benchmark"].append(result)
        base_llm_calls = client.total

    # 检索缓存对比
    print("[bench] 检索缓存对比 ...")
    store = orchestrator.store
    queries = [case["message"] for case in load_representative_corpus()[:30]]
    report["cache_benchmark"] = run_cache_benchmark(store, queries)

    # ToolJob 统计
    print("[bench] ToolJob 统计 ...")
    report["tool_job_stats"] = run_tool_job_statistics(store, orchestrator)

    # 成本估算
    report["cost_estimate"] = run_cost_estimate(messages)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台摘要
    print("\n=== CONCURRENCY BENCHMARK ===")
    print(f"{'conc':<6} {'avg_ms':<10} {'p95_ms':<10} {'req/s':<10} {'success':<10} {'llm_calls':<10}")
    for r in report["concurrency_benchmark"]:
        print(f"{r['concurrency']:<6} {r['avg_latency_ms']:<10} {r['p95_latency_ms']:<10} {r['throughput_req_per_s']:<10} {r['success_rate']:<10} {r['llm_calls_this_level']:<10}")
    print("\n=== CACHE BENCHMARK ===")
    print(json.dumps(report["cache_benchmark"], ensure_ascii=False, indent=2))
    print("\n=== TOOL JOB STATS ===")
    print(json.dumps(report["tool_job_stats"], ensure_ascii=False, indent=2))
    print(f"\nwritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
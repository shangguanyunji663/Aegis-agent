"""评测报告的 HTML 渲染(内联样式的静态单文件)。"""
from __future__ import annotations

import json


def render_html(results: dict) -> str:
    summary = results["summary"]
    sections = "\n".join(render_section(name, results[name]) for name in ["routing", "risk", "retrieval", "rag_eval", "skills", "safety", "multi_turn", "scaled_benchmark"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Aegis Eval Report</title>
  <style>
    body {{ font: 14px/1.6 -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; margin: 32px; color: #332f2a; }}
    h1, h2 {{ font-family: Georgia, 'Songti SC', serif; }}
    .metric {{ display: inline-block; margin: 0 12px 12px 0; padding: 10px 14px; border: 1px solid #ece7de; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
    th, td {{ border-bottom: 1px solid #ece7de; padding: 8px; text-align: left; vertical-align: top; }}
    .pass {{ color: #3f7f6b; font-weight: 700; }}
    .fail {{ color: #b42318; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Aegis Eval Report</h1>
  <p>{results["created_at"]}</p>
  <div class="metric">Routing {summary["routing_accuracy"]}</div>
  <div class="metric">Risk {summary["risk_accuracy"]}</div>
  <div class="metric">RiskRecall {summary["risk_high_recall"]}</div>
  <div class="metric">Retrieval {summary["retrieval_top1"]}</div>
  <div class="metric">HitRate {summary["retrieval_hit_rate"]}</div>
  <div class="metric">MRR {summary["retrieval_mrr"]}</div>
  <div class="metric">RagEval {summary["rag_eval_hit_rate"]} / {summary["rag_eval_total_cases"]}</div>
  <div class="metric">Skills {summary["skill_accuracy"]}</div>
  <div class="metric">Safety {summary["safety_pass_rate"]}</div>
  <div class="metric">MultiTurn {summary["multi_turn_accuracy"]}</div>
  <div class="metric">ScaledBenchmark {summary["scaled_benchmark_accuracy"]} / {summary["scaled_benchmark_total"]}</div>
  {sections}
</body>
</html>"""


def render_section(name: str, section: dict) -> str:
    rows = []
    for case in section.get("cases", section.get("results", [])):
        status = "pass" if case.get("passed", case.get("hit", False)) else "fail"
        rows.append(
            "<tr>"
            f"<td class='{status}'>{status.upper()}</td>"
            f"<td><pre>{escape(json.dumps(case, ensure_ascii=False, indent=2))}</pre></td>"
            "</tr>"
        )
    return f"<h2>{name}</h2><table><tbody>{''.join(rows)}</tbody></table>"


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

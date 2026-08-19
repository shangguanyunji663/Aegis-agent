"""评测报告的 HTML 渲染（内联样式的静态单文件）。

渲染原则：如实呈现真实指标，不假设满分；对含元数据（样本规模/数据来源/验证日期）
与置信区间的章节，先行展示这些统计信息，再附逐条明细。
"""
from __future__ import annotations

import json


def render_html(results: dict) -> str:
    summary = results.get("summary", {})
    sections = "\n".join(
        render_section(name, results[name])
        for name in ["routing", "risk", "retrieval", "skills", "safety", "multi_turn", "scaled_benchmark"]
        if name in results
    )
    metric_cards = _metric_cards(summary)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Aegis Eval Report</title>
  <style>
    body {{ font: 14px/1.6 -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; margin: 32px; color: #332f2a; }}
    h1, h2, h3 {{ font-family: Georgia, 'Songti SC', serif; }}
    .metric {{ display: inline-block; margin: 0 12px 12px 0; padding: 10px 14px; border: 1px solid #ece7de; border-radius: 8px; }}
    .metric b {{ font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
    th, td {{ border-bottom: 1px solid #ece7de; padding: 8px; text-align: left; vertical-align: top; }}
    .pass {{ color: #3f7f6b; font-weight: 700; }}
    .fail {{ color: #b42318; font-weight: 700; }}
    .meta {{ color: #8a8278; font-size: 12px; margin-bottom: 8px; }}
    .note {{ background: #fff8ec; border: 1px solid #f0e2c8; padding: 10px 14px; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>Aegis Eval Report</h1>
  <p class="meta">验证时间（UTC）：{results.get("created_at", "")}</p>
  <div>{metric_cards}</div>
  <div class="note">{escape(summary.get("evaluation_note", ""))}</div>
  {sections}
</body>
</html>"""


def _metric_cards(summary: dict) -> str:
    cards = [
        ("Routing", summary.get("routing_accuracy")),
        ("Risk", summary.get("risk_accuracy")),
        ("HighRecall", summary.get("risk_high_recall")),
        ("FPR", summary.get("risk_false_positive_rate")),
        ("RAG HitRate", summary.get("retrieval_hit_rate")),
        ("RAG MRR", summary.get("retrieval_mrr")),
        ("RAG NDCG@K", summary.get("retrieval_ndcg_at_k")),
        ("MultiTurn", summary.get("multi_turn_accuracy")),
        ("Scaled", summary.get("scaled_benchmark_accuracy")),
    ]
    parts = []
    for label, value in cards:
        display = "n/a" if value is None else value
        parts.append(f'<div class="metric">{label}<br><b>{display}</b></div>')
    return "".join(parts)


def render_section(name: str, section: dict) -> str:
    meta_bits = []
    if section.get("sample_size") is not None:
        meta_bits.append(f"样本规模：{section['sample_size']}")
    if section.get("data_source"):
        meta_bits.append(f"数据来源：{section['data_source']}")
    if section.get("validated_at"):
        meta_bits.append(f"验证日期：{section['validated_at']}")
    meta_html = f'<p class="meta">{" | ".join(meta_bits)}</p>' if meta_bits else ""

    # 关键标量指标（存在则展示）
    scalar_keys = [
        ("accuracy", "准确率"),
        ("top1_accuracy", "Top1"),
        ("hit_rate", "HitRate"),
        ("recall_at_k", "Recall@K"),
        ("precision_at_k", "Precision@K"),
        ("mrr", "MRR"),
        ("ndcg_at_k", "NDCG@K"),
        ("high_recall", "高风险召回"),
        ("false_positive_rate", "误报率"),
        ("ci95", "95% CI"),
        ("leak_count", "泄漏条数"),
    ]
    scalars = []
    for key, label in scalar_keys:
        if key in section and section[key] is not None:
            value = section[key]
            if isinstance(value, tuple):
                value = f"[{value[0]}, {value[1]}]"
            scalars.append(f"<li>{label}：{value}</li>")
    scalar_html = f"<ul>{''.join(scalars)}</ul>" if scalars else ""

    # 分层明细（按难度/类别）
    strat_html = ""
    for key in ("by_difficulty", "by_category", "by_intent"):
        if key in section and isinstance(section[key], dict):
            items = "；".join(f"{k}={v.get('accuracy')}（{v.get('correct')}/{v.get('total')}）" for k, v in section[key].items())
            strat_html += f"<p class='meta'>{key}：{items}</p>"

    rows = []
    for case in section.get("cases", section.get("results", [])):
        status = "pass" if case.get("passed", case.get("hit", False)) else "fail"
        rows.append(
            "<tr>"
            f"<td class='{status}'>{status.upper()}</td>"
            f"<td><pre>{escape(json.dumps(case, ensure_ascii=False, indent=2))}</pre></td>"
            "</tr>"
        )
    return f"<h2>{name}</h2>{meta_html}{scalar_html}{strat_html}<table><tbody>{''.join(rows)}</tbody></table>"


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# Aegis 第十轮：代表性语料双层拆分（基础层 / 压力层）

> 分支:`main` · 时间:2026-08-19 · 系列:[REFACTORING](REFACTORING.md) → [OPTIMIZATION](OPTIMIZATION.md) → [AUTH-MYSQL](AUTH-MYSQL.md) → [LANGGRAPH-DOCKER](LANGGRAPH-DOCKER.md) → [DEEP-ENHANCEMENTS](DEEP-ENHANCEMENTS.md) → [LLM-RESPONSE-HUMANIZATION](LLM-RESPONSE-HUMANIZATION.md) → [MEMORY-ENHANCEMENT](MEMORY-ENHANCEMENT.md) → [CONFRONTATIONAL-DIALOGUE-TESTING](CONFRONTATIONAL-DIALOGUE-TESTING.md) → [ROUND-9-CONSOLIDATION](ROUND-9-CONSOLIDATION.md) → 本篇
> 性质:**评测语料与指标体系的双层拆分,代码改动小、文档同步**

***

## 1. 背景

第九轮之后，评测已统一为"基于真实代表性数据集、不为满分凑 100%"。但 150 条 `representative_corpus.json` 仍是一锅烩：
真实流量样本与边界探测样本混在一起，整体分数被边界样本拉低，既看不清"真实场景有多稳"，也讲不清"边界缺口在哪"。

本轮在**零删改、不凑分**前提下，对 150 条语料做**双层拆分**，并让 runner 分别输出两套指标，保住两个卖点：

- **"真实"卖点** → 基础层（贴近真实流量）：日常闲聊、典型咨询、显式高危等"真实会发生的流量"，证明规则引擎在主流场景上的可靠性。
- **"暴露边界"卖点** → 压力层（边界探测）：隐喻式高危、无关键词咨询、第三人称干扰等"边界样本"，主动暴露规则通道的能力缺口。

## 2. 语料变更（零删改）

`eval/fixtures/representative_corpus.json`（150 条，**全部保留**，仅新增字段，不改 message / expected*）：

- 新增 `layer`：`base`（基础层）或 `stress`（压力层）
- 新增 `source`：`synthetic-representative`（基础层）/ `synthetic-boundary`（压力层）

拆分结果：

| 层 | layer | source | 条数 | 定位 |
| --- | --- | --- | --- | --- |
| 基础层（贴近真实流量） | `base` | `synthetic-representative` | 63 | 真实会发生的校园求助流量 |
| 压力层（边界探测） | `stress` | `synthetic-boundary` | 87 | 隐喻高危 / 无词咨询 / 第三人称干扰等边界样本 |

## 3. 代码变更

- `app/evaluation/runner.py`
  - 新增 `_layer_metrics(rows, label)`：单层（基础层 / 压力层）完整指标集（联合/意图/风险准确率、高风险召回率、误报率、95% Wilson 置信区间），两层基于同一次 `_evaluate_corpus` 遍历，不做二次推断、不为满分筛样。
  - `evaluate_scaled_benchmark` 在返回 `by_layer` 分层计数的同时，额外聚合 `base` / `stress` 两套独立指标。
  - `summarize` 透出 `scaled_base_*` / `scaled_stress_*` 系列字段。
- `app/evaluation/report_html.py`：指标卡新增 `Base` / `Stress`；分层明细新增 `by_layer`。
- `app/evaluation/datasets.py`：`load_representative_corpus` 文档补充 `layer` / `source` 字段说明。
- `tests/test_retrieval_eval.py`：新增 `test_scaled_benchmark_supports_layer_split`，断言 `by_layer` 含 `base`/`stress`、两层覆盖全部 150 条、且 `stress_accuracy <= base_accuracy`（验证分层确实区分了难度）。

## 4. 评测结果（2026-08-19，确定性 MockLLM 环境）

整体：联合准确率 **0.63**、意图 **0.63**、风险 **0.81**、高风险召回 **0.60**、误报率 **0.00**。

| 层 | 准确率 | 意图 | 风险 | 高召回 | 误报率 |
| --- | --- | --- | --- | --- | --- |
| 基础层（贴近真实流量, n=63） | **0.97** | 0.97 | 1.00 | 1.00 | 0.00 |
| 压力层（边界探测, n=87） | **0.39** | 0.39 | 0.67 | 0.52 | 0.00 |

- 基础层稳健（风险/高召回双 1.00）→ 对应"真实"卖点。
- 压力层偏低且 `stress_accuracy <= base_accuracy` → 如实暴露隐喻式高危、无关键词咨询、第三人称干扰等边界缺口，对应"暴露边界"卖点；零删改、不凑分。

## 5. 验证

`python -m pytest tests/test_retrieval_eval.py -q` → **5 passed**（含 `test_scaled_benchmark_supports_layer_split`）。

## 6. 本轮文件清单

- `eval/fixtures/representative_corpus.json`（新增 `layer`/`source` 字段，150 条全保留）
- `app/evaluation/runner.py`
- `app/evaluation/report_html.py`
- `app/evaluation/datasets.py`
- `tests/test_retrieval_eval.py`
- `README.md`（评测结果：数据来源、150 条规模化基准双层行、非 100% 真实含义）
- `Aegis项目逐文件学习指南.md`（评测闭环章节）
- `docs/records/CORPUS-LAYER-SPLIT.md`（本文件）

# Aegis 第十九轮：RAG 语义重排引擎（Cross-Encoder）与真 MiniLM 实测

> 分支:`main` · 时间:2026-09-29 · 系列:[ROUND-12-RAG-ENHANCEMENT-BENCHMARK](ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md) → [ROUND-13-MEMORY-SKILL-DISTILLATION](ROUND-13-MEMORY-SKILL-DISTILLATION.md) → 第十五~十八轮（前端系列） → 本篇
> 性质:**重排槽位升级（词法公式 → 可选 Cross-Encoder）+ 真语义向量首轮实测 + 检索概念文档体系化**

***

## 1. 背景

第十二轮建立「BM25 + local-hash 向量 + 词法 rerank」混合链路并给出消融后，遗留三个问题：

- **消融已证伪 local-hash**：哈希 bigram 伪向量在 0.65 权重下稀释 BM25（hybrid 62/77 vs bm25_only 72/77），但"真实语义向量是否更好"没有实测数据；
- **重排层无语义能力**：四路词法信号全部与 BM25 同源（字面重叠），对同义改写查询（"睡不好" vs "失眠"）无能为力，且没有模型重排的替代实现；
- **文档可读性**：检索子系统概念（召回/重排/融合的层级与顺序、四条配置路径、两种"默认"）在学习指南中分散且易混淆，初学者反馈"绕晕"。

本轮目标：概念文档体系化 + 真语义向量首轮实测 + Cross-Encoder 重排引擎落地。

## 2. 学习文档增补（小白防绕晕体系）

《Aegis项目逐文件学习指南》新增/修订 7 处：

- **新增 9.7.0「小白防绕晕：概念地图与四条路」**：六问六答覆盖 检索/召回/重排层级与固定顺序（含 `store.py` 逐行时序）、四条配置路 + weighted/rrf 与 rerank 两个子开关 + RRF 跳过重排的例外、重排槽位概念（Cross-Encoder 不是第五条路）、local-hash 伪向量原理与三缺陷、降级 vs 关闭与两种"默认"、升级顺序建议；
- 0.2 概念速成、0.3 术语表增加指向；第三部分 RAG 选型条目"代价/取舍"重写；
- 9.7.5 补消融数字跨版本漂移提示；1.3 加与 README 架构图分工说明；
- 新增 **9.7.8 本轮实测增补**（见 §4/§5）。

## 3. 路 3 实测：Chroma + 本地 MiniLM（77 条，临时索引）

环境：chromadb 1.5.9（项目 `.conda` 自带），`DefaultEmbeddingFunction`（all-MiniLM-L6-v2，384 维）；一次性 SQLite + 临时 chroma 目录，不碰生产索引。

| 模式 | 召回 | 融合 | 重排 | HitRate@4 | 延迟 |
| --- | --- | --- | --- | --- | --- |
| `bm25_only`（基准） | BM25 | weighted | 词法 | **72/77 (0.9351)** | 18 ms |
| `hybrid_minilm` | BM25+MiniLM | weighted 0.65/0.35 | 关 | 66/77 (0.8571) | 233 ms |
| `hybrid_rerank_minilm` | BM25+MiniLM | weighted | 词法 | 67/77 (0.8701) | 242 ms |
| `rrf_minilm` | BM25+MiniLM | rrf | 跳过 | 64/77 (0.8312) | 221 ms |

**结论（如实呈现）**：真 MiniLM 优于 local-hash（66 vs 62），并实际救回 3 条 BM25 因字面零重叠漏掉的语义改写查询（`rag-lowmood-03`/`rag-refer-04`/`rag-amb-03`）；但 `all-MiniLM-L6-v2` 是英文模型，中文只剩字面碎片匹配，0.65 权重下稀释 BM25 精准信号（BM25 命中而 hybrid 漏 9 条、反向补 3 条），**路 3 暂不建议启用**。要启用需换中文嵌入模型（如 bge-small-zh-v1.5）或调低 `KNOWLEDGE_HYBRID_VECTOR_WEIGHT` 后重测。逐条报告：`data/eval/minilm-eval-report.json`。

## 4. Cross-Encoder 重排引擎（新增代码）

### 4.1 设计（对应学习指南 9.7.0 Q3 的两段式架构）

- **重排槽位二选一**：`KNOWLEDGE_RERANK_ENGINE = lexical | cross_encoder`（默认 `lexical`，行为与历史完全一致）；
- **词法引擎**：保持"全库重打分"现状不变（纯公式可负担）；
- **Cross-Encoder 引擎**：按融合分截取 top-N（`KNOWLEDGE_RERANK_TOP_N=16`）精排——模型一次推理几十毫秒，全库跑不起；未进 top-N 的候选保留融合分垫底；
- **永不中断**：模型缺失/损坏/推理失败一律回退词法公式并在 `vector_error` 记录原因。

### 4.2 代码落地

| 文件 | 变更 |
| --- | --- |
| `app/rag/reranker.py`（新增） | ONNX 懒加载会话 + tokenizers pair 编码 + 手动 numpy padding（onnxruntime 不接受锯齿列表）+ sigmoid；进程内缓存 |
| `app/config.py` | `knowledge_rerank_engine` / `knowledge_rerank_top_n` / `reranker_model_dir` 三字段 |
| `app/repository/store.py` | 融合循环引擎分发 + `_apply_cross_encoder_rerank()` 两段式与失败回退 |
| `.env.example` | 三个新配置示例 |
| `tests/test_reranker_engine.py`（新增） | 5 项单测：sigmoid 边界 / 模型缺失报错 / 默认词法不变 / top-N 两段式分数替换 / 失败回退词法。检索回归 16 项全过 |

模型：`Xenova/bge-reranker-base` `model_quantized.onnx`（int8，279 MB）+ `tokenizer.json`（17 MB），经 hf-mirror 下载至 `data/models/bge-reranker-base-onnx/`。

### 4.3 冒烟证据

三个候选 base 分全为 0.5（无区分度）时，对查询"我最近总是睡不好怎么办"：失眠块 **0.7938**、考试块 0.0001、生活块 0.0062——中文成对判别能力真实存在，与英文 MiniLM 嵌入的表现形成鲜明对比。

## 5. Cross-Encoder 实测（77 条）

| 模式 | 召回 | 重排 | HitRate@4 | 延迟 |
| --- | --- | --- | --- | --- |
| `bm25_only`（历史基准） | BM25 | 词法 | 72/77 (0.9351) | 18 ms |
| `bm25_cross_encoder` | BM25 | **CE** | **73/77 (0.9481) 历史最优** | 850 ms |
| `hybrid_minilm_ce` | BM25+MiniLM | CE | 60/77 (0.7792) | 1306 ms |

- **bm25 + CE 为全项目历史最优**：相对词法基准新增命中 5 条（含 3 条语义改写查询）、漏掉 4 条，净 +1。**单点 +1 在 77 条上不具统计显著性**，扩展评测集后再确认；
- `hybrid_minilm_ce` 全场最差：粗排 top-16 已被弱向量带偏、正确文档未进候选头部时 CE 无法挽回——"召回决定上限，重排决定座次"的反例验证；
- 延迟：CE ~850 ms/条（16 候选 × int8 CPU 推理），演示可接受，生产需评估并发。逐条报告：`data/eval/ce-eval-report.json`。

## 6. 配置与使用

```bash
# 默认（词法重排,零模型依赖）
KNOWLEDGE_RERANK_ENGINE=lexical

# 启用 Cross-Encoder 精排（需模型文件在 RERANKER_MODEL_DIR）
KNOWLEDGE_RERANK_ENGINE=cross_encoder
KNOWLEDGE_RERANK_TOP_N=16
RERANKER_MODEL_DIR=data/models/bge-reranker-base-onnx
```

## 7. 局限与后续

- CE 增益 +1 样本量小：扩展评测集（>200 条）再验证；
- 路 3 的真正启用前提是中文嵌入模型接入（bge-small-zh-v1.5 / bge-m3），本轮明确其被英文模型拖累的机制；
- CE 延迟 850 ms/条为单线程 CPU 值，可探索动态量化 / ONNX Runtime 线程调优 / 按风险分级启用；
- 评测脚本 `scripts/eval_minilm_ablation_tmp.py`、`eval_ce_tmp.py` 保留（换嵌入模型后可直接复测）。

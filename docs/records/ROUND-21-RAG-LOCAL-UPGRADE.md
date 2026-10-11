# Aegis 第二十一轮：RAG 本地化升级——中文小模型嵌入、CE 融合精排与规模化落地

> 分支：`main` · 时间：2026-10-11 · 系列：[ROUND-12-RAG-ENHANCEMENT-BENCHMARK](ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md) → [ROUND-19-RAG-SEMANTIC-RERANK](ROUND-19-RAG-SEMANTIC-RERANK.md) → 本篇
> 性质：**检索链路本地化（零外部 API）+ 融合式精排重构 + 真实扩库规模化验证 + 生产路径 bug 修复与窗口调优**

***

## 1. 背景与目标

第十九轮建立了「BM25 + 可选向量 + 词法/CE 重排」的双引擎骨架，遗留三个问题：

- **嵌入层依赖英文模型或外部 API**：真 MiniLM（all-MiniLM-L6-v2）中文判别力弱（rrf 仅 64/77），而外部中文嵌入 API（智谱 embedding-3）虽效果最优但引入网络依赖、数据出境与"技术增量不可归因"问题；
- **CE 精排为"替换式"**：Cross-Encoder 分直接覆盖词法分，救回 5 条的同时丢失 4 条（24 块库净 +1）；
- **知识库仅为 24 个短文档**：真实规模下的表现（干扰、覆盖率、多块霸榜）完全未知。

本轮目标：**全部本地组件（ONNX CPU 推理、零外部 API）** 下完成召回层替换 + 精排融合重构 + 真实扩库（24 → 570 块）规模化落地。

## 2. 召回层升级：bge-small-zh-v1.5（本地 ONNX）

- 模型：`BAAI/bge-small-zh-v1.5`（33M 参数，512 维，CLS 池化 + L2 归一化），Xenova ONNX 版（fp32 91MB / int8 23MB）落盘 `data/models/bge-small-zh-onnx/`；
- 代码：新增 `app/rag/zh_embedder.py`（ONNX 惰性加载，对齐 `reranker.py` 模式）；`embedding_provider=local-zh` 接入 `vector_store.py`；冒烟：语义梯度 0.71 > 0.60 > 0.42，单条 2.5ms。

**24 块库召回实测**（`scripts/eval_bge_small_zh_recall.py` → `data/eval/bge-small-zh-recall-report.json`）：

| 模式 | MiniLM（旧） | bge-small-zh（新） |
| --- | --- | --- |
| hybrid（weighted） | 66 | 73（w 0.2–0.5 稳定） |
| hybrid_rerank | 67 | 73 |
| **rrf** | **64** | **75（+11）** |
| 延迟 | 200–500ms | **16–32ms** |

RRF 作为"嵌入质量晴雨表"验证成立：无权重旋钮，弱嵌入垫底、强嵌入领先。**rrf 召回 75/77 已超过纯 BM25 基线（72/77）**。

## 3. 精排重构：CE 替换式 → 融合式

**机制**：替换式 `score = CE分` 覆盖一切；融合式 `final = λ·norm(词法分) + (1-λ)·norm(CE分)`（head top-16 内，λ=0.4 网格实测最优），tail 保持原序。

**24 块库三口径对照**（`scripts/eval_ce_fusion.py` → `data/eval/ce-fusion-report.json`）：

| 召回口径 | 词法链路 | 替换式 | **融合式 λ0.4** |
| --- | --- | --- | --- |
| A（BM25） | 72 | 76 | **77/77（满命中）** |
| B（bge hybrid） | 74 | — | **75** |
| C（bge rrf） | 75 | — | **76** |

**融合式 ≥ 替换式在全部三口径成立（均 +1）**；核心机制证据：`lowmood-02` 被 CE 打 0.171（替换式会丢），融合式用词法分保住。

**代码落地**（`app/repository/store.py`）：

- `_apply_ce_fusion_rerank()`：head 内双信号归一化加权融合，异常回退词法公式（检索永不中断）；
- 引擎分发：`KNOWLEDGE_RERANK_ENGINE=ce_fusion`（配置 `KNOWLEDGE_CE_FUSION_LAMBDA=0.4`）；
- `app/config.py` 新增 `knowledge_ce_fusion_lambda` 字段。

## 4. 真实扩库验证（v2 库，590 块）

语料构成（`data/scale-test/knowledge-v2/`，183 文件 / 590 块）：原 24 + univs 平台 65 篇 + 百度百科词条 84 条 + AI 样稿 10 篇；覆盖考试/情绪/关系/危机/求助等全部主题域。

**六配置对照**（`scripts/eval_v2_full.py` → `data/eval/v2-full-report.json`，77 题 Top-4）：

| 配置 | 宽松 | 严格 |
| --- | --- | --- |
| A_lexical（纯 BM25 + 词法） | 50 | 45 |
| A_fusion | 58 | 54 |
| C_lexical（rrf 召回 + 词法） | 59 | 55 |
| C_replace（替换式） | 59 | 55 |
| **C_fusion（融合式）** | **64 (0.8312)** | **61 (0.7922)** |

三条结论：① C_fusion 双料第一，领先不用 CE 的 C_lexical 5 条（融合精排在真实规模下仍有价值）；② 融合式 > 替换式（64 vs 59，扩库后证据比 24 块库更强）；③ **扩库后纯词法召回崩塌**（A_lexical 严格 0.5844 vs C_lexical 0.7143），语义向量召回是规模化的必要条件。

## 5. 生产落地与 bug 修复（核心工程故事）

### 5.1 首跑异常

生产配置（`local-zh + rrf + ce_fusion λ0.4`，570 块）复评首跑仅 **宽松 34/77（0.44）/ 严格 24/77（0.31）**，远低于实验预期（0.83/0.79）。

### 5.2 三层诊断定位根因

- 向量召回正常（campus-01 向量 top1 即期望源，db_id 对齐零错位）；BM25 正常；
- 但 `store.search_knowledge` 的 top-4 完全错乱：**两个无关主题的 query，top1 都是同一篇字母序靠前的老文档**；
- 追踪补丁（monkey-patch `_apply_ce_fusion_rerank`）显示：**进入精排的 `ranked` 列表根本未排序**，head 取到的是"数据库插入顺序前 16 条"。

**根因**：`ranked` 仅按 DB 查询顺序 append，`ranked.sort()` 位于精排调用**之后**（`store.py`），而 `_apply_*_rerank` 内部 `head = ranked[:16]` —— 于是每个 query 的 CE 精排都发生在**同一批"最早入库的 16 条文档"**上，与融合分无关。

### 5.3 修复与复评

修复（精排调用前先排序，ce_fusion 与 cross_encoder 两引擎一并修复）：

```python
                ranked.append((chunk, score))
            # 精排引擎只处理候选池头部:必须先按分排序,否则 head 取到的是数据库插入顺序
            ranked.sort(key=lambda item: item[1], reverse=True)
            if rerank_engine == "cross_encoder":
                ranked = self._apply_cross_encoder_rerank(rewritten_query, ranked)
            if rerank_engine == "ce_fusion":
                ranked = self._apply_ce_fusion_rerank(rewritten_query, ranked)
            ranked.sort(key=lambda item: item[1], reverse=True)
```

修复后复评：**宽松 57/77（0.7403）/ 严格 54/77（0.7013）（+23/+30）**。

### 5.4 教训

评测脚本跑通 ≠ 生产路径正确：本轮 CE 评测历史数据（9/29 的 73/77）来自**独立实验脚本**，生产 `store.search_knowledge` 的 ce_fusion/cross_encoder 分发路径在规模化下**从未被黑盒验证过**。修复此 bug 的途径是"复评走近生产路径 + 逐层白盒对账"。

## 6. 窗口诊断与调优（candidate_k 16 → 128）

修复后生产（57/54）与实验（64/61）仍差 7 条。逐题 diff：**7 条全部为"生产挂而实验过"**（anx-05 / crisis-01 / lone-02 / perf-02 / rel-03 / sleep-04 / amb-01），反向 0 条。

**机制**：RRF 的向量侧排名项 `1/(k+v_rank)` 只覆盖"被向量召回进候选窗口"的条目；窗口=16 时，全库向量排名 19–82 的期望源拿不到 v 项 → RRF 排名塌陷出 head-16 → CE 无法触达。crisis 题实测：`crisis.md` 全库向量排名 28，窗口 16 下 RRF #27（不进 head），全库口径下 RRF #9（进 head，CE 融合后命中）。

**同库（570 块）A/B/K128 完整链路对照**（`scripts/eval_retrieval_window.py`，可复跑）：

| 口径 | 宽松 | 严格 |
| --- | --- | --- |
| A：窗口 16（现状） | 57 | 54 |
| K=128 | 62 | 60 |
| B：全库向量排名 | 63 | 61 |

**决策**：`KNOWLEDGE_CANDIDATE_K` / `VECTOR_TOP_K` 由 16 调整为 **128** —— 对齐工业 RRF 窗口实践（Elasticsearch `rank_window_size` 默认 ≈100），保留 ANN 截断架构，K=128 已收敛到全库口径的 98%。

**128 窗口生产复评（最终）**：**宽松 63/77（0.8182）/ 严格 61/77（0.7922）**，平均延迟 2157.9 ms；相对窗口 16 新增命中 7 条（含 crisis-01），丢失 1 条（adj-04），净 +6。生产黑盒结果与全库口径白盒（63/61）逐题仅 1 条边界差异（perf-01，以生产实现为准）。

## 7. 工程加固

- **测试隔离**：`tests/test_reranker_engine.py` 三个用例此前依赖宿主 `.env`（生产配置切换后断言语义被带偏而失败），修复为 `Settings(_env_file=None, **params)`（对齐 `test_api.py` 既有先例）；修复后 5 passed，且不再误加载 CE 模型（51.6s → 11.8s）；
- **配置模板同步**：`.env.example` 的 `KNOWLEDGE_CANDIDATE_K` / `VECTOR_TOP_K` 同步为 128 并加注窗口语义（避免复现者掉进同一坑）；
- **全库扫描**：确认"未排序切片"仅存于 store 精排链路两处（已修复），`vector_store` 本地/Chroma 后端均为先排序再截断。

## 7A. 评测体系补测与消融引擎缺陷修复（2026-11-11）

> 本节记录第 7 节之后的补充工作：把生产配置的**完整 7 指标**跑出来、修复消融引擎切换缺陷、并定位一处「反直觉但正确」的结果。产出已同步学习指南 9.7.9 / 9.7.10。

### 7A.1 背景：指标口径分裂

第 6 节的生产复评只产出**宽松/严格 2 个口径**（`eval_production_check.py` 是自定义脚本，未走 `evaluate()` 的完整聚合），而 `rag-eval-report.json` 虽含**全部 7 个指标**却产生于旧配置（`local` MiniLM + weighted + lexical，24 块库时代）。

**即：生产配置的 Recall / Precision / MRR / NDCG 从未测过。** 补跑 `python -m app.evaluation.rag`（耗时 12 分 49秒）后填齐。

### 7A.2 生产配置 7 指标（77 题 Top-4）

| 指标 | 值 |
| --- | --- |
| recallAtK | 0.8182 |
| precisionAtK | 0.2857 |
| mrr | 0.6656 |
| ndcgAtK | 0.6997 |
| hitRate（宽松） | 0.8182（63/77） |
| hitRateStrict | 0.7922（61/77） |
| averageFirstRelevantRank | 1.5079 |

**★ 强交叉验证**：本次 `hitRate`/`hitRateStrict` = **63/77 / 61/77**，与第 6 节生产黑盒复评**完全一致**——两条独立代码路径（生产 `store.search_knowledge` vs 评测框架 `evaluate()`）得到同一结果，检索链路可复现。

### 7A.3 消融引擎切换缺陷（已修复）

**缺陷**：`run_ablation` 只切`rerank_enabled` / `fusion_mode` / `vector_enabled`，**从不切 `knowledge_rerank_engine`**——因此所有 `rerank_enabled=True` 的组实际执行的都是生产值 `ce_fusion`，而非模式声称的「词法重排」。

**影响**：消融结论被归因到错误的引擎。据此得出的「词法重排是纯亏组合」**结论碰巧正确但证据是错误的**（那个零增益实际来自 CE 的部分生效）。

**修复**（`app/evaluation/rag.py`）：每个模式显式声明 `engine`；循环内真正切换；`config.rerankEngine` 留痕；`finally` 中还原 `original_engine` 防状态残留。新增 `rrf_ce`（生产配置）与 `hybrid_ce` 两组。回归：`tests/test_retrieval_eval.py` 5 passed。

### 7A.4 六组消融（修复后真正切换引擎）

| 模式 | 向量 | 融合 | 重排引擎 | HitRate | 命中 | 平均延迟 |
| --- | --- | --- | --- | --- | --- | --- |
| **`rrf_ce`（= 生产配置）** | ✓ | rrf | **ce_fusion** | **0.8182** | **63/77** | 1995ms |
| `rrf` | ✓ | rrf | 无 | 0.7922 | 61/77 | **329ms** |
| `hybrid` | ✓ | weighted | 无 | 0.7532 | 58/77 | 306ms |
| `hybrid_rerank` | ✓ | weighted | **lexical** | 0.7532 | 58/77 | 745ms |
| `hybrid_ce` | ✓ | weighted | **ce_fusion** | 0.7273 | 56/77 | 2005ms |
| `bm25_only` | ✗ | weighted | **lexical** | 0.6753 | 52/77 | 501ms |

**四条结论**：

1. `rrf_ce` 当前最优，且等于主指标、等于第 6 节生产复评值——**三处独立数字互相吻合**；
2. **融合方式比精排引擎更关键**：`rrf_ce` vs `hybrid_ce` 差 **9 条**，而 `rrf` vs `hybrid` 只差 3 条 → 先定融合、再定精排，这正是本轮的选型顺序；
3. **词法重排确认真零增益**：`hybrid` → `hybrid_rerank` 一条不多、慢 2.4 倍。注意这**不等于「词法没用」**——BM25 召回阶段已完成词法工作，精排再叠一层是重复劳动；
4. **关向量最差**：`bm25_only`仅 0.6753，**语义召回是规模化的必要前提**（第 4 节结论的独立复现）。

### 7A.5 反常项：weighted 下加 CE反而掉 2 条

`hybrid`(0.7532) → `hybrid_ce`(0.7273)，**加精排反而变差**，违反直觉。

**排除误判**：延迟增量 `hybrid_ce` +1699ms vs `rrf_ce` +1666ms，几乎相同 ⇒ CE 在两种融合下都真实执行，不是漏跑或回退。

**根因**：`store.py:886-893` 两分支的候选池守卫不同——weighted 只跳过「双零」块（候选池 ≈ 全库 570），rrf 须至少进过一路榜单（候选池 ≈ 128 + BM25 命中数）。

**机制**：weighted 融合分经 `normalize_scores` 做 min-max 后**长尾被拉平**，头部 16 与17~50 名的差距远小于 RRF的阶梯状分布（`1/(60+rank)`），导致 `ranked[:16]` 未必是真正相关的 16 条；CE 融合式在这个噪声 head 上归一化加权，**反而放大噪声**、把排序带偏 2 条。rrf 候选池小且都是强候选，head 质量高，CE 才能真正发挥。

**升级结论**：**融合方式的选择比精排引擎的选择更能决定最终效果**（差 9 条 vs 差 2 条）——融合决定候选池质量上限，精排只能在池子里挑。这是 9.7.0 Q1「召回失败不可挽回」在融合层的具体体现。

**未实测的遗留改进项**（供后续参考，非本轮结论）：① weighted 分支引入「至少进一路榜单」守卫收窄池子；② 归一化改z-score / 秩归一化以减少长尾拉平。

### 7A.6 指标口径缺陷（与本轮改动同期发现）

1. **Recall 名不副实**：实现为 `1.0 if hit else 0.0`（`rag.py:169`），已退化成 HitRate——两次独立实测recall 与 hitRate 完全相等（0.8701/0.8701、0.8182/0.8182）。
2. **Precision@K 超理论上限**：分母固定 `top_k=4`，而每题只有 1~2 个期望源 → 单题上限 0.25~0.5，实测却有 23 题达 0.5~0.75。根因是 `is_relevant` 宽松口径为「source 命中 **OR** term 命中」，会把同主题不同文档误判相关（如 `rag-anx-03` 期望 `anxiety.md`，实际 rank1 `career-anxiety.md` 因含term「求职」被判相关）。

**处置**：明确标注 Recall 与 Precision **非标准IR 语义、跨系统不可引用**；HitRate 与 MRR/NDCG 口径清晰，作为可对外引用的主指标。

### 7A.7 复现性

同配置曾跑出 62/77（差 1 条），源于 Chroma 向量后端的近似检索非确定性，属正常抖动而非配置差异。旧配置的 7 指标报告已归档为 `data/eval/rag-eval-report.minilm-archive.json`。

## 8. 结论与数据链

**最终生产配置**：`local-zh（bge-small-zh-v1.5 ONNX）+ rrf 融合 + ce_fusion λ0.4 + candidate_k=128 + head16`。

**核心数字链（77 题 Top-4，宽松/严格）**：

| 阶段 | 库 | 结果 |
| --- | --- | --- |
| 旧生产（MiniLM + hybrid_rerank + 词法） | 24 块 | 0.870 / 0.792 |
| 本轮修复前（ce_fusion bug） | 570 块 | 0.442 / 0.312 |
| 修复后（窗口 16） | 570 块 | 0.740 / 0.701 |
| **修复后（窗口 128，最终）** | **570 块** | **0.818 / 0.792** |

**结论**：在库规模放大 24 倍（24 → 570 块）的前提下，本地化检索链路（全本地 ONNX、零外部 API）严格口径与旧 24 块库生产基线持平（0.792），宽松口径 0.818；`crisis`（自伤危机）等高风险场景查询全部命中；全部增量可归因于自研组件与调优（中文嵌入选型、CE 融合算法、窗口诊断、bug 修复），不依赖任何外部高级模型。

**报告与资产索引**：

- `data/eval/bge-small-zh-recall-report.json`（召回层实测）
- `data/eval/ce-fusion-report.json` + `ce-fusion-raw.json`（CE 融合三口径）
- `data/eval/v2-full-report.json`（590 块六配置）
- `data/eval/ksweep-head16-cover.json`（窗口 sweep 覆盖）
- `data/eval/align-ab-report.json`（A/B 同库完整链路）
- `data/eval/align-k128-report.json`（K=128 白盒）
- `data/eval/production-check-report.json`（**128 窗口生产复评·最终**）
- `data/eval/production-check-buggy-archive.json`（bug 版存档）/ `production-check-k16-report.json`（窗口 16 版）
- `data/eval/rag-eval-report.json`（**生产配置 7 指标 + 六组消融·7A 节最终**）
- `data/eval/rag-eval-report.minilm-archive.json`（旧 MiniLM 配置 7 指标存档）

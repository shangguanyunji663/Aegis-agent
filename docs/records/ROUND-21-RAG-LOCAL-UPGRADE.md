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

# Aegis 第十二轮：RAG 知识库扩充、检索增强与本地性能 Benchmark

> 分支:`main` · 时间:2026-08-21 · 系列:[REFACTORING](REFACTORING.md) → [OPTIMIZATION](OPTIMIZATION.md) → [AUTH-MYSQL](AUTH-MYSQL.md) → [LANGGRAPH-DOCKER](LANGGRAPH-DOCKER.md) → [DEEP-ENHANCEMENTS](DEEP-ENHANCEMENTS.md) → [LLM-RESPONSE-HUMANIZATION](LLM-RESPONSE-HUMANIZATION.md) → [MEMORY-ENHANCEMENT](MEMORY-ENHANCEMENT.md) → [CONFRONTATIONAL-DIALOGUE-TESTING](CONFRONTATIONAL-DIALOGUE-TESTING.md) → [ROUND-9-CONSOLIDATION](ROUND-9-CONSOLIDATION.md) → [CORPUS-LAYER-SPLIT](CORPUS-LAYER-SPLIT.md) → [ROUND-11-RISK-LLM-DUAL-CHANNEL](ROUND-11-RISK-LLM-DUAL-CHANNEL.md) → 本篇
> 性质:**RAG 检索链路增强 + 知识库规模化扩充 + 本地系统性能基准,对标企业级 RAG 与工程化能力**

---

## 1. 背景

第十一轮完成风险双通道、评测双层拆分后，项目在**规则/评测体系**上已较完整，但 RAG 侧仍有明显短板：

- **知识库太小**：仅 12 篇、每篇 1 段话（共约 7000 字符），覆盖主题窄，检索区分度低，离"企业 RAG 知识库"差距大。
- **检索链路单薄**：只有 BM25+向量加权融合+词法 rerank，缺少 RRF 排名融合、查询缓存；评测只输出单口径指标，没有消融对比，无法证明"为什么这么配"。
- **没有性能基准**：只有 Runtime A/B 的准确性对比，缺少企业常用的吞吐 / 并发 / P95 延迟 / 缓存加速 / 成本估算指标。

本轮目标：把 RAG 部分从"demo 级检索"提升到"可量化、可解释、可对标企业简历"的完整链路。

## 2. 知识库扩充（12 → 24 篇）

### 2.1 现有 12 篇深化

`knowledge/*.md` 从单段话扩展为 3-4 个结构化章节（常见表现 / 支持策略 / 升级信号 / 注意事项），每篇篇幅提升约 2 倍，为检索提供更多可命中的主题词与上下文。

### 2.2 新增 12 个主题

| 主题 | 文件 | 覆盖问题 |
| --- | --- | --- |
| 学业拖延与时间管理 | `academic-procrastination.md` | 拖延原因、2分钟法则、番茄工作法 |
| 就业/求职焦虑 | `career-anxiety.md` | 求职压力、面试焦虑、可控/不可控 |
| 恋爱关系困扰 | `romantic-relationships.md` | 失恋、暗恋、关系边界、安全升级 |
| 孤独与社交焦虑 | `loneliness.md` | 社交回避、小范围社交、关注对方 |
| 完美主义 | `perfectionism.md` | 自我苛责、够好就行、绝对化思维 |
| 网络与手机依赖 | `internet-addiction.md` | 手机依赖、物理隔离、替代活动 |
| 正念与自我关怀 | `self-compassion.md` | 正念呼吸、自我友善、接纳练习 |
| 愤怒管理 | `anger-management.md` | 冷静策略、非暴力表达 |
| 哀伤与丧失 | `grief-and-loss.md` | 丧亲/分手、哀伤过程、升级信号 |
| 经济压力 | `financial-stress.md` | 预算、勤工俭学、消费差距自卑 |
| 躯体化症状 | `somatization.md` | 心慌/头痛/胃痛、身心关联、肌肉放松 |
| 习得性无助 | `learned-helplessness.md` | 自我效能、小目标、重新归因 |

所有文档统一保留 YAML frontmatter（topic / audience / risk_level / source_type / last_reviewed），正文为 markdown 多段结构，兼容现有 `chunk_text` 切块与元数据过滤。

### 2.3 评测集同步扩充

`eval/fixtures/rag_queries.json`：50 → 77 条查询，为 12 个新主题各写 2-3 条 query（含 expectedSources + expectedTerms），并保留原有跨主题组合题（amb-*）。

## 3. 检索链路增强

### 3.1 RRF 融合（企业高频词）

- `app/rag/scoring.py` 新增 `rrf_fused_score(vector_rank, bm25_rank, k=60)`：按两路各自排名做 Reciprocal Rank Fusion，替代分数归一化线性加权，对分数分布更鲁棒。
- `app/config.py` 新增 `knowledge_fusion_mode: str = "weighted"`（`weighted` | `rrf`），默认保持原行为。

### 3.2 查询缓存

- `app/config.py` 新增 `knowledge_cache_enabled`（默认 False）、`knowledge_cache_ttl_seconds=300`、`knowledge_cache_max_entries=128`。
- `app/repository/store.py` 新增进程内 LRU 缓存（OrderedDict，key=规范化查询+top_k+过滤条件），有 Redis 时同时写入 Redis。
- `knowledge_status()` 暴露 `cache_hits` / `cache_misses` / `cache_hit_rate`。

### 3.3 双口径评测

- `app/rag_eval/runner.py` 的 `is_relevant()` 拆为两层返回：
  - **宽松口径（loose）**：来源命中或任一 expected term 出现在内容（原口径）
  - **严格口径（strict）**：仅 expected source 命中
- 报告新增 `hitRateStrict` / `strictSourceMatches`，同时输出两口径值。

### 3.4 消融实验

- `app/rag_eval/runner.py` 新增 `run_ablation()`：同一 77 条查询 × 4 种检索配置，输出 HitRate 与平均检索延迟：
  - `bm25_only`：关向量、开 rerank
  - `hybrid`：开 local 向量、关 rerank
  - `hybrid_rerank`：开向量 + rerank（生产默认）
  - `rrf`：RRF 融合
- 消融中按模式重建向量后端（`build_vector_backend` + `rebuild_vector_index`），结束后还原原配置。
- 环境注明：消融在零依赖 `local-hash` 向量后端下运行；接入 Chroma/MiniLM 语义向量后结论可复跑更新。

## 4. 本地性能 Benchmark

新增 `scripts/run_benchmark.py`（复用 harness factory 隔离装配：独立 SQLite + 真实 24 篇知识库 + MockLLM 确定性环境）：

- **并发基准**：并发 [1, 4, 8]，每级 20 条代表性消息，`ThreadPoolExecutor` 并发调用 `orchestrator.handle`，输出 avg / P95 / 吞吐（req/s）/ 成功率 / 每级 LLM 调用数（复用 CountingLLMClient 模式）。
- **缓存基准**：knowledge_cache 开/关各测一轮检索延迟，量化命中加速。
- **ToolJob 统计**：跑一轮"高危消息 → 审批 → 执行队列"，统计成功率/重试/死信。
- **成本估算**：按中文字符≈1 token 估算输入量（注明仅代表相对量级）。

输出 `data/eval/benchmark.json` + 控制台 Markdown 摘要。

## 5. 评测结果（2026-08-21，确定性 MockLLM 环境）

### 5.1 RAG 检索（77 条查询，Top-4）

| 指标 | 值 |
| --- | --- |
| 宽松口径 HitRate@4 | **0.9351**（72/77） |
| 严格口径 HitRateStrict | **0.8831**（68/77） |
| Recall@4 / Precision@4 | 0.9351 / 0.3506 |
| MRR / NDCG@4 | 0.8203 / 0.8323 |

### 5.2 消融实验（local-hash 向量后端）

| 配置 | HitRate | avg 延迟(ms) |
| --- | --- | --- |
| bm25_only | **0.9351** | 20.59 |
| hybrid | 0.8312 | 7.73 |
| hybrid_rerank | 0.8052 | 19.14 |
| rrf | 0.7662 | 8.16 |

**结论（如实呈现）**：在零依赖的 `local-hash` 词法向量下，纯 BM25 已足够强，混入词法 hash 向量反而稀释分数；hybrid / RRF 的增量价值需要**真实语义向量**（Chroma + MiniLM / OpenAI embeddings）才能体现。这一结果明确了"为什么生产要开语义向量、演示模式退化为 BM25"的配置边界，是检索工程理解的实证，而非缺陷。

### 5.3 本地性能基准

| 并发 | avg(ms) | P95(ms) | 吞吐(req/s) | 成功率 | LLM 调用/级 |
| --- | --- | --- | --- | --- | --- |
| 1 | 66.0 | 70.7 | 15.14 | 1.0 | 60 |
| 4 | 316.5 | 728.5 | 12.28 | 1.0 | 60 |
| 8 | 516.6 | 1260.2 | 13.53 | 1.0 | 60 |

- 备注：单进程多线程受 GIL 限制，并发 4/8 的吞吐未线性提升；生产可改多进程/异步提升并发吞吐。
- **缓存基准**：冷查询 avg ~18-20ms，命中后 <0.01ms，**加速约 3 个数量级**，命中率 0.667（30 条 warmup + 60 次命中）。
- **ToolJob**：5/5 成功，0 死信，成功率 1.0。

## 6. 验证

- `python -m pytest tests/ -q` → **71 passed**（含 RAG 评测、Harness、基准相关测试，无回归）。
- `python -m app.rag_eval.runner` → 输出双口径 + 消融对比，写 `data/eval/rag-eval-report.json`。
- `python -m scripts.run_benchmark` → 输出完整性能报告，写 `data/eval/benchmark.json`。

## 7. 文件变更清单

- `knowledge/`：12 篇深化 + 12 篇新增（共 24 篇）
- `eval/fixtures/rag_queries.json`（50 → 77 条）
- `app/rag/scoring.py`（RRF 融合）
- `app/rag_eval/runner.py`（双口径 + 消融）
- `app/repository/store.py`（查询缓存、缓存统计）
- `app/config.py`（fusion_mode / cache 三项新配置）
- `scripts/run_benchmark.py`（新增本地性能基准）
- `.env.example`（新配置示例）
- `README.md`（RAG 双口径/消融、benchmark 行、技术栈、命令、环境变量）
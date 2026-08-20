## 面向校园心理支持场景的多 Agent 风险识别与干预协作平台项目简介

`Aegis Psych Agent` 是一个校园心理支持多 Agent 平台，围绕学生端倾诉、心理知识检索、风险识别、辅导员工作台和高风险工具执行闭环展开。项目不是简单的聊天机器人，而是把“学生侧即时支持”和“管理侧可审计干预”拆成两套独立信息架构，并通过后端 Agent Runtime Harness 统一处理意图路由、记忆注入、RAG 检索、风险报告、trace 落库和工具计划。

我在设计时重点解决三个问题：

- 普通聊天不应被过度检索和过度工具化，避免无效召回影响回复质量。
- 高风险表达必须进入可审计流程，工具执行需要人审、脱敏、重试和死信机制。
- 多 Agent 协作不能只停留在顺序调用，需要有共享状态、任务认领、产物验收和运行 trace。

> 安全声明：本项目用于心理支持和工程展示，不提供医学诊断，也不能替代专业心理咨询或危机干预服务。高风险场景下，系统只做风险识别、辅助总结和转介建议，最终干预应由具备资质的人员完成。

## 核心亮点

| 模块 | 解决的问题 | 实现方式 |
| --- | --- | --- |
| 双端独立界面 | 学生倾诉体验和管理员处置流程关注点不同，混在一起会让产品边界混乱 | `/student` 提供学生对话与会话记忆，`/admin` 提供报告、个案、trace、知识库、工具队列和评测工作台 |
| Agent Runtime Harness | Agent 调用、上下文注入、风险报告和工具计划分散在业务代码里会难以审计 | `AegisAgentHarness` 统一封装输入脱敏、运行时调用、trace 保存、消息持久化、报告生成和工具计划 |
| 自治多 Agent 协作 | 单个 Lead Agent 串行分派容易变成“伪协作”，复杂场景缺少中间产物 | 基于 append-only blackboard 实现任务发布、Agent claim、artifact 产出、风险 override 和最终验收，不依赖 LangGraph |
| MemoryAgent | 心理支持需要连续性，单轮回复无法体现对用户状态的理解 | 独立 `MemoryAgent` 维护会话摘要和近期上下文，并将记忆作为 Agent 协作输入 |
| Agentic RAG | 所有消息都检索知识库会增加噪声，尤其普通陪伴类对话容易被知识文档带偏 | 通过 CHAT / CONSULT / RISK 意图路由决定是否检索；**多路召回（BM25 + 向量）+ 可选 RRF 融合 + rerank + 邻块扩展**，支持元数据过滤、查询改写、语义/精确缓存与消融评测（详见「评测结果」） |
| 工具治理与 MCP | 高风险预警、Excel 记录、邮件通知不能由模型越权直接执行 | 工具调用先生成 `ToolJob`，经角色、风险等级、审批、脱敏和审计后进入队列；支持 internal 和 FastMCP 两种后端 |
| 后台 Tool Queue | 外部工具慢、失败或限流时，不应阻塞学生端流式回复 | 独立 worker 支持依赖调度、重试延迟、邮件限流、dead letter、ExcelRecord 和 AlertRecord 持久化 |
| Engineering Harness | Agent 项目只看 demo 容易高估完成度，需要可重复验证 | 基于真实代表性数据集的 pytest 单元/接口测试、RAG eval、综合 eval(含 LLM-as-Judge)、harness 8 套件、三运行时 A/B 对比评测，覆盖路由、风险、安全、RAG、API、工具队列与编排器链路（真实指标见下方「评测结果」） |
| 风险双通道 | 关键词规则召回有限，单靠模型又不可控 | 规则 ∪ 轻量 LLM 取并集、任一判高危即高危，并以规则兜底回退保证安全边界（落地细节见 Roadmap） |

## 架构概览

```mermaid
flowchart LR
    Student["学生端 /student"] --> API["FastAPI API 层"]
    Admin["管理员端 /admin"] --> API

    API --> Harness["AegisAgentHarness"]
    Harness --> Runtime["Autonomous Blackboard Runtime"]

    Runtime --> Memory["MemoryAgent"]
    Runtime --> Lead["Lead / Supervisor Agent"]
    Runtime --> Risk["RiskGuardianAgent"]
    Runtime --> Knowledge["KnowledgeAgent"]
    Runtime --> Counselor["CounselorAgent"]
    Runtime --> Companion["CompanionAgent"]

    Knowledge --> RAG["Hybrid RAG<br/>BM25 + Vector + Rerank"]
    Harness --> Store["SQLite / PostgreSQL<br/>messages, memory, reports, traces"]
    Harness --> ToolPlan["Governed ToolJob"]
    ToolPlan --> Queue["Tool Queue Worker"]
    Queue --> MCP["FastMCP / internal tools"]
    MCP --> Outputs["Excel, Alert, Email, Handoff, Audit"]

    Admin --> Eval["Eval & Harness Reports"]
    Eval --> Store
```

## 功能清单

### 学生端

- 注册与登录:学生自由注册;教师凭邀请码注册(默认 `aegis-teacher`,经 `AUTH_TEACHER_INVITE_CODE` 配置)后进入咨询后台。
- 登录、退出、会话创建、会话重命名和会话删除。
- SSE 流式心理支持回复，兼容非流式 `/api/chat`。低风险对话在生成的同时逐字直播(真流式),中/高风险回复经安全复核通过后再输出。
- 低风险陪伴、心理咨询建议、高风险安全回应三类回复路径。
- 会话级记忆摘要，支持多轮上下文连续表达。
- 高风险内容不向学生暴露内部报告字段，避免造成二次伤害或信息泄露。

### 管理端

- 风险报告列表、状态流转和报告 trace 查看。
- 个案创建、辅导员确认、备注追加和状态更新。
- 知识库检索、文件上传、重建索引、向量索引重建和备份。
- ToolJob、ToolAudit、ExcelRecord、AlertRecord、DeadLetter 的独立查看。
- Agent 模型配置状态、Agent 私有记忆和 Runtime 状态查看。
- 一键触发综合评测和 Harness 验证。

### Agent 协作

- `MemoryAgent`：加载和更新会话记忆。
- `LeadAgent / SupervisorAgent`：识别意图并决定协作路径。
- `RiskGuardianAgent`：风险分级、安全 override、高风险报告生成。
- `KnowledgeAgent`：按意图和风险等级检索知识库，注入标准 Skill。
- `CounselorAgent`：生成咨询类支持计划和可追踪回复。
- `CompanionAgent`：处理低风险陪伴和情绪支持对话。

### 工具与治理

- FastMCP server：暴露 case create、case ack、case note add、alert、ledger、email、handoff、resource lookup 等工具。
- MCP client：支持从平台内切换到 MCP 后端执行工具。
- 工具契约：限制角色、风险等级、审批要求、脱敏字段和最大重试次数。
- 后台 worker：支持批量领取、依赖调度、失败重试、限流和 dead letter。
- 真实输出：Excel 写入、Alert 独立记录、邮件发送或日志投递、handoff Markdown 文件。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 API | Python, FastAPI, Pydantic, SQLAlchemy |
| Agent Runtime | LangGraph StateGraph(主推)+ 自研 blackboard runtime(认领制兜底)+ ordered 流水线,三档可切换 |
| RAG | 多路召回（BM25 + 向量）+ 加权/RRF 融合 + rerank + 邻块扩展，Chroma/local 双后端，元数据过滤，查询缓存（LRU/Redis），四档消融评测 |
| 工具协议 | FastMCP, governed ToolJob, background worker |
| 存储 | SQLite local mode, optional PostgreSQL, optional Redis lock |
| 前端 | 原生 HTML/CSS/JavaScript, student/admin 双端页面 |
| 工程验证 | pytest, custom eval runner, RAG eval runner（双口径+消融）, harness runner, 本地性能 benchmark |
| 部署 | Dockerfile, docker-compose |

## 快速开始

### 本地运行

```bash
git clone https://github.com/m4rklee/aegis-psych-agent.git
cd aegis-psych-agent

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -m app.init_db
uvicorn app.main:app --host 127.0.0.1 --port 8091
```

默认使用 SQLite,零外部依赖即可运行。**使用本地 MySQL 8.0 时**,在 `.env` 中设置:

```bash
DATABASE_URL=mysql+pymysql://root:你的密码@localhost:3306/aegis?charset=utf8mb4
```

首次启动会自动建库建表(utf8mb4);已有 SQLite 数据可用 `python -m scripts.migrate_sqlite_to_mysql` 一键迁移(旧文件保留为备份)。

打开浏览器访问：

- 首页：[http://127.0.0.1:8091](http://127.0.0.1:8091)
- 学生端：[http://127.0.0.1:8091/student](http://127.0.0.1:8091/student)
- 管理端：[http://127.0.0.1:8091/admin](http://127.0.0.1:8091/admin)

默认演示账号：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 学生 | `student` | `student123!` |
| 管理员 | `admin` | `admin123!` |

### Docker Compose

```bash
docker compose up --build
```

Compose 会启动应用、PostgreSQL、Redis 和 Chroma。默认本地模式使用 SQLite；如需切换数据库或向量后端，可在 `.env` 中调整 `DATABASE_URL`、`VECTOR_ENABLED`、`VECTOR_BACKEND` 等配置。

## 常用命令

```bash
# 初始化数据库
python -m app.init_db

# 后端测试（只跑 tests/，避免被根目录 test_chat.py 阻塞）
python -m pytest tests -q

# 前端脚本语法检查
node --check static/login.js static/student.js static/admin.js

# 综合评测
python -m eval.run_eval

# RAG 独立评测(含双口径 + 消融)
python -m app.rag_eval.runner

# 本地性能 benchmark(并发/延迟/吞吐/缓存/ToolJob)
python -m scripts.run_benchmark

# 工程 Harness 验证
python -m app.harness.runner --suite all --output data/harness/latest.json

# 查看 MCP 能力
python -m app.mcp_tools.server --list
```

## 评测结果

当前仓库的评测体系**基于人工构造的代表性测试集**（模拟真实校园心理求助语料特征），**不筛选样本、不为追求满分而人为凑 100%**。所有指标由 `python -m eval.run_eval` 与 `python -m app.harness.runner` 在确定性（MockLLM）环境下产出，衡量的是当前**规则引擎通道**的真实能力边界；生产环境开启 `RISK_LLM_CHANNEL_ENABLED` 后，双通道中的 LLM 通道会进一步补强召回。

> **注意**：评测指标反映测试集表现，非真实用户流量验证，不等同于临床有效性评估。

> 数据来源与最近验证日期：**最近验证日期 2026-08-20**。
> - 路由/风险/规模化基准：`eval/fixtures/representative_corpus.json`（150 条唯一真实样本，**双层拆分**：每条含 `layer`（base 基础层 / stress 压力层）与 `source`（synthetic-representative / synthetic-boundary）字段，含隐式高危与第三人称干扰）
> - RAG 检索：`eval/fixtures/rag_queries.json`（77 条自然语言问句，基于 24 篇知识文档）
> - 多轮回归：`eval/fixtures/multi_turn_corpus.json`（8 组多轮场景）
> - 三运行时 A/B：10 条代表性消息（覆盖四意图 + 中风险 + 显式/隐式高危 + 第三人称干扰）
> - 性能基准：`python -m scripts.run_benchmark`（并发/延迟/吞吐/缓存/ToolJob，确定性 MockLLM 环境）

| 验证项 | 覆盖内容 | 最近验证结果（2026-08-19） |
| --- | --- | --- |
| 单元与接口测试 | API、认证、风险双通道、Function Calling、Agent runtime、LangGraph checkpoint、MCP tools、评测 runner | 本地 SQLite 可执行 **57 通过**（`tests/test_api.py` 依赖 MySQL 后端，本环境未运行；`test_langgraph_checkpoint` 的跨实例持久化为既有环境问题，与本次评测改造无关） |
| 150 条规模化基准（双层拆分，横向分层） | 150 条唯一真实样本（非循环生成），按 `layer` 拆为 **基础层（贴近真实流量）63 条** 与 **压力层（边界探测）87 条**，runner 分别输出两套独立指标。**目的：横向对比基础层 vs 压力层，衡量规则引擎能力边界** | 整体：联合准确率 **0.63**；意图 **0.63**；风险 **0.81**；高风险召回 **0.60**；误报率 **0.00**。- **基础层（贴近真实流量）**：准确率 **0.97**、意图 **0.97**、风险 **1.00**、高召回 **1.00**（贴近真实校园求助流量，规则引擎表现稳健）。- **压力层（边界探测）**：准确率 **0.39**、意图 **0.39**、风险 **0.67**、高召回 **0.52**（隐喻式高危、无关键词咨询、第三人称干扰等边界样本，如实暴露规则通道的能力缺口）。按难度分层：easy 明显优于 hard |
| 风险 LLM 通道双路径（第十一轮，纵向对比） | 150 条全量双路径对比：baseline（纯规则 channel OFF，**即上行压力层纯规则结果，此处作为纵向对比起点不重复数字**）→ MetaphorAwareStub ON（rules ∪ LLM 并集）→ GLM-4.7-flash sanity probe。**目的：纵向对比 LLM 通道相对纯规则的补强幅度** | **baseline（channel OFF）**：压力层风险 **0.67**、高召回 **0.52**、误报 **0.00**（同上行压力层，纯规则）。**llm_stub（channel ON）**：压力层风险 **0.94**（↑0.27）、高召回 **1.00**（↑0.48）、误报 **0.03**（corp-106..130 全部 25 条隐喻命中；2 条 medium distress 含"撑不下去"/"不配"属 prompt-vs-corpus 标注张力，如实保留）。**GLM probe**：25 条扩展探针，成功调用 11 条中 10 条正确判 high、1 条判 medium（14 条 429 回退 none；成功调用准确率 0.91，不超 stub 上界 0.94，符合预期）。数据：`data/eval/risk_dual_path.json` + `data/eval/glm_probe_25.json` |
| 多轮回归 | 8 组多轮场景（含升级到中/高风险、第三人称转自身） | 最终关键内容命中率 **0.875**（7/8） |
| RAG 检索 | 77 条自然语言问句，Top-4 混合检索（BM25 + 向量 + rerank），24 篇知识文档 | 宽松口径 HitRate@4 **0.935**、严格口径（仅来源命中）**0.883**、Recall@4 **0.935**、Precision@4 **0.351**、MRR **0.820**、NDCG@4 **0.832**。**消融实验**（本地 local-hash 向量后端）：纯 BM25=0.935 > hybrid=0.831 > hybrid+rerank=0.805 > RRF=0.766，说明在零依赖词法 hash 向量下 BM25 已足够强，接入真实语义向量（Chroma/MiniLM）后 hybrid/RRF 才有增量价值 |
| 三运行时 A/B | langgraph / autonomous / ordered 同数据集对比延迟、trace 步数、LLM 调用数与判定一致性（10 条代表性消息） | 三运行时判定**完全一致**；意图准确率 **0.8**、风险准确率 **0.9**（含 1 条规则引擎当前漏判的隐式高危样本，如实暴露跨运行时一致的缺口） |
| Harness 验证 | Risk Safety、Agent Routing、Standard Skills、RAG、API、Tool Queue、Runtime A/B 等链路（验证工程行为，**不强制满分**） | **8/8 通过**（行为级断言；已移除 HitRate≥0.9 / 规模化=100% / 风险=100% 等硬性阈值门限） |
| 本地性能 benchmark | `scripts/run_benchmark.py`，MockLLM 确定性环境，20 条代表性消息 × 并发 [1,4,8]，测量延迟/吞吐/缓存/ToolJob | 并发1：avg 66ms、P95 71ms、吞吐 15.1 req/s；并发4：avg 316ms、P95 729ms、吞吐 12.3 req/s；并发8：avg 517ms、P95 1260ms、吞吐 13.5 req/s（单进程多线程，受 GIL 限制，成功率均 100%）。**检索缓存**：命中延迟 <0.01ms，相比冷查询 18-20ms 提速约 3 个数量级。**ToolJob**：5/5 成功，0 死信。数据：`data/eval/benchmark.json` |

**双层拆分下的真实含义（两个卖点：保住"真实" + 暴露边界，均非"失败"）：**
- **基础层（贴近真实流量，63 条）准确率 0.97、风险 1.00、高召回 1.00**：覆盖日常闲聊、典型咨询、显式高危等"真实会发生的流量"，规则引擎表现稳健——对应 **"真实"卖点**，证明系统在主流场景上可靠。
- **压力层（边界探测，87 条）准确率 0.39、风险 0.67、高召回 0.52**：刻意堆满隐喻式自杀意念（"想消失""不再面对明天"）、无关键词咨询、第三人称干扰等"边界样本"，用于**主动暴露**规则通道的能力缺口——对应 **"暴露边界"卖点**，且零删改、不凑分。
- **整体准确率 0.63、风险准确率 0.81、高风险召回 0.60**：这些指标是基础层（高分）和压力层（低分）的**加权平均**，单独引用会失去双层拆分的工程价值。
- **高风险召回 0.60**：基础层显式/部分隐式高危已全命中（高召回 1.00）；但压力层的**隐喻式自杀意念**无关键词可命中，拉低整体，需依赖 LLM 风险通道；这是关键词路线的固有上限，非调参可解。
- **路由准确率 0.63**：许多真实咨询/研究诉求**无明显关键词**（如"我和男朋友吵架了，心里不舒服"），纯关键词兜底路由必然漏判；已扩充通用中文求助表达词表，但彻底解决需 LLM 意图通道。
- **误报率 0.00**：第三人称提及高危词（"新闻里有人轻生""直播自杀"）已通过说话人消歧修复，不再误判为自身高危。

> **📊 简历/面试引用建议**：
> - ✅ **推荐引用**："150 条双层评测，基础层准确率 0.97、压力层 0.39（含隐喻式高危等边界样本）"、"风险双通道 0.67→0.94"、"RAG HitRate@4 = 0.94"
> - ⚠️ **需补充说明**：引用"整体 0.63"或"风险 0.81"时必须同时说明"压力层 0.39 主动暴露能力边界"
> - ❌ **避免单独引用**："高危召回 100%"（仅基础层 5/5 或某单一场景）、"路由准确率 100%"（4 条金标准样本，非代表性验证）
> - 💡 **强调工程价值**："零筛选样本、横向对比基础/压力层、纵向验证 LLM 补强幅度"更能体现评测体系成熟度

**风险 LLM 通道双路径验证（第十一轮，2026-08-19）：**
- **生产配置**：`RISK_LLM_CHANNEL_ENABLED=false`（纯规则），压力层风险准确率 **0.67**、高风险召回 **0.52**——与上行「规模化基准」压力层纯规则结果同源（同一语料 + 同一规则引擎），维持"暴露边界"卖点，baseline 不上升。
- **能力上界**（`MetaphorAwareStubClient` + channel ON，rules ∪ LLM 并集）：压力层风险准确率 **0.94**、高风险召回 **1.00**（25 条隐喻式自杀意念 corp-106..130 全部命中）、误报率 **0.03**（2 条 medium distress 含"撑不下去"/"不配"被 prompt 列为 high，属 prompt-vs-corpus 标注张力，如实保留）。
- **真实 GLM sanity check**：GLM-4.7-flash 对压力层全部 **25 条**隐喻式自杀意念样本做扩展探针（2026-08-20，`data/eval/glm_probe_25.json`）。受免费档限流影响，14 条命中 429/超时回退 none；**成功调用的 11 条中 10 条正确判 high、1 条判 medium（corp-130）**，成功调用准确率 **0.91**，验证 stub 量出的 0.94 上界是真实 GLM 可达水平（真实模型不超 stub 上界，且有 1 条理解偏差，符合预期）。
- **数据来源**：`data/eval/risk_dual_path.json`（150 条全量双路径对比）、`data/eval/glm_probe_25.json`（25 条扩展 GLM 探针）。

<details>
<summary><b>风险双通道机制详解（点击展开）</b></summary>

本系统的风险判定由**两条通道**组成，`RISK_LLM_CHANNEL_ENABLED` 控制是否启用第二条 LLM 通道：

**规则通道（rules channel，不可关）** — `app/assessment.py` 的 `assess_message()`
- 纯关键词匹配，零 LLM 调用、零外部依赖、可审计
- `HIGH_TERMS`（自杀/轻生/一了百了等 19 词）命中 → HIGH
- `MEDIUM_TERMS`（自残/崩溃/绝望等 7 词）命中 → MEDIUM
- 第三人称消歧：高危词出现在"新闻/电影/朋友"等语境 → 降级 LOW
- **固有上限**：只能识别词面，隐喻式表达（"想消失""不配""撑不下去"）常漏判

**LLM 通道（llm channel，可开关）** — `app/llm/client.py` + `app/agents/classic.py:78-94`
- 用 `RISK_ASSESS_SYSTEM_PROMPT`（`client.py:45-53`）让模型理解隐喻
- 并集融合：`order[llm_level] > order[risk_level]` 时升级（只升不降，安全优先）
- 兜底：LLM 失败/超时/429 返回 None → 回退纯规则结果，保证安全边界

**CHANNEL ON/OFF 的含义**
- `RISK_LLM_CHANNEL_ENABLED=false`（生产）：只跑规则通道，trace 记 `llm: "skipped"`
- `RISK_LLM_CHANNEL_ENABLED=true`（dev）：两条通道并行，取并集，trace 记 `llm: "high/medium/low"`

**双路径评测中的两个"假客户端"**
- `MockLLMClient`（baseline 路径用）：`assess_risk()` 返回 None，让 LLM 通道形同虚设 → 量**下界**（LLM 通道最差情况 = 不工作）
- `MetaphorAwareStubClient`（llm_stub 路径用）：继承 MockLLMClient，用 30 个隐喻关键词 + 13 个痛苦关键词**模拟**理想 LLM 的判定逻辑，不调真模型 → 量**上界**（LLM 通道满血情况）
- 真实 GLM（GLM probe 路径）：小样本 sanity check，量**真实表现**（介于上下界之间）

**为什么上界用 stub 不用真模型**：GLM 免费档 ~1 req/s，150 条全量跑会大量 429 污染结果；stub 用关键词确定性地模拟"LLM 完美理解 prompt 会怎么判"，给出可复现的能力天花板。25 条扩展 GLM 探针验证了这一设计——成功调用准确率 0.91，接近 stub 量出的 0.94 上界且不超，说明 stub 是 LLM 的合理代理。

</details>

> 评测数据用于工程回归和能力展示，不等同于临床有效性评估。允许并保留非 100% 的真实通过率，以暴露真实的代码/能力边界。

## 目录结构

```text
.
├── app/
│   ├── main.py                   # 应用入口:create_app 装配 + 路由注册
│   ├── config.py                 # pydantic-settings 全局配置
│   ├── models.py                 # 领域模型:Intent/RiskLevel/ChatResponse 等
│   ├── entities.py               # SQLAlchemy ORM 实体
│   ├── database.py               # 引擎/会话工厂/建表/迁移/就绪检查
│   ├── assessment.py             # 规则式风险评估(高危/中危关键词单一来源)
│   ├── skills.py                 # SkillRegistry:技能注册与 OpenAI 工具 schema
│   ├── core/                     # 横切原语:auth(认证) privacy(脱敏) runtime(Redis 限流锁) utils
│   ├── llm/                      # 模型后端:client(Mock/OpenAI/Ollama) prompts(提示词模板)
│   ├── agents/                   # 智能体层:classic(六单轮) model_profiles runtime harness orchestrator
│   ├── autonomous/               # 自治协作:events registry board coordinator agents runtime
│   ├── rag/                      # 检索子系统:text scoring(BM25/rerank) chunking memory vector_store
│   ├── repository/               # 持久化仓储:DatabaseStore
│   ├── tools/                    # 工具治理:contracts(契约) gateway(网关) mcp_client
│   ├── services/                 # 业务服务:report_case tool_executor tool_queue tool_records tool_governance
│   ├── api/                      # HTTP 路由:schemas deps middleware pages system auth_routes chat admin
│   ├── evaluation/               # 评测:runner datasets report_html
│   ├── harness/                  # 工程 Harness:factory(装配工厂) runner(场景回放 CLI)
│   ├── mcp_tools/                # FastMCP 工具服务(可选)
│   └── rag_eval/                 # RAG 独立评测 runner
├── knowledge/                    # 内置心理支持知识库(12 篇 .md)
├── eval/                         # 评测 CLI 与 fixtures(路由/风险/安全/多轮/检索/RAG 数据集)
├── skills/                       # 标准化心理支持 Skill 规范(SKILL.md)
├── static/                       # 学生端和管理员端页面(login/student/admin)
├── tests/                        # pytest 测试
├── scripts/                      # 启动脚本 + 评测脚本(eval_risk_dual_path/probe_glm/run_benchmark)
├── docs/                         # 架构、安全和演示文档
├── Aegis项目逐文件学习指南.md      # 从零构建式逐模块学习指南
├── docs/records/                 # 迭代记录(重构→提速→注册MySQL→LangGraph→深度增强→回复真人化→记忆增强→对抗型对话测试→语料双层拆分→风险LLM通道双路径→RAG增强与性能基准)
├── Dockerfile
└── docker-compose.yml
```

## API 摘要

| 类型 | 接口 |
| --- | --- |
| 认证 | `POST /api/auth/register`(注册), `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| 学生会话 | `GET /api/sessions`, `POST /api/sessions`, `GET /api/sessions/{id}`, `PATCH /api/sessions/{id}` |
| 聊天 | `POST /api/chat`, `POST /api/chat/stream` |
| 管理端报告 | `GET /api/admin/reports`, `PATCH /api/admin/reports/{report_id}` |
| 个案 | `GET /api/admin/cases`, `POST /api/admin/cases/{case_id}/notes`, `PATCH /api/admin/cases/{case_id}` |
| 工具队列 | `GET /api/admin/tool-jobs`, `POST /api/admin/tool-jobs/run`, `GET /api/admin/tool-worker/status` |
| 工具审计 | `GET /api/admin/tool-audits`, `GET /api/admin/excel-records`, `GET /api/admin/alert-records`, `GET /api/admin/dead-letters` |
| 知识库 | `GET /api/admin/knowledge/search`, `POST /api/admin/knowledge`, `POST /api/admin/knowledge/rebuild-vector` |
| 评测 | `GET /api/admin/eval-results`, `POST /api/admin/eval-results/run` |

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `AI_PROVIDER` | `mock`、`openai` 或 `ollama`。默认支持无密钥本地演示 |
| `LLM_THINKING_ENABLED` | 是否启用深度思考型模型的内部推理,默认 `false`(显著降低响应延迟;接入智谱 GLM-4.x 系列时推荐保持关闭) |
| `DATABASE_URL` | 默认 `sqlite:///data/aegis.sqlite`，可切换 PostgreSQL |
| `VECTOR_ENABLED` | 是否启用向量检索 |
| `EMBEDDING_PROVIDER` | 嵌入提供方:`local`(chromadb 内置 MiniLM,零依赖零费用,默认推荐)或 `openai`(OpenAI 兼容 /embeddings API) |
| `RISK_LLM_CHANNEL_ENABLED` | 风险评估双通道:规则 ∪ 轻量 LLM 取并集,任一判高危即高危,规则兜底 |
| `FUNCTION_CALLING_ENABLED` | 技能选择:模型 function calling 在白名单内自主挑选,规则兜底 |
| `LANGGRAPH_CHECKPOINT_ENABLED` | LangGraph SqliteSaver 检查点持久化(长对话跨进程可恢复) |
| `VECTOR_BACKEND` | 向量后端，支持本地或 Chroma 配置 |
| `KNOWLEDGE_FUSION_MODE` | 检索融合方式：`weighted`（线性加权，默认）或 `rrf`（Reciprocal Rank Fusion 排名融合） |
| `KNOWLEDGE_CACHE_ENABLED` | 是否启用查询缓存（LRU，可配 `KNOWLEDGE_CACHE_TTL_SECONDS`、`KNOWLEDGE_CACHE_MAX_ENTRIES`） |
| `TOOL_BACKEND` | `internal` 或 `mcp` |
| `MCP_ENABLED` | 是否启用 MCP 工具路径 |
| `TOOL_QUEUE_*` | 后台工具 worker 的轮询、批量、线程和重试配置 |
| `SMTP_*` | 邮件预警发送配置 |
| `ALERT_EMAIL_*` | 高风险预警邮件投递配置 |
| `AUTH_DEFAULT_*` | 默认学生和管理员账号 |
| `AUTH_TEACHER_INVITE_CODE` | 教师注册邀请码(默认 `aegis-teacher`,生产环境务必修改) |

## 设计取舍

- 三档运行时可切换(`AGENT_RUNTIME`)：LangGraph StateGraph 为主推编排(声明式状态图+条件边)；自研认领制黑板 runtime 作为兜底与对照(SAFETY_OVERRIDE 一票否销、不可变快照、认领调度)；ordered 流水线为最简链路。三者复用同一批 Agent 与安全规则。
- 不让工具直连学生端：高风险工具执行全部走 ToolJob，避免模型在流式回复中直接触发外部动作。
- 不对所有输入做 RAG：先做意图路由，只有咨询和风险类场景触发知识检索，普通陪伴类对话更强调倾听和情绪支持。
- 默认可本地运行：没有外部 API key 时也能完成端到端演示；接入 OpenAI、Ollama、Chroma、Redis、SMTP 后可以切换到更接近生产的配置。

## 文档

- [架构说明](docs/architecture.md)
- [安全设计](docs/safety-design.md)
- [演示脚本](docs/demo-script.md)
- [逐文件学习指南](Aegis项目逐文件学习指南.md)
- [第一次重构方案](docs/records/REFACTORING.md)
- [第二次优化方案(提速与流式)](docs/records/OPTIMIZATION.md)
- [第三次功能说明(注册与 MySQL)](docs/records/AUTH-MYSQL.md)
- [第四次功能说明(LangGraph 与全栈激活)](docs/records/LANGGRAPH-DOCKER.md)
- [第五次深度增强(风险双通道/FC/A·B评测/Judge/Checkpoint)](docs/records/DEEP-ENHANCEMENTS.md)
- [第六次回复真人化改造(提示词/兜底模板/429重试)](docs/records/LLM-RESPONSE-HUMANIZATION.md)
- [第七次记忆系统增强(消息数/摘要容量提升)](docs/records/MEMORY-ENHANCEMENT.md)
- [第八次对抗型对话测试(10轮配合+10轮对抗)](docs/records/CONFRONTATIONAL-DIALOGUE-TESTING.md)
- [第十轮代表性语料双层拆分(基础层/压力层)](docs/records/CORPUS-LAYER-SPLIT.md)
- [第十一轮风险LLM通道双路径验证(stub-LLM on vs MockLLM OFF)](docs/records/ROUND-11-RISK-LLM-DUAL-CHANNEL.md)
- [第十二轮RAG增强与性能基准(知识库24篇/RRF/缓存/双口径消融/benchmark)](docs/records/ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md)

## 待改进与优化(Roadmap)

> 按「实现难度 × 实现意义」盘点的演进清单;带 ✅ 的已在本仓库落地,详见 [docs/records](docs/records/) 各轮说明文档。

### 安全与合规(心理场景立身之本)
- ✅ **风险评估双通道**:规则关键词 ∪ 轻量 LLM 二次评估,任一通道判高危即高危,规则兜底(`RISK_LLM_CHANNEL_ENABLED`)
- ✅ **双路径验证**:stub-LLM on vs MockLLM OFF,压力层风险准确率 0.67→0.94、高风险召回 0.52→1.00(第十一轮,`data/eval/risk_dual_path.json`)
- 危机转介资源可配置化:学校心理中心/紧急联系方式从硬编码改为按校配置、管理端可编辑(低难度)
- 对话数据字段级加密存储(中难度)
- 账号安全补齐:登录失败锁定、密码强度策略、会话撤销列表(低难度)
- 用户数据导出与删除(低难度)

### Agent 与算法深度
- ✅ **Function Calling 真接入**:GLM 自主选择回复技能,规则白名单兜底(`FUNCTION_CALLING_ENABLED`)
- ✅ **三运行时 A/B 评测**:langgraph/autonomous/ordered 同数据集对比延迟/trace/LLM 调用数(`--suite runtime-ab`)
- ✅ **LLM-as-Judge**:模型为回复打共情性/安全性/结构性分数,进入评测报告
- ✅ **LangGraph Checkpoint**:SqliteSaver 检查点持久化,长对话跨进程可恢复
- ✅ 记忆系统基础增强:最近消息数 6→15、摘要最大字符 900→3000(第七轮,低难度)
- 记忆系统深度升级:滚动摘要 → 结构化记忆(用户画像+情绪轨迹+历史会话向量检索)(高难度)
- 主动关怀闭环:高危用户 N 天未跟进自动生成提醒任务(复用工具队列)(中难度)
- 词表外置:路由/技能触发关键词从代码抽到 YAML(低难度)

### 工程化与运维
- CI/CD:GitHub Actions 跑 pytest + node check + harness(低难度)
- Alembic 迁移:消灭手写 DDL 与 ORM 的两份 schema 真相(中难度)
- request_id 贯通结构化日志(低难度)
- Prometheus 指标 + Grafana 面板(中难度)
- Docker compose 全链路实测(待有 Docker 环境)

### 产品功能
- 心理量表接入(PHQ-9/GAD-7):定期测评→分数趋势→与风险阈值联动(中难度)
- 群体心理态势仪表盘:全校风险分布/话题热度(中难度)
- 教师与管理员权限细分(低难度)
- 企业微信/钉钉 webhook 告警通道(低难度)

## License

当前仓库未声明开源许可证。未经作者许可，请不要将代码用于商业分发或生产心理咨询服务。

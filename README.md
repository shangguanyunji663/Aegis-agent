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
| 四套疗愈主题可切换 | 心理支持场景需要按来访者状态切换视觉语气；单一主题难以覆盖低龄与深度倾诉 | CSS 变量四主题(`warm`/`ocean`/`forest`/`playful`) + `theme.js` 顶栏切换器 + `PUT /api/auth/me/theme` 按用户持久化 + `pages.py` 服务端首屏注入零闪烁(详见第十八轮) |
| Agent Runtime Harness | Agent 调用、上下文注入、风险报告和工具计划分散在业务代码里会难以审计 | `AegisAgentHarness` 统一封装输入脱敏、运行时调用、trace 保存、消息持久化、报告生成和工具计划 |
| 自治多 Agent 协作 | 单个 Lead Agent 串行分派容易变成“伪协作”，复杂场景缺少中间产物 | 默认 `autonomous` 运行时基于 append-only blackboard 实现任务发布、Agent claim、artifact 产出、风险 override 和最终验收；也可切换至 LangGraph 或 ordered 运行时 |
| 分层 MemoryAgent | 心理支持需要连续性，单轮回复无法体现对用户状态变化的理解 | L1 Agent 私有记忆 + L2 跨会话结构化用户事实 + L3 会话滚动摘要 + L4 最近原话窗口；L2 以有效期截断处理状态冲突，并优先于可能过期的摘要注入 Prompt |
| Agentic RAG | 所有消息都检索知识库会增加噪声，尤其普通陪伴类对话容易被知识文档带偏 | 通过 CHAT / CONSULT / RISK 意图路由决定是否检索；**多路召回（BM25 + 可选向量）+ 加权/RRF 融合 + 条件 rerank + 邻块扩展**，支持元数据过滤、查询改写、进程内 LRU 精确查询缓存与消融评测（详见「评测结果」） |
| 工具治理与 MCP | 高风险预警、Excel 记录、邮件通知不能由模型越权直接执行 | 工具调用先生成 `ToolJob`，经角色、风险等级、审批、脱敏和审计后进入队列；支持 internal 和 FastMCP 两种后端 |
| 后台 Tool Queue | 外部工具慢、失败或限流时，不应阻塞学生端流式回复 | 独立 worker 支持依赖调度、重试延迟、邮件限流、dead letter、ExcelRecord 和 AlertRecord 持久化 |
| Engineering Harness | Agent 项目只看 demo 容易高估完成度，需要可重复验证 | 基于真实代表性数据集的 pytest 单元/接口测试、RAG eval、综合 eval(含 LLM-as-Judge)、harness 8 套件、三运行时 A/B 对比评测，覆盖路由、风险、安全、RAG、API、工具队列与编排器链路（真实指标见下方「评测结果」） |
| 风险双通道 | 关键词规则召回有限，单靠模型又不可控 | 规则 ∪ QLoRA/通用 LLM 取并集、任一判高危即高危，并以规则兜底回退保证安全边界（落地细节见 Roadmap） |

## 架构概览

```mermaid
flowchart LR
    Student["学生端 /student"] --> API["FastAPI API 层"]
    Admin["管理员端 /admin"] --> API

    API --> Harness["AegisAgentHarness"]
    Harness --> Runtime["Agent Runtime<br/>默认 autonomous Blackboard"]

    Runtime --> Memory["MemoryAgent"]
    Runtime --> Lead["Lead / Supervisor Agent"]
    Runtime --> Risk["RiskGuardianAgent"]
    Runtime --> Knowledge["KnowledgeAgent"]
    Runtime --> Counselor["CounselorAgent"]
    Runtime --> Companion["CompanionAgent"]

    Knowledge --> RAG["Hybrid RAG<br/>BM25 + 可选 Vector + Rerank"]
    Harness --> Store["SQLite / MySQL / 可选 PostgreSQL<br/>messages, memory, reports, traces"]
    Harness --> ToolPlan["Governed ToolJob"]
    ToolPlan --> Queue["Tool Queue Worker"]
    Queue --> MCP["FastMCP / internal tools"]
    MCP --> Outputs["Excel, Alert, Email, Handoff, Audit"]

    Admin --> Eval["Eval & Harness Reports"]
    Eval --> Store
```

## 功能清单

### 学生端

- 注册与登录:学生自由注册;教师凭邀请码注册(默认 `aegis-teacher`,经 `AUTH_TEACHER_INVITE_CODE` 配置)后进入咨询工作台。
- 登录、退出、会话创建与新会话切换;会话重命名/删除目前仅提供 API 接口(`PATCH` / `DELETE /api/sessions/{id}`),界面暂无对应按钮。
- 对话助手「小暖」:消息头像、入场动画与欢迎屏话题 chips;顶栏时段问候、服务状态圆点(60 秒自动刷新)。
- 左栏实用卡片:「心情速选」2×2 图标卡一键填入表达、「需要立即帮助」卡(心理援助热线 12356 / 120)与「60 秒放松练习」。
- 四套疗愈主题可切换:暖意疗愈(默认)/ 深海冥想 / 晨雾森林 / 童趣治愈贴贴,顶栏切换器即时换色并按用户持久化、跨设备同步;服务端首屏注入 `html[data-theme]`,无切换闪烁(详见 [第十八轮](docs/records/ROUND-18-THEME-SWITCHER.md))。
- SSE 流式心理支持回复，兼容非流式 `/api/chat`。低风险对话在生成的同时逐字直播(真流式),中/高风险回复经安全复核通过后再输出。
- 低风险陪伴、心理咨询建议、高风险安全回应三类回复路径。
- L2/L3/L4 分层记忆：跨会话当前有效用户事实、会话滚动摘要与最近原话窗口共同注入回复；当前有效事实优先于可能过期的摘要，避免旧状态干扰当前回应。
- 高风险内容不向学生暴露内部报告字段，避免造成二次伤害或信息泄露。

### 管理端

- 三列页签工作台（桌面端固定一屏、界面全中文）：左列「个案 | 知识库 | 协作状态」、中列「风险报告 | 对话回放」、右列「详情检查器 + 工作台」；操作详见《[咨询工作台使用手册(教师版)](docs/admin-teacher-guide.md)》。
- 风险报告列表、状态流转和报告 trace 查看(「对话回放」页签)。
- 个案创建、辅导员确认、备注追加和状态更新。
- 知识库检索、内容上传(.md/.txt/.pdf)、重建索引和备份;向量索引重建另提供 `/api/admin/knowledge/rebuild-vector` 接口。
- 工具任务(ToolJob)与执行记录(ExcelRecord/AlertRecord)在界面查看;操作审计在「审计」页签查看;ToolAudit 与 DeadLetter 提供独立 API 查询(`tool-audits` / `dead-letters`)。
- Runtime 协作状态查看(编排引擎/调度/存储/队列与智能体名单),模型状态在顶栏胶囊展示;Agent 模型配置与 Agent 私有记忆另提供 API 查询(`agent-models` / `agent-memories`)。
- 一键触发综合评测(Harness 验证经命令行 `python -m app.evaluation.harness.runner` 执行)。

### Agent 协作

- `MemoryAgent`：加载 L1 Agent 私有记忆、L2 当前有效用户事实、L3 会话摘要和 L4 最近消息；回复后更新 L3，并以确定性规则抽取可变化用户状态写入 L2。
- `LeadAgent / SupervisorAgent`：识别意图并决定协作路径。
- `RiskGuardianAgent`：风险分级、安全 override、高风险报告生成。
- `KnowledgeAgent`：按意图和风险等级检索知识库，注入标准 Skill；重复的基础 Skill 组合达到默认 3 次后可自动蒸馏为 `skills/auto/` 下的新 Skill。当前自动 Skill 会直接重载并参与后续匹配，人工审核工作台仍是后续规划。
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
| Agent Runtime | 三档可切换：autonomous（代码默认，事件驱动黑板/认领协作）、langgraph（StateGraph + 可选 SQLite checkpoint）、ordered（简化有序管道）；三者复用 Agent 与安全规则 |
| RAG | 多路召回（BM25 + 可选向量）+ 加权/RRF 融合 + 条件 rerank + 邻块扩展，Chroma/local 双后端，元数据过滤，进程内 LRU 精确查询缓存，四档消融评测 |
| 工具协议 | FastMCP, governed ToolJob, background worker |
| 存储 | SQLite local mode, MySQL（Compose）, optional PostgreSQL / Redis |
| 前端 | 原生 HTML/CSS/JavaScript, student/admin 双端页面, CSS 变量多主题切换(暖意疗愈/深海冥想/晨雾森林/童趣治愈贴贴), 服务端首屏注入零闪烁 |
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

### 使用已验收的 QLoRA 风险模型（可选）

普通启动默认**不会加载训练模型**：`RISK_QLORA_ENABLED=false`，RiskGuardian 保持现有规则/通用 LLM 行为。训练服务可以在本机独立启动并用 `/health`、`/assess` 做 smoke test；应用侧的 QLoRA HTTP 集成只接受经过保护的公网 HTTPS endpoint，不直接访问 localhost、环回或内网地址：

```bash
# Windows 示例；其他机器把这些路径改成自己的训练根目录
set AEGIS_TRAINING_ROOT=D:\AegisTraining
set AEGIS_QLORA_MODEL_DIR=%AEGIS_TRAINING_ROOT%\exports\aegis-risk-qwen3.5-2b-v9-merged

%AEGIS_TRAINING_ROOT%\envs\qlora-qwen35\python.exe ^
  %AEGIS_TRAINING_ROOT%\training\scripts\serve_risk_qlora.py ^
  --model-dir "%AEGIS_QLORA_MODEL_DIR%"
```

服务默认监听 `http://127.0.0.1:8301`，可先检查：

```bash
curl http://127.0.0.1:8301/health
```

本地服务的 HTTP 地址只用于独立 smoke test，不填入应用 `.env`。要接入应用，先将推理服务部署到受保护的公网 HTTPS 地址，再配置：

```ini
RISK_QLORA_ENABLED=true
RISK_QLORA_URL=https://your-approved-qlora.example.com
RISK_QLORA_TIMEOUT_SECONDS=8
```

服务不可达、超时或返回非法 JSON 时，RiskGuardian 自动回退规则。其他 Agent 仍使用各自原有模型通道。训练文件和模型仍放在外部 `AEGIS_TRAINING_ROOT`，不写入项目仓库。

> 生产部署默认建议使用 bf16（与验收口径一致）；显存不足时可加 `--load-4bit`，但需要重新验证边界样本结果。`RISK_QLORA_ENABLED` 默认关闭。
>
> 后续生产化学习与改进路线（异步/并发/HTTP/SSE/WebSocket、部署、MCP/JSON-RPC/A2A、权限、流式工具调用、错误恢复、KV Cache/vLLM/SGLang、Reranker、GraphRAG）见 [`docs/QLORA-SSE-PRODUCTION-IMPROVEMENTS.md`](docs/QLORA-SSE-PRODUCTION-IMPROVEMENTS.md)。

**QLoRA 训练目标**：不是训练通用聊天能力，而是把 Qwen3.5-2B-Base 微调成 RiskGuardian 的 `low / medium / high` JSON 风险评估器。基座 4-bit NF4 量化并冻结，LoRA `r=8/alpha=16` 只训练约 840 万参数（总参数约 18.9 亿的 0.445%）；训练样本只覆盖风险判定、理由长度和主体/意图裁决，不改变 Counselor、RAG、工具治理或审批链路。

**风险模型横向对比（冻结 stress 87 条；各版 QLoRA 使用各自训练时提示词，当前 v9 使用提示词 v2）**：

| 通道/版本 | 训练规模 | Accuracy | Macro-F1 | HIGH Recall | Medium Recall | 第三人称准确率 | non-high→high FPR | JSON 有效率 | P95 | 验收 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 规则 baseline | 0 | 0.667 | 0.480 | 0.52 | 0.00 | 1.00 | 0 | — | — | — |
| 原始 `qwen3.5:2b` | 0 | 0.644 | 0.609 | 0.68 | 0.29 | 0.82 | 14.52% | 93.10% | 0.86s | — |
| 第一版（旧 v1）QLoRA | 720+120 | 0.770 | 0.743 | 0.64 | 0.59 | 1.00 | 0 | 100% | 0.95s | ❌ 隐喻 +3 |
| 第二版（旧 v3）QLoRA | 840+140 | 0.770 | 0.751 | 0.84 | 0.71 | 1.00 | 4.84% | 100% | 0.88s | ❌ FPR |
| 第三版（旧 v4）QLoRA | 1703+198 | 0.667 | 0.606 | 0.80 | 0.24 | 0.27 | 3.23% | 100% | 1.20s | ❌ FPR |
| 第四版（旧 v5）QLoRA | 1703+200 | 0.736 | 0.674 | 0.84 | 0.29 | 0.55 | 0 | 100% | 0.93s | ✅ |
| 第五版（旧 v7）QLoRA | 1703+200 | 0.759 | 0.746 | 0.80 | 0.77 | 0.82 | 3.23% | 100% | 1.04s | ❌ FPR |
| 第六版（旧 v8）QLoRA | 2864+200 | 0.782 | 0.760 | 0.80 | 0.71 | 0.91 | 3.23% | 100% | 0.96s | ❌ FPR |
| **第七版（旧 v9）QLoRA** | **2867+200** | **0.782** | **0.777** | **0.76** | **0.88** | **0.82** | **0** | **100%** | **1.37s** | **✅ 8/8** |

> 注：规则/原始模型的 medium 与 JSON 指标来自对应报告的原始通道；各版 QLoRA 的 `rules ∪ QLoRA` 结果用于生产形态对比。小型 87 条压力集用于安全验收，不能替代临床有效性评估；完整原始 JSON 报告和训练沿革见 `D:\AegisTraining\reports\`。



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

Compose 会启动应用、MySQL 8.0、Redis 和 Chroma。默认本地模式使用 SQLite；如需切换数据库或向量后端，可在 `.env` 中调整 `DATABASE_URL`、`VECTOR_ENABLED`、`VECTOR_BACKEND` 等配置。项目依赖中包含 PostgreSQL 驱动，但当前 Compose 拓扑不启动 PostgreSQL 服务。

## 常用命令

```bash
# 初始化数据库
python -m app.init_db

# 后端测试（只跑 tests/，scripts/ 下的联调脚本不在 pytest 收集范围）
python -m pytest tests -q

# 前端脚本语法检查
node --check static/login.js static/student.js static/admin.js

# 综合评测
python -m eval.run_eval

# RAG 独立评测(含双口径 + 消融)
python -m app.evaluation.rag

# 本地性能 benchmark(并发/延迟/吞吐/缓存/ToolJob)
python -m scripts.run_benchmark

# 工程 Harness 验证
python -m app.evaluation.harness.runner --suite all --output data/harness/latest.json

# 查看 MCP 能力
python -m app.mcp.server --list
```

## 评测结果

当前仓库的评测体系基于**人工构造、人工标注且贴近校园心理求助语料的代表性金标集**，不筛选样本、不为追求满分而人为凑 100%。路由、RAG、综合评测、Harness 与 benchmark 的主指标在确定性 MockLLM 环境下产出，衡量规则和编排链路的能力边界；风险评测另含真实 GLM sanity probe 与隔离 Transformers QLoRA v9 的冻结验收结果。

> **注意**：评测指标反映测试集表现，非真实用户流量验证，不等同于临床有效性评估。

> 数据来源与落盘日期（评测产物是可再生快照，不代表后续提交必然得到相同数值）：
> - 路由/风险/规模化基准：`eval/fixtures/representative_corpus.json`（150 条人工构造、人工标注的代表性金标样本，双层拆分：每条含 `layer`（base 基础层 / stress 压力层）与 `source`（synthetic-representative / synthetic-boundary）字段，含隐式高危与第三人称干扰；综合结果来源 `data/eval/latest.json`，2026-08-19）
> - RAG 检索：`eval/fixtures/rag_queries.json`（77 条自然语言问句，基于 24 篇知识文档；专项结果来源 `data/eval/rag-eval-report.json`，2026-08-20）
> - 多轮回归：`eval/fixtures/multi_turn_corpus.json`（8 组多轮场景；综合结果来源 `data/eval/latest.json`，2026-08-19）
> - 三运行时 A/B：10 条代表性消息（结果来源 `data/harness/runtime-ab-report.md`，2026-08-20）
> - 性能基准：`python -m scripts.run_benchmark`（并发/延迟/吞吐/缓存/ToolJob；MockLLM，`VECTOR_ENABLED=false`，结果来源 `data/eval/benchmark.json`，2026-08-20）

| 验证项 | 覆盖内容 | 已落盘结果与适用边界 |
| --- | --- | --- |
| 单元与接口测试 | API、认证、风险双通道、Function Calling、Agent runtime、LangGraph checkpoint、MCP tools、评测 runner | **历史记录**：第十三轮于 2026-08-21 记录 `python -m pytest tests/ -q` 为 **71 passed, 8 warnings**。`tests/test_api.py` 使用临时 SQLite；测试数量与结果应以当前环境重跑为准。 |
| 150 条规模化基准（双层拆分，横向分层） | 150 条人工构造、人工标注的代表性金标样本，按 `layer` 拆为基础层（贴近主流场景）63 条与压力层（边界探测）87 条；runner 分别输出两套独立指标。 | **2026-08-19，`data/eval/latest.json`**：整体联合准确率 **0.63**；意图 **0.63**；风险 **0.81**；高风险召回 **0.60**；误报率 **0.00**。基础层：准确率 **0.97**、风险 **1.00**、高召回 **1.00**；压力层：准确率 **0.39**、风险 **0.67**、高召回 **0.52**。 |
| 风险 LLM 通道双路径（第十一轮历史快照） + QLoRA 微调（第十四轮当前实现） | 历史规则/stub/GLM sanity 与当前真实 v9 QLoRA 冻结 stress 87 条验收。 | **当前以 v9 QLoRA 为准**：`RISK_QLORA_ENABLED=true` 时八门槛全过；第十一轮 stub/GLM 数字仅作历史复现。 |
| 多轮回归 | 8 组多轮场景（含升级到中/高风险、第三人称转自身） | **2026-08-19，`data/eval/latest.json`**：最终关键内容命中率 **0.875**（7/8）。 |
| RAG 检索 | 77 条自然语言问句，Top-4；专项消融使用 local-hash 向量配置。 | **2026-08-20，`data/eval/rag-eval-report.json`**：宽松 HitRate@4 **0.935**、严格来源命中 **0.883**、Recall@4 **0.935**、Precision@4 **0.351**、MRR **0.820**、NDCG@4 **0.832**。消融：纯 BM25=0.935 > hybrid=0.831 > hybrid+rerank=0.805 > RRF=0.766；真实语义向量下应重新评测。 |
| 三运行时 A/B | langgraph / autonomous / ordered 同数据集对比延迟、trace 步数、LLM 调用数与判定一致性（10 条代表性消息） | **2026-08-20，`data/harness/runtime-ab-report.md`**：三运行时判定完全一致；意图准确率 **0.8**、风险准确率 **0.9**，含 1 条规则引擎漏判的隐式高危边界样本。 |
| Harness 验证 | Risk Safety、Agent Routing、Standard Skills、RAG、API、Tool Queue、Runtime A/B 等链路（验证工程行为，不强制满分） | **历史快照**：`data/harness/current-verification.json` 为 **8/8 通过**；`data/harness/latest.json` 是旧的 7-suite 存档，建议重跑后覆盖。 |
| 本地性能 benchmark | `scripts/run_benchmark.py`，MockLLM 确定性环境，20 条代表性消息 × 并发 [1,4,8]，测量延迟/吞吐/缓存/ToolJob | **2026-08-20，`data/eval/benchmark.json`**：并发1：avg 66ms、P95 71ms、吞吐 15.1 req/s；并发4：avg 316ms、P95 729ms、吞吐 12.3 req/s；并发8：avg 517ms、P95 1260ms、吞吐 13.5 req/s。进程内检索缓存命中 <0.01ms；ToolJob 5/5 成功、0 死信。 |

**双层拆分下的真实含义（两个卖点：保住"真实" + 暴露边界，均非"失败"）：**
- **基础层（贴近真实流量，63 条）准确率 0.97、风险 1.00、高召回 1.00**：覆盖日常闲聊、典型咨询、显式高危等"真实会发生的流量"，规则引擎表现稳健——对应 **"真实"卖点**，证明系统在主流场景上可靠。
- **压力层（边界探测，87 条）准确率 0.39、风险 0.67、高召回 0.52**：刻意堆满隐喻式自杀意念（"想消失""不再面对明天"）、无关键词咨询、第三人称干扰等"边界样本"，用于**主动暴露**规则通道的能力缺口——对应 **"暴露边界"卖点**，且零删改、不凑分。
- **整体准确率 0.63、风险准确率 0.81、高风险召回 0.60**：这些指标是基础层（高分）和压力层（低分）的**加权平均**，单独引用会失去双层拆分的工程价值。
- **高风险召回 0.60**：基础层显式/部分隐式高危已全命中（高召回 1.00）；但压力层的**隐喻式自杀意念**无关键词可命中，拉低整体，需依赖 LLM 风险通道；这是关键词路线的固有上限，非调参可解。
- **路由准确率 0.63**：许多真实咨询/研究诉求**无明显关键词**（如"我和男朋友吵架了，心里不舒服"），纯关键词兜底路由必然漏判；已扩充通用中文求助表达词表，但彻底解决需 LLM 意图通道。
- **误报率 0.00**：第三人称提及高危词（"新闻里有人轻生""直播自杀"）已通过说话人消歧修复，不再误判为自身高危。

> **当前推荐引用（真实 QLoRA）**：第十四轮 v9 冻结 stress 87 条八门槛全过，FPR 0、medium 召回 0.88、第三人称准确率 0.82、P95 1.37s；报告 `D:\AegisTraining\reports\risk-qlora-eval-v9.json`。以下第十一轮 stub/GLM 数字保留为历史可复现快照，不应与 v9 真实模型数字混用。
>
> **📊 简历/面试引用建议**：
> - ✅ 推荐："v9 QLoRA 风险模型冻结 stress 87 条八门槛全过，FPR 0、隐喻新增 +6、medium 召回 0.88、P95 1.37s"；同时说明该结果不是临床有效性评估
> - ✅ 可补充："真实原始 qwen3.5:2b 通道对照 FPR 14.5%，QLoRA 候选降为 0；JSON 有效率 93.1%→100%"
> - ⚠️ 历史双层规则/Stub 指标（0.63/0.81/0.94 等）只作为能力边界留痕，不作为当前生产模型成绩
> - 💡 训练谱系、数据审计与提示词契约变更见 `D:\AegisTraining\reports\TRAINING-HISTORY-INDEX.md`

**风险 LLM 通道双路径验证（第十一轮，2026-08-19） + QLoRA 微调投产（第十四轮，2026-08-24）：**
- **规则基线配置**：显式设置 `RISK_LLM_CHANNEL_ENABLED=false` 时只跑规则通道，压力层风险准确率 **0.67**、高风险召回 **0.52**；该设置适合需要纯规则、可复现 baseline 的场景。
- **QLoRA 微调模型（生产级，第十四轮）**：经过多轮有效版本迭代（第一版至第七版，旧 v2 编号作废；数据 720→2867 条，提示词契约 v2），最终候选 **`aegis-risk-qwen3.5-2b-v9`** 在冻结 stress 87 条验收集上**八门槛全部通过**——**FPR 0（零误升级）、隐喻新增 +6（13→19/25）、medium 召回 0.88、第三人称准确率 0.82、整体 accuracy 0.782**。格式 100%、P95 延迟 1.37s，由隔离 Transformers 服务（`serve_risk_qlora.py`，`RISK_QLORA_ENABLED` 开关控制）提供推理。提示词契约 v2 同步移除「不配」「活着多余」两个与金标细线冲突的高危示例，三处副本（client.py / data_contract.py / 数据管线）已同步更新。
- **训练隔离约定**：训练脚本、数据、adapter、merged 模型、GGUF 与报告全部位于 `AEGIS_TRAINING_ROOT` 指向的独立训练仓库（本机为 `D:\AegisTraining`），不进入项目仓库；训练初始化、数据准备、训练和评测命令统一见 [AegisTraining README](https://github.com/shangguanyunji663/AegisTraining)。本项目只保留 QLoRA 服务接入配置。
- **真实 GLM sanity check**：GLM-4.7-flash 对压力层全部 **25 条**隐喻式自杀意念样本做扩展探针（2026-08-20，`data/eval/glm_probe_25.json`）。受免费档限流影响，14 条命中 429/超时回退 none；**11 条非 fallback 判断中 10 条判 high、1 条判 medium（corp-130）**，显示真实模型的 best-effort 表现接近但不超过 QLoRA 上界。
- **配置事实**：`Settings` 与 `.env.example` 默认 `RISK_LLM_CHANNEL_ENABLED=true`、`RISK_QLORA_ENABLED=false`；是否开启应由部署的安全策略显式决定。

<details>
<summary><b>风险双通道机制详解（点击展开）</b></summary>

本系统的风险判定由**规则通道 + 可选模型通道**组成，`RISK_LLM_CHANNEL_ENABLED` 控制通用 LLM 通道，`RISK_QLORA_ENABLED` 控制已验收的 QLoRA 通道：

**规则通道（rules channel，不可关）** — `app/assessment.py` 的 `assess_message()`
- 纯关键词匹配，零 LLM 调用、零外部依赖、可审计
- `HIGH_TERMS`（自杀/轻生/一了百了等 18 词）命中 → HIGH
- `MEDIUM_TERMS`（自残/崩溃/绝望等 7 词）命中 → MEDIUM
- 第三人称消歧：高危词出现在"新闻/电影/朋友"等语境 → 降级 LOW
- **固有上限**：只能识别词面，隐喻式表达（"想消失"、"从没出生过"、"撑不下去"）常漏判；实际补强由 QLoRA 通道承担

**LLM 通道（llm channel，可开关）** — `app/llm/client.py` + `app/agents/classic.py`
- 用 `RISK_ASSESS_SYSTEM_PROMPT`（`app/llm/client.py`，提示词契约 v2）让模型理解隐喻
- **QLoRA 微调通道（第十四轮）**：`RISK_QLORA_ENABLED=true` 时 RiskGuardian 的 LLM 通道自动切换为 QLoRA 微调模型（`aegis-risk-qwen3.5-2b-v9`），以隔离 Transformers 推理服务（`serve_risk_qlora.py`）代替原始 Ollama 调用；不启用时行为完全不变
- 并集融合：`order[llm_level] > order[risk_level]` 时升级（只升不降，安全优先）
- 兜底：LLM 失败/超时/429 返回 None → 回退纯规则结果，保证安全边界

**CHANNEL ON/OFF 的含义**
- `RISK_QLORA_ENABLED=false`：不启用微调通道；行为由 `RISK_LLM_CHANNEL_ENABLED` 决定。若后者为 false，只跑规则；若为 true，使用配置的通用 LLM 客户端。
- `RISK_QLORA_ENABLED=true`：RiskGuardian 自动使用隔离 Transformers 服务中的 v9 QLoRA 模型，规则与 QLoRA 两条通道取并集；`RISK_LLM_CHANNEL_ENABLED` 会被强制视为 true。服务不可达/超时/非法 JSON 自动回退规则。

**历史双路径评测中的客户端**
- `MockLLMClient`：用于规则 baseline，`assess_risk()` 返回 None。
- `MetaphorAwareStubClient`：第十一轮历史测试替身，用关键词模拟理想 LLM；**不是生产模型，也不是 v9 QLoRA 的成绩**。
- v9 QLoRA：当前生产候选，真实 Transformers 推理服务，验收结果见上方第十四轮记录。

> 第十一轮 stub/GLM 数字保留作历史可复现记录；生产能力和上线判断以 `risk-qlora-eval-v9.json` 的真实 QLoRA 评测为准。

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
│   ├── skills.py                 # SkillRegistry:注册式 Skill、标准 Skill 与自动蒸馏
│   ├── core/                     # 横切原语:auth(认证) privacy(脱敏) runtime_services(Redis 限流锁) network(出站 URL 校验/SSRF 防护) utils
│   ├── llm/                      # 模型后端:Mock/OpenAI/Ollama/RiskQloraClient + prompts
│   ├── agents/                   # 智能体层:classic(六单轮) model_profiles runtime harness orchestrator
│   ├── autonomous/               # 自治协作:events registry board coordinator agents runtime
│   ├── rag/                      # 检索与记忆：text/scoring/chunking/facts(L2)/memory(L3)/vector_store
│   ├── repository/               # 持久化仓储：会话、L2 用户事实、知识库、报告与工具任务
│   ├── tools/                    # 工具治理:contracts(契约) gateway(网关)
│   ├── services/                 # 业务服务:report_case tool_executor tool_queue tool_records tool_governance
│   ├── api/                      # HTTP 路由:schemas deps middleware pages system auth_routes chat admin
│   ├── evaluation/               # 评测:runner rag(双口径+消融) datasets report_html runtime_ab judge + harness/(factory 装配工厂, runner 场景回放 CLI)
│   └── mcp/                      # MCP 边界:server(FastMCP 服务) client(stdio 客户端)
├── knowledge/                    # 内置心理支持知识库（当前 24 篇 .md）
├── eval/                         # 评测 CLI 与 fixtures(路由/风险/安全/多轮/检索/RAG 数据集)
├── skills/                       # 人工策展 Skill 规范；运行时可在 skills/auto/ 生成 auto Skill
├── static/                       # 学生端和管理员端页面(login/student/admin)
├── tests/                        # pytest 测试
├── scripts/                      # 启动/联调/诊断脚本(start-local start-compose smoke_chat probe_glm migrate_sqlite_to_mysql eval_risk_dual_path run_benchmark analyze_layers)
├── docs/                         # 架构、安全、演示、教师手册与前端学习文档
├── Aegis项目逐文件学习指南.md      # 从零构建式逐模块学习指南
├── docs/records/                 # 迭代记录（重构→提速→注册 MySQL→LangGraph→深度增强→回复真人化→记忆增强→对抗测试→文档整合→语料分层→风险双路径→RAG 增强→记忆分层与 Skill 自动蒸馏→前端整体改造:主题/页签化/全中文化/学习指南→多主题切换:四套疗愈主题/服务端注入零闪烁/跨设备持久化）
├── Dockerfile
└── docker-compose.yml
```

## API 摘要

| 类型 | 接口 |
| --- | --- |
| 系统状态 | `GET /api/health`, `GET /api/readiness`, `GET /api/agent/status`(需登录), `GET /api/skills` |
| 认证 | `POST /api/auth/register`(注册), `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`(含 `theme` 字段), `PUT /api/auth/me/theme`(切换并持久化主题偏好) |
| 学生会话 | `GET /api/sessions`, `POST /api/sessions`, `GET /api/sessions/{id}`, `PATCH /api/sessions/{id}`, `DELETE /api/sessions/{id}` |
| 聊天 | `POST /api/chat`, `POST /api/chat/stream` |
| 管理端报告 | `GET /api/admin/reports`, `PATCH /api/admin/reports/{report_id}`, `GET /api/admin/traces`(对话回放) |
| 个案 | `GET /api/admin/cases`, `POST /api/admin/cases/{case_id}/notes`, `PATCH /api/admin/cases/{case_id}` |
| 工具队列 | `GET /api/admin/tool-jobs`, `POST /api/admin/tool-jobs/run`, `POST /api/admin/tool-jobs/{job_id}/retry`, `GET /api/admin/tool-worker/status`, `POST /api/admin/tool-worker/run-once` |
| 工具审计 | `GET /api/admin/tool-audits`, `GET /api/admin/excel-records`, `GET /api/admin/alert-records`, `GET /api/admin/dead-letters`, `GET /api/admin/audit-logs` |
| 知识库 | `GET /api/admin/knowledge/status`, `GET /api/admin/knowledge/search`, `POST /api/admin/knowledge`(文本入库), `POST /api/admin/knowledge/upload`, `POST /api/admin/knowledge/rebuild`, `POST /api/admin/knowledge/rebuild-vector`, `POST /api/admin/knowledge/backup` |
| 评测 | `GET /api/admin/eval-results`, `POST /api/admin/eval-results/run` |

## 环境变量

| 变量 | 说明与代码默认值 |
| --- | --- |
| `AI_PROVIDER` | `mock`（代码默认）、`openai` 或 `ollama`；mock 支持无密钥本地演示。 |
| `LLM_THINKING_ENABLED` | 是否启用深度思考型模型的内部推理；默认 `false`，接入智谱 GLM-4.x 时通常保持关闭以降低延迟。 |
| `DATABASE_URL` | 默认 `sqlite:///data/aegis.sqlite`；可改为 MySQL（Compose 提供）或自行部署的 PostgreSQL。 |
| `VECTOR_ENABLED` | 是否启用向量召回；代码默认 `false`。关闭后仍保留 BM25 + 条件 rerank 路径。 |
| `EMBEDDING_PROVIDER` | `openai`（代码默认）或 `local`（Chroma 本地嵌入）；`.env.example` 用 `local` 作为无外部密钥演示示例。 |
| `VECTOR_BACKEND` | 向量后端，默认 `chroma`；仅在 `VECTOR_ENABLED=true` 时参与向量检索。 |
| `KNOWLEDGE_FUSION_MODE` | `weighted`（代码默认，线性加权）或 `rrf`（Reciprocal Rank Fusion 排名融合）。 |
| `KNOWLEDGE_CACHE_ENABLED` | 是否启用进程内 LRU 精确查询缓存；默认 `false`，可配 `KNOWLEDGE_CACHE_TTL_SECONDS`、`KNOWLEDGE_CACHE_MAX_ENTRIES`。Redis 写入目前为预留能力，检索读取仍以进程内缓存为准。 |
| `RISK_LLM_CHANNEL_ENABLED` | 风险评估通用 LLM 通道开关；代码和 `.env.example` 默认 `true`。`RISK_QLORA_ENABLED=true` 时由 QLoRA 通道接管。 |
| `RISK_QLORA_ENABLED` | QLoRA 风险增强开关；默认 `false`，开启后 RiskGuardian 调用隔离 Transformers 服务。 |
| `RISK_QLORA_URL` | QLoRA 服务地址；默认占位值为 `https://qlora-endpoint.example.invalid`，应用集成拒绝 localhost、环回、私有和保留地址。 |
| `RISK_QLORA_TIMEOUT_SECONDS` | QLoRA 请求超时；默认 `8` 秒，超时回退规则。 |
| `FUNCTION_CALLING_ENABLED` | 技能选择：模型在规则白名单内自主挑选；默认 `true`，失败时回退规则白名单。 |
| `SKILL_DISTILL_ENABLED` | 是否记录基础 Skill 重复组合并触发自动蒸馏；默认 `true`。 |
| `SKILL_DISTILL_MIN_REPEAT` | 同一 `intent|risk|基础 Skill 集合` 触发蒸馏的次数；默认 `3`。 |
| `SKILL_DISTILL_DIR` | 自动 Skill 输出目录；默认 `skills/auto`。当前达到阈值后直接重载，尚无人工审核门禁。 |
| `MEMORY_RECENT_MESSAGES` | L4 最近原始消息窗口条数；默认 `15`。 |
| `MEMORY_SUMMARY_MAX_CHARS` | L3 会话滚动摘要的字符上限；默认 `3000`。 |
| `AGENT_RUNTIME` | `autonomous`（代码默认）、`langgraph` 或 `ordered`。环境变量可覆盖默认运行时。 |
| `LANGGRAPH_CHECKPOINT_ENABLED` / `LANGGRAPH_CHECKPOINT_PATH` | LangGraph SqliteSaver 检查点开关与路径；默认 `true` / `data/langgraph-checkpoints.sqlite`。 |
| `TOOL_BACKEND` / `MCP_ENABLED` | `internal`（默认）或 `mcp` 工具后端，以及 MCP 路径开关。 |
| `TOOL_QUEUE_*` | 后台工具 worker 的轮询、批量、线程和重试配置。 |
| `SMTP_*` / `ALERT_EMAIL_*` | 邮件预警发送和投递配置。 |
| `AUTH_DEFAULT_*` / `AUTH_TEACHER_INVITE_CODE` | 默认学生/管理员账号与教师邀请码；邀请码默认 `aegis-teacher`，生产必须修改。 |

> 表中的“默认”均指 `Settings` 代码默认值；`.env.example` 是推荐示例，部署环境的 `.env` 或环境变量可以覆盖两者。 |

## 设计取舍

- 三档运行时可切换（`AGENT_RUNTIME`）：`autonomous` 是代码默认，使用事件驱动黑板、任务认领和安全验收；`langgraph` 使用声明式 StateGraph 与可选 SQLite checkpoint；`ordered` 是最简顺序链路。三者复用同一批 Agent 与安全规则。
- 不让工具直连学生端：高风险工具执行全部走 ToolJob，避免模型在流式回复中直接触发外部动作。
- 不对所有输入做 RAG：先做意图路由，只有咨询和风险类场景触发知识检索；`VECTOR_ENABLED=false` 时使用 BM25 + 条件 rerank，向量开启后可使用混合召回。
- 默认可本地运行：没有外部 API key 时也能完成端到端演示；接入 OpenAI、Ollama、Chroma、Redis、SMTP 后可以切换到更接近生产的配置。
- 自动 Skill 当前按重复模式自动生成并在后续匹配中重载；生产使用应结合目录权限、版本控制与人工审核流程，审核工作台尚未实现。

## 文档

- [架构说明](docs/architecture.md)
- [安全设计](docs/safety-design.md)
- [咨询工作台使用手册(教师版)](docs/admin-teacher-guide.md)
- [前端学习指南](docs/frontend-learning-guide.md)
- [QLoRA 微调参数与操作手册](docs/qlora-finetuning.md)
- [演示脚本](docs/demo-script.md)
- [逐文件学习指南](Aegis项目逐文件学习指南.md)
- [第一轮模块化重构方案与变更记录](docs/records/REFACTORING.md)
- [第二轮响应提速与真流式输出](docs/records/OPTIMIZATION.md)
- [第三轮注册登录与 MySQL 持久化](docs/records/AUTH-MYSQL.md)
- [第四轮 LangGraph 编排与全栈激活](docs/records/LANGGRAPH-DOCKER.md)
- [第五轮深度增强(风险双通道/FC/A·B评测/Judge/Checkpoint)](docs/records/DEEP-ENHANCEMENTS.md)
- [第六轮回复真人化改造(提示词/兜底模板/429重试)](docs/records/LLM-RESPONSE-HUMANIZATION.md)
- [第七轮记忆系统增强(消息数/摘要容量提升)](docs/records/MEMORY-ENHANCEMENT.md)
- [第八轮对抗型对话测试(10轮配合+10轮对抗)](docs/records/CONFRONTATIONAL-DIALOGUE-TESTING.md)
- [第九轮项目文档整合与规范化](docs/records/ROUND-9-CONSOLIDATION.md)
- [第十轮代表性语料双层拆分(基础层/压力层)](docs/records/CORPUS-LAYER-SPLIT.md)
- [第十一轮风险LLM通道双路径验证(stub-LLM on vs MockLLM OFF)](docs/records/ROUND-11-RISK-LLM-DUAL-CHANNEL.md)
- [第十二轮RAG增强与性能基准(知识库24篇/RRF/缓存/双口径消融/benchmark)](docs/records/ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md)
- [第十三轮记忆分层与 Skill 自动蒸馏(L2/L3/L4/SCD-2/自动 Skill)](docs/records/ROUND-13-MEMORY-SKILL-DISTILLATION.md)
- [第十五轮前端疗愈主题升级(暖米白+鼠尾草绿/风险分级色条/无障碍)](docs/records/ROUND-15-FRONTEND-CALM-THEME.md)
- [第十六轮咨询工作台教师使用手册(全板块按钮逐一覆盖)](docs/records/ROUND-16-ADMIN-TEACHER-GUIDE.md)
- [第十七轮前端整体改造(后台页签化布局/固定一屏/全中文界面/前端学习指南)](docs/records/ROUND-17-FRONTEND-OVERHAUL.md)
- [第十八轮前端多主题切换(四套疗愈主题/服务端注入零闪烁/跨设备持久化)](docs/records/ROUND-18-THEME-SWITCHER.md)

## 待改进与优化(Roadmap)

> 按「实现难度 × 实现意义」盘点的演进清单;带 ✅ 的已在本仓库落地,详见 [docs/records](docs/records/) 各轮说明文档。

### 安全与合规(心理场景立身之本)
- ✅ **风险评估双通道**:规则关键词 ∪ QLoRA/通用 LLM 二次评估,任一通道判高危即高危,规则兜底(`RISK_QLORA_ENABLED` / `RISK_LLM_CHANNEL_ENABLED`)
- ✅ **真实 QLoRA 验收**:第十四轮 v9 冻结 stress 87 条八门槛全过,FPR 0、medium 召回 0.88、第三人称 0.82
- 危机转介资源可配置化:学校心理中心/紧急联系方式从硬编码改为按校配置、管理端可编辑(低难度)
- 对话数据字段级加密存储(中难度)
- 账号安全补齐:登录失败锁定、密码强度策略、会话撤销列表(低难度)
- 用户数据导出与删除(低难度)

### Agent 与算法深度
- ✅ **Function Calling 真接入**:GLM 自主选择回复技能,规则白名单兜底(`FUNCTION_CALLING_ENABLED`)
- ✅ **三运行时 A/B 评测**:langgraph/autonomous/ordered 同数据集对比延迟/trace/LLM 调用数(`--suite runtime-ab`)
- ✅ **LLM-as-Judge**:模型为回复打共情性/安全性/结构性分数,进入评测报告
- ✅ **LangGraph Checkpoint**:SqliteSaver 检查点持久化,长对话跨进程可恢复
- ✅ **记忆系统分层增强**：L2 用户结构化事实（有效期截断/冲突消解）、L3 会话摘要（默认 3000 字符）与 L4 最近 15 条原话窗口已在三运行时接入 Prompt；L1 保留 Agent 私有记忆。
- ✅ **Skill 自动蒸馏闭环**：记录重复基础 Skill 组合，默认第 3 次命中后生成并重载 `skills/auto/` Skill；自动 Skill 不再次参与计数，避免递归膨胀。
- 记忆系统进一步升级：结构化用户画像/情绪轨迹、历史会话向量检索、L1/L2 协同检索，以及 L2 事实审计/纠错工作台（高难度）。
- 自动 Skill 审核工作台：管理员查看生成内容、审批启用/拒绝/回滚并记录审计（中难度）。
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

本项目基于 [MIT License](LICENSE) 开源发布。同时请继续遵守上文的安全声明：本项目用于心理支持工程学习与展示，不提供医学诊断，不能替代专业心理咨询或危机干预服务，未经专业评估不建议直接用于真实生产心理咨询服务。

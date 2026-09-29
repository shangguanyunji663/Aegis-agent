<div align="center">

# Aegis Psych Agent

**面向校园心理支持场景的多 Agent 风险识别与干预协作平台**

学生侧即时情绪支持 · 管理侧可审计干预闭环 · QLoRA 隐式风险检测

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/Runtime-autonomous%20%7C%20langgraph%20%7C%20ordered-4B8BBE?style=flat-square)
![Storage](https://img.shields.io/badge/Storage-SQLite%20%7C%20MySQL%20%7C%20PostgreSQL-4479A1?style=flat-square&logo=mysql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Skills](https://img.shields.io/badge/Skills-8%20curated%20%2B%20auto--distilled-orange?style=flat-square)

[项目简介](#项目简介) · [核心亮点](#核心亮点) · [快速开始](#快速开始) · [目录结构](#目录结构) · [核心功能](#核心功能) · [配置说明](#配置说明) · [评测结果](#评测结果) · [贡献指南](#贡献指南)

</div>

---

> :warning: **安全声明（请先阅读）**
>
> 本项目用于心理支持工程学习与系统展示，**不提供医学诊断，也不能替代专业心理咨询或危机干预服务**。
> 高风险场景下，系统仅承担风险识别、辅助总结与转介建议职责，最终干预必须由具备资质的人员完成。
> 评测数据反映测试集表现，**不等同于临床有效性评估**。

---

## 目录

- [项目简介](#项目简介)
- [核心亮点](#核心亮点)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [方式一：本地运行](#方式一本机运行推荐)
  - [方式二：Docker Compose](#方式二docker-compose)
  - [访问地址与演示账号](#访问地址与演示账号)
  - [启用 QLoRA 风险模型（可选）](#启用-qlora-风险模型可选)
- [目录结构](#目录结构)
- [核心功能](#核心功能)
- [配置说明](#配置说明)
- [API 摘要](#api-摘要)
- [常用命令](#常用命令)
- [评测结果](#评测结果)
- [设计取舍](#设计取舍)
- [文档地图](#文档地图)
- [Roadmap](#roadmap)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 项目简介

`Aegis Psych Agent` 是一个校园心理支持多 Agent 平台，围绕**学生端倾诉**、**心理知识检索**、**风险识别**、**辅导员工作台**和**高风险工具执行闭环**五个环节展开。

它不是一个简单的聊天机器人，而是将「学生侧即时支持」与「管理侧可审计干预」拆分为两套独立信息架构，并通过统一的后端 Agent Runtime Harness 处理意图路由、记忆注入、RAG 检索、风险报告、trace 落库与工具计划。

设计时重点解决三个工程问题：

| 问题 | 应对 |
| :--- | :--- |
| 普通聊天被过度检索、过度工具化，无效召回损害回复质量 | 按意图路由决定是否检索，非咨询类对话不触发 RAG |
| 高风险表达缺少可审计流程，工具执行存在越权风险 | 工具调用先生成 `ToolJob`，经角色、风险等级、审批、脱敏与审计后入队 |
| 多 Agent 协作停留在顺序调用，缺少共享状态与中间产物 | 基于 append-only blackboard 实现任务发布、Agent 认领、artifact 产出与最终验收 |

**关键事实一览**

| 项 | 数值 |
| :--- | :--- |
| 内置知识库 | 24 篇 Markdown 文档 |
| 人工策展 Skill | 8 个（另有运行时自动蒸馏产物） |
| 评测金标集 | 150 条代表性样本（基础层 63 / 压力层 87）+ 77 条 RAG 问句 + 8 组多轮场景 |
| 测试覆盖 | 15 个 pytest 模块，覆盖路由 / 风险 / 记忆 / API / MCP / 三运行时 A/B |
| 零密钥启动 | 支持，`AI_PROVIDER=mock` 下无需任何外部 API Key |

---

## 核心亮点

| 模块 | 解决的问题 | 实现方式 |
| :--- | :--- | :--- |
| 双端独立界面 | 学生倾诉体验与管理员处置流程关注点不同，混在一起会导致产品边界混乱 | `/student` 提供学生对话与会话记忆，`/admin` 提供报告、个案、trace、知识库、工具队列与评测工作台 |
| 四套疗愈主题 | 心理支持需按来访者状态切换视觉语气，单一主题难以覆盖低龄与深度倾诉 | CSS 变量四主题（`warm`/`ocean`/`forest`/`playful`）+ `theme.js` 顶栏切换 + `PUT /api/auth/me/theme` 按用户持久化 + 服务端首屏注入零闪烁 |
| Agent Runtime Harness | Agent 调用、上下文注入、风险报告与工具计划散落业务代码将难以审计 | `AegisAgentHarness` 统一封装输入脱敏、运行时调用、trace 保存、消息持久化、报告生成与工具计划 |
| 自治多 Agent 协作 | 单个 Lead Agent 串行分派容易沦为「伪协作」 | 默认 `autonomous` 运行时基于 append-only blackboard 实现任务发布、Agent claim、artifact 产出、风险 override 与最终验收；可切换 LangGraph 或 ordered 运行时 |
| 分层 MemoryAgent | 心理支持需要连续性，单轮回复无法体现对用户状态变化的理解 | L1 Agent 私有记忆 + L2 跨会话结构化用户事实 + L3 会话滚动摘要 + L4 最近原话窗口；L2 以有效期截断处理状态冲突，并优先于可能过期的摘要注入 Prompt |
| Agentic RAG | 全量检索会引入噪声，陪伴类对话尤其易被知识文档带偏 | 通过 CHAT / CONSULT / RISK 意图路由决定是否检索；多路召回（BM25 + 可选向量）+ 加权/RRF 融合 + 条件 rerank + 邻块扩展 |
| 工具治理与 MCP | 高风险预警、Excel 记录、邮件通知不可由模型越权直接执行 | 工具调用先生成 `ToolJob`，经角色、风险等级、审批、脱敏与审计后进入队列；支持 internal 与 FastMCP 双后端 |
| 后台 Tool Queue | 外部工具慢、失败或限流时不应阻塞学生端流式回复 | 独立 worker 支持依赖调度、重试退避、邮件限流、dead letter、`ExcelRecord` 与 `AlertRecord` 持久化 |
| 工程 Harness | Agent 项目只看 demo 容易高估完成度 | pytest 单元/接口测试、RAG eval、综合 eval（含 LLM-as-Judge）、harness 8 套件、三运行时 A/B、本地 benchmark |
| 风险双通道 | 关键词规则召回有限，单靠模型又不可控 | 规则 ∪ QLoRA/通用 LLM 取并集，任一判高危即高危，并以规则兜底回退保证安全边界 |

---

## 系统架构

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

**数据流说明**：学生消息进入 Harness → 输入脱敏 → 意图路由 → 按意图决定是否检索 → 多 Agent 在黑板协议下协作 → 风险双通道判定 → 生成 `ToolJob` 而非直接执行 → 回复流式返回同时工具异步入队 → trace / 报告 / 审计全量落库。

---

## 快速开始

### 环境要求

| 依赖 | 版本 | 是否必需 |
| :--- | :--- | :--- |
| Python | 3.12+（Dockerfile 基准镜像 `python:3.12-slim`） | 必需 |
| pip / venv | 随 Python | 必需 |
| MySQL | 8.0 | 可选，SQLite 为零配置默认 |
| Redis | 最新稳定版 | 可选，限流锁能力预留 |
| Chroma | 随依赖安装 | 可选，`VECTOR_ENABLED=true` 时使用 |
| Node.js | 任意版本（仅用于前端脚本语法自检） | 可选 |

> 默认使用 SQLite，**零外部依赖即可完成端到端演示**。

### 方式一：本机运行（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/shangguanyunji663/aegis-psych-agent.git
cd aegis-psych-agent

# 2. 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量并初始化数据库
cp .env.example .env
python -m app.init_db

# 5. 启动服务
uvicorn app.main:app --host 127.0.0.1 --port 8091
```

**切换到 MySQL**（本机或 Compose 提供的 MySQL 8.0），在 `.env` 中设置：

```bash
DATABASE_URL=mysql+pymysql://root:你的密码@localhost:3306/aegis?charset=utf8mb4
```

首次启动自动建库建表（`utf8mb4`）；已有 SQLite 数据可通过 `python -m scripts.migrate_sqlite_to_mysql` 一键迁移，原文件保留为备份。

### 方式二：Docker Compose

```bash
docker compose up --build
```

Compose 会启动应用、MySQL 8.0、Redis 与 Chroma。默认本地模式仍使用 SQLite；如需切换数据库或向量后端，在 `.env` 中调整 `DATABASE_URL`、`VECTOR_ENABLED`、`VECTOR_BACKEND` 等配置。

> 注意：依赖中包含 PostgreSQL 驱动，但当前 Compose 拓扑**不启动** PostgreSQL 服务。

### 访问地址与演示账号

| 入口 | 地址 |
| :--- | :--- |
| 首页 | <http://127.0.0.1:8091> |
| 学生端 | <http://127.0.0.1:8091/student> |
| 管理端 | <http://127.0.0.1:8091/admin> |

| 角色 | 用户名 | 密码 | 备注 |
| :--- | :--- | :--- | :--- |
| 学生 | `student` | `student123!` | 学生可自由注册 |
| 管理员 | `admin` | `admin123!` | 初始账号，生产环境必须修改 |
| 教师 | 自由注册 + 邀请码 | 自定义 | 默认邀请码 `aegis-teacher`，由 `AUTH_TEACHER_INVITE_CODE` 配置，注册后进入咨询工作台 |

> :camera: **界面截图待补充**：欢迎通过 PR 提供 `/student`、`/admin` 页面截图至 `docs/assets/`，并同步更新本节。

### 启用 QLoRA 风险模型（可选）

普通启动默认**不加载训练模型**（`RISK_QLORA_ENABLED=false`），RiskGuardian 保持现有规则 / 通用 LLM 行为。

<details>
<summary><b>展开：QLoRA 推理服务接入步骤</b></summary>

**1. 独立启动推理服务**（本例为 Windows，其余环境替换为自己的训练根目录）

```bash
# Windows 示例
set AEGIS_TRAINING_ROOT=D:\AegisTraining
set AEGIS_QLORA_MODEL_DIR=%AEGIS_TRAINING_ROOT%\exports\aegis-risk-qwen3.5-2b-v9-merged

%AEGIS_TRAINING_ROOT%\envs\qlora-qwen35\python.exe ^
  %AEGIS_TRAINING_ROOT%\training\scripts\serve_risk_qlora.py ^
  --model-dir "%AEGIS_QLORA_MODEL_DIR%"
```

服务默认监听 `http://127.0.0.1:8301`，可先做连通性检查：

```bash
curl http://127.0.0.1:8301/health
```

**2. 安全约束（重要）**

应用侧的 QLoRA HTTP 集成**只接受受保护的公网 HTTPS endpoint**，明确拒绝 localhost、环回、私有网段与保留地址。本地地址仅用于服务自身的 smoke test，**不可**填入应用 `.env`。

正确做法是先将推理服务部署到受保护的公网 HTTPS 地址，再配置：

```ini
RISK_QLORA_ENABLED=true
RISK_QLORA_URL=https://your-approved-qlora.example.com
RISK_QLORA_TIMEOUT_SECONDS=8
```

**3. 故障降级**

服务不可达、超时或返回非法 JSON 时，RiskGuardian 自动回退规则通道，保证安全边界不降低。其余 Agent 仍使用各自原有模型通道。训练文件与模型权重存放于外部 `AEGIS_TRAINING_ROOT`，**不写入本项目仓库**。

> 生产部署建议使用 bf16（与验收口径一致）；显存不足时可加 `--load-4bit`，但需重新验证边界样本结果。

**QLoRA 训练目标**：并非训练通用聊天能力，而是将 Qwen3.5-2B-Base 微调为 RiskGuardian 的 `low / medium / high` JSON 风险评估器。基座采用 4-bit NF4 量化并冻结，LoRA `r=8/alpha=16` 仅训练约 840 万参数（占总参数约 18.9 亿的 0.445%）。训练样本只覆盖风险判定、理由长度与主体/意图裁决，**不改变** Counselor、RAG、工具治理或审批链路。

> 后续生产化改进路线（异步/并发、HTTP/SSE/WebSocket、部署、MCP/JSON-RPC/A2A、权限、流式工具调用、错误恢复、KV Cache/vLLM/SGLang、Reranker、GraphRAG）见 [`docs/QLORA-SSE-PRODUCTION-IMPROVEMENTS.md`](docs/QLORA-SSE-PRODUCTION-IMPROVEMENTS.md)。

</details>

---

## 目录结构

```text
.
├── app/                         # 后端主包
│   ├── main.py                  # 应用入口：create_app 装配 + 路由注册
│   ├── config.py                # pydantic-settings 全局配置
│   ├── models.py                # 领域模型：Intent / RiskLevel / ChatResponse 等
│   ├── entities.py              # SQLAlchemy ORM 实体
│   ├── database.py              # 引擎 / 会话工厂 / 建表 / 迁移 / 就绪检查
│   ├── init_db.py               # 数据库初始化与默认账号引导
│   ├── assessment.py            # 规则式风险评估（高危/中危关键词单一来源）
│   ├── skills.py                # SkillRegistry：注册式 Skill、标准 Skill 与自动蒸馏
│   ├── core/                    # 横切原语：auth | privacy | runtime_services | network(SSRF 防护) | utils
│   ├── llm/                     # 模型后端：Mock / OpenAI / Ollama / RiskQloraClient + prompts
│   ├── agents/                  # 智能体层：classic | harness | model_profiles | orchestrator | runtime | skill_selection | langgraph_runtime
│   ├── autonomous/              # 自治协作：events | registry | board | coordinator | agents | runtime
│   ├── rag/                     # 检索与记忆：text | scoring | chunking | facts(L2) | memory(L3) | vector_store | reranker(CE 精排)
│   ├── repository/              # 持久化仓储：会话、L2 用户事实、知识库、报告与工具任务
│   ├── tools/                   # 工具治理：contracts（契约）| gateway（网关）
│   ├── services/                # 业务服务：report_case | tool_executor | tool_queue | tool_records | tool_governance
│   ├── api/                     # HTTP 路由：schemas | deps | middleware | pages | system | auth_routes | chat | admin
│   ├── evaluation/              # 评测：runner | rag | datasets | report_html | runtime_ab | judge + harness/
│   └── mcp/                     # MCP 边界：server（FastMCP 服务）| client（stdio 客户端）
├── knowledge/                   # 内置心理支持知识库（当前 24 篇 .md）
├── eval/                        # 评测 CLI 与 fixtures（路由 / 风险 / 安全 / 多轮 / 检索 / RAG 数据集）
├── skills/                      # 人工策展 Skill 规范；运行时可在 skills/auto/ 生成 auto Skill
├── static/                      # 前端：index | login | student | admin 页面 + styles.css + theme.js
├── tests/                       # pytest 测试（16 个模块）
├── scripts/                     # 启动/联调/诊断：start-local | start-compose | smoke_chat | probe_glm
│                                #                migrate_sqlite_to_mysql | eval_risk_dual_path | run_benchmark | analyze_layers
│                                #                eval_minilm_ablation_tmp | eval_ce_tmp（第十九轮 RAG 对照评测）
├── docs/                        # 架构、安全、演示、教师手册与前端学习文档
│   └── records/                 # 迭代记录（第 1 ~ 19 轮）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 核心功能

### 学生端

- **账号体系**：学生自由注册；教师凭邀请码注册后进入咨询工作台。
- **会话管理**：登录登出、会话创建与新会话切换；重命名/删除已提供 API（`PATCH` / `DELETE /api/sessions/{id}`），**界面暂无对应按钮**。
- **对话助手「小暖」**：SSE 真流式输出，消息头像与入场动画、欢迎屏话题 chips；顶栏时段问候与服务状态圆点（60 秒自动刷新）。另有 `POST /api/chat` 非流式兼容路径。
- **实用卡片**：「心情速选」2×2 图标卡一键填入表达、「需要立即帮助」（心理援助热线 12356 / 120）与「60 秒放松练习」。
- **四套疗愈主题**：暖意疗愈（默认）/ 深海冥想 / 晨雾森林 / 童趣治愈贴贴，顶栏切换器即时换色，按用户持久化并跨设备同步；服务端首屏注入 `html[data-theme]`，无切换闪烁。
- **三类回复路径**：低风险陪伴、心理咨询建议、高风险安全回应。低风险对话在生成时逐字直播，中/高风险回复经安全复核通过后再输出。
- **分层记忆注入**：L2 跨会话当前有效事实 + L3 会话滚动摘要 + L4 最近原话窗口共同注入；当前有效事实优先于可能过期的摘要，避免旧状态干扰当前回应。
- **信息隔离**：高风险内容不向学生暴露内部报告字段，避免二次伤害与信息泄露。

### 管理端

- **三列页签工作台**：桌面端固定一屏、界面全中文。左列「个案 | 知识库 | 协作状态」、中列「风险报告 | 对话回放」、右列「详情检查器 + 工作台」。操作详见《[咨询工作台使用手册（教师版）](docs/admin-teacher-guide.md)》。
- **风险处置**：报告列表、状态流转与报告 trace 查看；个案创建、辅导员确认、备注追加与状态更新。
- **知识库运维**：检索、内容上传（`.md`/`.txt`/`.pdf`）、重建索引与备份；向量索引重建另提供 `/api/admin/knowledge/rebuild-vector`。
- **工具与审计**：ToolJob 与执行记录（`ExcelRecord`/`AlertRecord`）界面可查；「审计」页签查看操作审计；`ToolAudit` 与 `DeadLetter` 提供独立 API（`tool-audits` / `dead-letters`）。
- **运行态观测**：Runtime 协作状态（编排引擎 / 调度 / 存储 / 队列与智能体名单）可视，模型状态在顶栏胶囊展示；Agent 模型配置与私有记忆提供 `agent-models` / `agent-memories` 查询接口。
- **评测入口**：管理端可一键触发综合评测；Harness 验证另由命令行 `python -m app.evaluation.harness.runner` 执行。

### Agent 协作

| Agent | 职责 |
| :--- | :--- |
| `MemoryAgent` | 加载 L1 Agent 私有记忆、L2 当前有效用户事实、L3 会话摘要与 L4 最近消息；回复后更新 L3，并以确定性规则抽取可变化用户状态写入 L2 |
| `LeadAgent` / `SupervisorAgent` | 识别意图并决定协作路径 |
| `RiskGuardianAgent` | 风险分级、安全 override、高风险报告生成 |
| `KnowledgeAgent` | 按意图与风险等级检索知识库，注入标准 Skill；重复的基础 Skill 组合达到默认 3 次后可自动蒸馏为 `skills/auto/` 下的新 Skill |
| `CounselorAgent` | 生成咨询类支持计划与可追踪回复 |
| `CompanionAgent` | 处理低风险陪伴与情绪支持对话 |

> Skill 自动蒸馏当前会直接重载并参与后续匹配，**人工审核工作台尚未实现**（见 [Roadmap](#roadmap)）。

### 工具与治理

- **FastMCP Server**：暴露 case create、case ack、case note add、alert、ledger、email、handoff、resource lookup 等工具。
- **MCP Client**：支持在平台内切换到 MCP 后端执行工具。
- **工具契约**：限制角色、风险等级、审批要求、脱敏字段与最大重试次数。
- **后台 Worker**：支持批量领取、依赖调度、失败重试、限流与 dead letter。
- **真实输出**：Excel 写入、Alert 独立记录、邮件发送或日志投递、handoff Markdown 文件。

---

## 配置说明

配置基于 `pydantic-settings`，优先级为：**环境变量 > `.env` > `.env.example` 建议值 > `Settings` 代码默认值**。
下表「默认」均指 `Settings` 代码默认值。

| 变量 | 说明与默认值 |
| :--- | :--- |
| `AI_PROVIDER` | `mock`（默认）/ `openai` / `ollama`；mock 支持无密钥本地演示 |
| `LLM_THINKING_ENABLED` | 是否启用深度思考型模型的内部推理；默认 `false`，接入 GLM-4.x 时通常保持关闭以降低延迟 |
| `DATABASE_URL` | 默认 `sqlite:///data/aegis.sqlite`；可改为 MySQL 或自行部署的 PostgreSQL |
| `VECTOR_ENABLED` | 是否启用向量召回；默认 `false`。关闭后仍保留 BM25 + 条件 rerank 路径 |
| `EMBEDDING_PROVIDER` | `openai`（默认）或 `local`（Chroma 本地嵌入）；`.env.example` 用 `local` 作为无密钥演示示例 |
| `VECTOR_BACKEND` | 向量后端，默认 `chroma`；仅在 `VECTOR_ENABLED=true` 时参与检索 |
| `KNOWLEDGE_FUSION_MODE` | `weighted`（默认，线性加权）或 `rrf`（倒数排名融合） |
| `KNOWLEDGE_RERANK_ENGINE` | 重排引擎：`lexical`（默认，纯 Python 词法公式，全库重打分）或 `cross_encoder`（ONNX 模型精排，两段式 top-N，见第十九轮） |
| `KNOWLEDGE_RERANK_TOP_N` | Cross-Encoder 精排候选数；默认 `16`（仅 `cross_encoder` 引擎使用） |
| `RERANKER_MODEL_DIR` | Cross-Encoder ONNX 模型目录；默认 `data/models/bge-reranker-base-onnx`（含 `model_quantized.onnx` 与 `tokenizer.json`，模型下载见第十九轮记录） |
| `KNOWLEDGE_CACHE_ENABLED` | 进程内 LRU 精确查询缓存开关；默认 `false`，可配 TTL 与最大条目数。Redis 写入为预留能力，检索读取仍以进程内缓存为准 |
| `RISK_LLM_CHANNEL_ENABLED` | 通用 LLM 风险通道开关；默认 `true`。`RISK_QLORA_ENABLED=true` 时由 QLoRA 通道接管 |
| `RISK_QLORA_ENABLED` | QLoRA 风险增强开关；默认 `false` |
| `RISK_QLORA_URL` | QLoRA 服务地址；默认占位 `https://qlora-endpoint.example.invalid`，应用集成拒绝 localhost / 环回 / 私有与保留地址 |
| `RISK_QLORA_TIMEOUT_SECONDS` | QLoRA 请求超时；默认 `8` 秒，超时回退规则 |
| `FUNCTION_CALLING_ENABLED` | 技能选择：模型在规则白名单内自主挑选；默认 `true`，失败回退规则白名单 |
| `SKILL_DISTILL_ENABLED` | 是否记录基础 Skill 重复组合并触发自动蒸馏；默认 `true` |
| `SKILL_DISTILL_MIN_REPEAT` | 同一 `intent \| risk \| 基础 Skill 集合` 触发蒸馏的次数；默认 `3` |
| `SKILL_DISTILL_DIR` | 自动 Skill 输出目录；默认 `skills/auto`。达到阈值后直接重载，无人工审核门禁 |
| `MEMORY_RECENT_MESSAGES` | L4 最近原始消息窗口条数；默认 `15` |
| `MEMORY_SUMMARY_MAX_CHARS` | L3 会话滚动摘要字符上限；默认 `3000` |
| `AGENT_RUNTIME` | `autonomous`（默认）/ `langgraph` / `ordered` |
| `LANGGRAPH_CHECKPOINT_ENABLED` / `LANGGRAPH_CHECKPOINT_PATH` | LangGraph SqliteSaver 检查点开关与路径；默认 `true` / `data/langgraph-checkpoints.sqlite` |
| `TOOL_BACKEND` / `MCP_ENABLED` | `internal`（默认）或 `mcp` 工具后端，以及 MCP 路径开关 |
| `TOOL_QUEUE_*` | 后台工具 worker 的轮询、批量、线程与重试配置 |
| `SMTP_*` / `ALERT_EMAIL_*` | 邮件预警发送与投递配置 |
| `AUTH_DEFAULT_*` / `AUTH_TEACHER_INVITE_CODE` | 默认学生/管理员账号与教师邀请码；邀请码默认 `aegis-teacher`，**生产必须修改** |

---

## API 摘要

| 类型 | 接口 |
| :--- | :--- |
| 系统状态 | `GET /api/health`、`GET /api/readiness`、`GET /api/agent/status`（需登录）、`GET /api/skills` |
| 认证 | `POST /api/auth/register`、`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`（含 `theme`）、`PUT /api/auth/me/theme` |
| 学生会话 | `GET /api/sessions`、`POST /api/sessions`、`GET /api/sessions/{id}`、`PATCH /api/sessions/{id}`、`DELETE /api/sessions/{id}` |
| 聊天 | `POST /api/chat`、`POST /api/chat/stream` |
| 管理端报告 | `GET /api/admin/reports`、`PATCH /api/admin/reports/{report_id}`、`GET /api/admin/traces` |
| 个案 | `GET /api/admin/cases`、`POST /api/admin/cases/{case_id}/notes`、`PATCH /api/admin/cases/{case_id}` |
| 工具队列 | `GET /api/admin/tool-jobs`、`POST /api/admin/tool-jobs/run`、`POST /api/admin/tool-jobs/{job_id}/retry`、`GET /api/admin/tool-worker/status`、`POST /api/admin/tool-worker/run-once` |
| 工具审计 | `GET /api/admin/tool-audits`、`GET /api/admin/excel-records`、`GET /api/admin/alert-records`、`GET /api/admin/dead-letters`、`GET /api/admin/audit-logs` |
| 知识库 | `GET /api/admin/knowledge/status`、`GET /api/admin/knowledge/search`、`POST /api/admin/knowledge`、`POST /api/admin/knowledge/upload`、`POST /api/admin/knowledge/rebuild`、`POST /api/admin/knowledge/rebuild-vector`、`POST /api/admin/knowledge/backup` |
| 评测 | `GET /api/admin/eval-results`、`POST /api/admin/eval-results/run` |

---

## 常用命令

```bash
# 初始化数据库
python -m app.init_db

# 后端测试（只收集 tests/，scripts/ 下的联调脚本不在 pytest 范围）
python -m pytest tests -q

# 前端脚本语法检查
node --check static/login.js static/student.js static/admin.js

# 综合评测
python -m eval.run_eval

# RAG 独立评测（双口径 + 消融）
python -m app.evaluation.rag

# 本地性能 benchmark（并发 / 延迟 / 吞吐 / 缓存 / ToolJob）
python -m scripts.run_benchmark

# 工程 Harness 验证
python -m app.evaluation.harness.runner --suite all --output data/harness/latest.json

# 查看 MCP 能力
python -m app.mcp.server --list
```

---

## 评测结果

评测体系基于**人工构造、人工标注且贴近校园心理求助语料的代表性金标集**。我们不筛选样本、不为追求满分而人为凑 100%，允许并保留非满分的真实通过率，用以暴露真实代码与能力边界。

> :warning: 评测指标反映测试集表现，**非真实用户流量验证，不等同于临床有效性评估**。评测产物是可再生快照，不代表后续提交必然得到相同数值。

### 数据来源与落盘日期

| 数据集 | 规模与来源 | 落盘产物 / 日期 |
| :--- | :--- | :--- |
| 路由 / 风险 / 规模化基准 | `eval/fixtures/representative_corpus.json`，150 条人工构造金标样本，含 `layer`（base / stress）与 `source` 双层拆分标记 | `data/eval/latest.json`，2026-08-19 |
| RAG 检索 | `eval/fixtures/rag_queries.json`，77 条自然语言问句，基于 24 篇知识文档 | `data/eval/rag-eval-report.json`，2026-08-20 |
| RAG 语义重排与真向量实测（第十九轮） | 同 77 条问句；Chroma+MiniLM 嵌入与 bge-reranker-base Cross-Encoder 逐条对照 | `data/eval/minilm-eval-report.json` / `data/eval/ce-eval-report.json`，2026-09-29 |
| 多轮回归 | `eval/fixtures/multi_turn_corpus.json`，8 组多轮场景 | `data/eval/latest.json`，2026-08-19 |
| 三运行时 A/B | 10 条代表性消息 | `data/harness/runtime-ab-report.md`，2026-08-20 |
| 性能基准 | `scripts/run_benchmark.py`，MockLLM + `VECTOR_ENABLED=false` | `data/eval/benchmark.json`，2026-08-20 |

### 主指标总览

| 验证项 | 覆盖内容 | 已落盘结果与适用边界 |
| :--- | :--- | :--- |
| 单元与接口测试 | API、认证、风险双通道、Function Calling、Agent runtime、LangGraph checkpoint、MCP tools、评测 runner | **历史记录**：2026-08-21 记录 `python -m pytest tests/ -q` 为 **71 passed, 8 warnings**。测试数量与结果应以当前环境重跑为准 |
| 150 条规模化基准（双层拆分） | 基础层 63 条 + 压力层 87 条，runner 分别输出两套独立指标 | **2026-08-19**：整体联合准确率 **0.63**、意图 **0.63**、风险 **0.81**、高风险召回 **0.60**、误报率 **0.00**；基础层准确率 **0.97** / 风险 **1.00** / 高召回 **1.00**；压力层准确率 **0.39** / 风险 **0.67** / 高召回 **0.52** |
| 风险双通道 + QLoRA 微调 | 历史规则/stub/GLM sanity 与当前真实 v9 QLoRA 冻结 stress 87 条验收 | **当前以 v9 QLoRA 为准**：`RISK_QLORA_ENABLED=true` 时八门槛全过 |
| 多轮回归 | 8 组多轮场景（含升级到中/高风险、第三人称转自身） | **2026-08-19**：最终关键内容命中率 **0.875**（7/8） |
| RAG 检索 | 77 条问句 Top-4；专项消融使用 local-hash 向量配置 | **2026-08-20**：宽松 HitRate@4 **0.935**、严格来源命中 **0.883**、Recall@4 **0.935**、Precision@4 **0.351**、MRR **0.820**、NDCG@4 **0.832** |
| RAG 语义重排（第十九轮实测） | 同 77 条问句：BM25+Cross-Encoder 精排、Chroma+MiniLM 真向量混合 | **2026-09-29**：BM25+Cross-Encoder **0.948**（73/77，历史最优）；真 MiniLM 混合 **0.857**（被英文嵌入模型拖累，暂不启用，需换中文嵌入模型重测）；CE 延迟 ~850ms/条（CPU int8） |
| 三运行时 A/B | langgraph / autonomous / ordered 对比延迟、trace 步数、LLM 调用数与判定一致性 | **2026-08-20**：三运行时判定完全一致；意图准确率 **0.8**、风险准确率 **0.9**，含 1 条规则引擎漏判的隐式高危边界样本 |
| Harness 验证 | Risk Safety、Agent Routing、Standard Skills、RAG、API、Tool Queue、Runtime A/B 等链路（验证工程行为，不强制满分） | **历史快照**：`data/harness/current-verification.json` 为 **8/8 通过**；`latest.json` 是旧的 7-suite 存档，建议重跑后覆盖 |
| 本地性能 benchmark | MockLLM 确定性环境，20 条代表性消息 × 并发 [1,4,8] | **2026-08-20**：并发 1 → avg 66ms / P95 71ms / 15.1 req/s；并发 4 → avg 316ms / P95 729ms / 12.3 req/s；并发 8 → avg 517ms / P95 1260ms / 13.5 req/s。缓存命中 <0.01ms；ToolJob 5/5 成功、0 死信 |

<details>
<summary><b>展开：双层拆分的真实含义（务必阅读后再引用指标）</b></summary>

**基础层（贴近真实流量，63 条）：准确率 0.97、风险 1.00、高召回 1.00**
覆盖日常闲聊、典型咨询、显式高危等「真实会发生的流量」，规则引擎表现稳健 —— 这是系统的 **可靠性证据**。

**压力层（边界探测，87 条）：准确率 0.39、风险 0.67、高召回 0.52**
刻意堆满隐喻式自杀意念（「想消失」「不再面对明天」）、无关键词咨询、第三人称干扰等边界样本，用于**主动暴露**规则通道的能力缺口 —— 这是系统的 **边界暴露证据**，零删改、不凑分。

**整体准确率 0.63、风险 0.81、高召回 0.60**：以上均为基础层与压力层的**加权平均**，单独引用会丢失双层拆分的工程价值。

- **高风险召回 0.60**：基础层显式与部分隐式高危全命中，压力层的隐喻式自杀意念无关键词可命中而拉低整体，需依赖 LLM 风险通道。这是关键词路线的固有上限，非调参可解。
- **路由准确率 0.63**：许多真实咨询诉求无明显关键词（如「我和男朋友吵架了，心里不舒服」），纯关键词兜底路由必然漏判。已扩充通用中文求助表达词表，彻底解决需 LLM 意图通道。
- **误报率 0.00**：第三人称提及高危词（「新闻里有人轻生」「直播自杀」）已通过说话人消歧修复，不再误判为自身高危。

**简历 / 面试引用建议**

- :white_check_mark: 推荐：「v9 QLoRA 风险模型冻结 stress 87 条八门槛全过，FPR 0、隐喻新增 +6、medium 召回 0.88、P95 1.37s」，并说明该结果并非临床有效性评估
- :white_check_mark: 可补充：「真实原始 `qwen3.5:2b` 通道对照 FPR 14.5%，QLoRA 候选降为 0；JSON 有效率 93.1% → 100%」
- :warning: 历史双层规则 / Stub 指标（0.63 / 0.81 等）只作为能力边界留痕，**不作为当前生产模型成绩**
- :bulb: 训练谱系、数据审计与提示词契约变更见 `AEGIS_TRAINING_ROOT/reports/TRAINING-HISTORY-INDEX.md`

</details>

<details>
<summary><b>展开：风险模型横向对比与双通道机制详解</b></summary>

**训练基线说明**：QLoRA 训练目标为风险判别而非通用对话。基座 Qwen3.5-2B-Base 采用 4-bit NF4 量化并冻结，LoRA `r=8/alpha=16` 训练约 840 万参数（占总参数约 18.9 亿的 0.445%）。

**风险模型横向对比（冻结 stress 87 条；各版 QLoRA 使用各自训练时提示词，当前 v9 使用提示词 v2）**

| 通道 / 版本 | 训练规模 | Accuracy | Macro-F1 | HIGH Recall | Medium Recall | 第三人称准确率 | non-high→high FPR | JSON 有效率 | P95 | 验收 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 规则 baseline | 0 | 0.667 | 0.480 | 0.52 | 0.00 | 1.00 | 0 | — | — | — |
| 原始 `qwen3.5:2b` | 0 | 0.644 | 0.609 | 0.68 | 0.29 | 0.82 | 14.52% | 93.10% | 0.86s | — |
| 第一版（旧 v1）QLoRA | 720+120 | 0.770 | 0.743 | 0.64 | 0.59 | 1.00 | 0 | 100% | 0.95s | :x: 隐喻 +3 |
| 第二版（旧 v3）QLoRA | 840+140 | 0.770 | 0.751 | 0.84 | 0.71 | 1.00 | 4.84% | 100% | 0.88s | :x: FPR |
| 第三版（旧 v4）QLoRA | 1703+198 | 0.667 | 0.606 | 0.80 | 0.24 | 0.27 | 3.23% | 100% | 1.20s | :x: FPR |
| 第四版（旧 v5）QLoRA | 1703+200 | 0.736 | 0.674 | 0.84 | 0.29 | 0.55 | 0 | 100% | 0.93s | :white_check_mark: |
| 第五版（旧 v7）QLoRA | 1703+200 | 0.759 | 0.746 | 0.80 | 0.77 | 0.82 | 3.23% | 100% | 1.04s | :x: FPR |
| 第六版（旧 v8）QLoRA | 2864+200 | 0.782 | 0.760 | 0.80 | 0.71 | 0.91 | 3.23% | 100% | 0.96s | :x: FPR |
| **第七版（旧 v9）QLoRA** | **2867+200** | **0.782** | **0.777** | **0.76** | **0.88** | **0.82** | **0** | **100%** | **1.37s** | **:white_check_mark: 8/8** |

> 注：规则 / 原始模型的 medium 与 JSON 指标来自对应报告的原始通道；各版 QLoRA 的 `rules ∪ QLoRA` 结果用于生产形态对比。87 条压力集用于安全验收，不能替代临床有效性评估；完整原始 JSON 报告见 `AEGIS_TRAINING_ROOT/reports/`。

**风险双通道机制**

判定由**规则通道 + 可选模型通道**组成，`RISK_LLM_CHANNEL_ENABLED` 控制通用 LLM 通道，`RISK_QLORA_ENABLED` 控制已验收的 QLoRA 通道。

*规则通道（`app/assessment.py` 的 `assess_message()`，不可关闭）*

- 纯关键词匹配，零 LLM 调用、零外部依赖、可审计
- `HIGH_TERMS`（自杀 / 轻生 / 一了百了等 18 词）命中 → HIGH；`MEDIUM_TERMS`（自残 / 崩溃 / 绝望等 7 词）命中 → MEDIUM
- 第三人称消歧：高危词出现在「新闻 / 电影 / 朋友」等语境 → 降级 LOW
- **固有上限**：只能识别词面，隐喻式表达常漏判；补强由 QLoRA 通道承担

*LLM 通道（`app/llm/client.py` + `app/agents/classic.py`，可开关）*

- 用 `RISK_ASSESS_SYSTEM_PROMPT`（提示词契约 v2）使模型理解隐喻
- `RISK_QLORA_ENABLED=true` 时切换为 QLoRA 模型（`aegis-risk-qwen3.5-2b-v9`），由隔离 Transformers 推理服务提供；不启用时行为完全不变
- 并集融合：`order[llm_level] > order[risk_level]` 时升级（只升不降，安全优先）
- 兜底：LLM 失败 / 超时 / 429 返回 None → 回退纯规则结果

*开关语义*

- `RISK_QLORA_ENABLED=false`：行为由 `RISK_LLM_CHANNEL_ENABLED` 决定；后者为 false 时只跑规则
- `RISK_QLORA_ENABLED=true`：自动使用 v9 QLoRA 模型，规则与 QLoRA 取并集，`RISK_LLM_CHANNEL_ENABLED` 被强制视为 true

*历史评测中的客户端角色*

- `MockLLMClient`：用于规则 baseline，`assess_risk()` 返回 None
- `MetaphorAwareStubClient`：历史测试替身，**不是生产模型，也不是 v9 QLoRA 的成绩**
- v9 QLoRA：当前生产候选，真实 Transformers 推理服务

*真实 GLM sanity check*：GLM-4.7-flash 对压力层全部 **25 条**隐喻式样本做扩展探针（2026-08-20，`data/eval/glm_probe_25.json`）。受免费档限流影响 14 条命中 429 / 超时回退 none；**11 条非 fallback 判断中 10 条判 high、1 条判 medium**，显示真实模型 best-effort 表现接近但不超过 QLoRA 上界。

**训练隔离约定**：训练脚本、数据、adapter、merged 模型、GGUF 与报告全部位于 `AEGIS_TRAINING_ROOT` 指向的独立训练仓库，**不进入本项目仓库**。本项目只保留 QLoRA 服务接入配置。

</details>

---

## 设计取舍

| 取舍 | 理由 |
| :--- | :--- |
| 三档运行时可切换（`AGENT_RUNTIME`） | `autonomous` 为代码默认，使用事件驱动黑板、任务认领与安全验收；`langgraph` 使用声明式 StateGraph 与可选 SQLite checkpoint；`ordered` 为最简顺序链路。三者复用同一批 Agent 与安全规则 |
| 不让工具直连学生端 | 高风险工具执行全部走 ToolJob，避免模型在流式回复中直接触发外部动作 |
| 不对所有输入做 RAG | 先做意图路由，仅咨询与风险类场景触发检索；`VECTOR_ENABLED=false` 时使用 BM25 + 条件 rerank |
| 默认可本地运行 | 无外部 API key 也能完成端到端演示；接入 OpenAI、Ollama、Chroma、Redis、SMTP 后可切换至接近生产的配置 |
| 自动 Skill 直接重载 | 当前按重复模式自动生成并参与后续匹配。生产使用应结合目录权限、版本控制与人工审核流程，审核工作台尚未实现 |

---

## 文档地图

**核心文档**

- [架构说明](docs/architecture.md)
- [安全设计](docs/safety-design.md)
- [咨询工作台使用手册（教师版）](docs/admin-teacher-guide.md)
- [前端学习指南](docs/frontend-learning-guide.md)
- [QLoRA 微调参数与操作手册](docs/qlora-finetuning.md)
- [QLoRA 生产化改进路线](docs/QLORA-SSE-PRODUCTION-IMPROVEMENTS.md)
- [演示脚本](docs/demo-script.md)
- [逐文件学习指南](Aegis项目逐文件学习指南.md)

<details>
<summary><b>展开：迭代记录（第 1 ~ 19 轮）</b></summary>

| 轮次 | 主题 | 文档 |
| :--- | :--- | :--- |
| 第一轮 | 模块化重构方案与变更记录 | [REFACTORING.md](docs/records/REFACTORING.md) |
| 第二轮 | 响应提速与真流式输出 | [OPTIMIZATION.md](docs/records/OPTIMIZATION.md) |
| 第三轮 | 注册登录与 MySQL 持久化 | [AUTH-MYSQL.md](docs/records/AUTH-MYSQL.md) |
| 第四轮 | LangGraph 编排与全栈激活 | [LANGGRAPH-DOCKER.md](docs/records/LANGGRAPH-DOCKER.md) |
| 第五轮 | 深度增强（风险双通道 / FC / A·B 评测 / Judge / Checkpoint） | [DEEP-ENHANCEMENTS.md](docs/records/DEEP-ENHANCEMENTS.md) |
| 第六轮 | 回复真人化改造（提示词 / 兜底模板 / 429 重试） | [LLM-RESPONSE-HUMANIZATION.md](docs/records/LLM-RESPONSE-HUMANIZATION.md) |
| 第七轮 | 记忆系统增强（消息数 / 摘要容量提升） | [MEMORY-ENHANCEMENT.md](docs/records/MEMORY-ENHANCEMENT.md) |
| 第八轮 | 对抗型对话测试（10 轮配合 + 10 轮对抗） | [CONFRONTATIONAL-DIALOGUE-TESTING.md](docs/records/CONFRONTATIONAL-DIALOGUE-TESTING.md) |
| 第九轮 | 项目文档整合与规范化 | [ROUND-9-CONSOLIDATION.md](docs/records/ROUND-9-CONSOLIDATION.md) |
| 第十轮 | 代表性语料双层拆分（基础层 / 压力层） | [CORPUS-LAYER-SPLIT.md](docs/records/CORPUS-LAYER-SPLIT.md) |
| 第十一轮 | 风险 LLM 通道双路径验证 | [ROUND-11-RISK-LLM-DUAL-CHANNEL.md](docs/records/ROUND-11-RISK-LLM-DUAL-CHANNEL.md) |
| 第十二轮 | RAG 增强与性能基准 | [ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md](docs/records/ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md) |
| 第十三轮 | 记忆分层与 Skill 自动蒸馏 | [ROUND-13-MEMORY-SKILL-DISTILLATION.md](docs/records/ROUND-13-MEMORY-SKILL-DISTILLATION.md) |
| 第十五轮 | 前端疗愈主题升级 | [ROUND-15-FRONTEND-CALM-THEME.md](docs/records/ROUND-15-FRONTEND-CALM-THEME.md) |
| 第十六轮 | 咨询工作台教师使用手册 | [ROUND-16-ADMIN-TEACHER-GUIDE.md](docs/records/ROUND-16-ADMIN-TEACHER-GUIDE.md) |
| 第十七轮 | 前端整体改造（页签化 / 固定一屏 / 全中文） | [ROUND-17-FRONTEND-OVERHAUL.md](docs/records/ROUND-17-FRONTEND-OVERHAUL.md) |
| 第十八轮 | 前端多主题切换与零闪烁注入 | [ROUND-18-THEME-SWITCHER.md](docs/records/ROUND-18-THEME-SWITCHER.md) |
| 第十九轮 | RAG 语义重排引擎（Cross-Encoder）与真 MiniLM 实测 | [ROUND-19-RAG-SEMANTIC-RERANK.md](docs/records/ROUND-19-RAG-SEMANTIC-RERANK.md) |

</details>

---

## Roadmap

按「实现难度 × 实现意义」整理的演进清单。带 :white_check_mark: 的已在本仓库落地。

### 安全与合规

- :white_check_mark: **风险评估双通道**：规则关键词 ∪ QLoRA / 通用 LLM 二次评估，任一判高危即高危，规则兜底
- :white_check_mark: **真实 QLoRA 验收**：v9 冻结 stress 87 条八门槛全过，FPR 0、medium 召回 0.88、第三人称 0.82
- 危机转介资源可配置化：学校心理中心 / 紧急联系方式从硬编码改为按校配置、管理端可编辑（低难度）
- 对话数据字段级加密存储（中难度）
- 账号安全补齐：登录失败锁定、密码强度策略、会话撤销列表（低难度）
- 用户数据导出与删除（低难度）

### Agent 与算法深度

- :white_check_mark: **Function Calling 真接入**：GLM 自主选择回复技能，规则白名单兜底
- :white_check_mark: **三运行时 A/B 评测**：langgraph / autonomous / ordered 同数据集对比延迟 / trace / LLM 调用数
- :white_check_mark: **LLM-as-Judge**：模型为回复打共情性 / 安全性 / 结构性分数，进入评测报告
- :white_check_mark: **LangGraph Checkpoint**：SqliteSaver 持久化，长对话跨进程可恢复
- :white_check_mark: **记忆系统分层增强**：L2 用户结构化事实（有效期截断 / 冲突消解）、L3 会话摘要、L4 最近原话窗口已接入三运行时 Prompt
- :white_check_mark: **Skill 自动蒸馏闭环**：默认第 3 次命中后生成并重载 `skills/auto/` Skill，自动 Skill 不再次计数以避免递归膨胀
- 记忆系统进一步升级：结构化用户画像 / 情绪轨迹、历史会话向量检索、L1/L2 协同检索、L2 事实审计与纠错工作台（高难度）
- 自动 Skill 审核工作台：查看生成内容、审批启用 / 拒绝 / 回滚并记录审计（中难度）
- 主动关怀闭环：高危用户 N 天未跟进自动生成提醒任务（复用工具队列）（中难度）
- 词表外置：路由 / 技能触发关键词从代码抽到 YAML（低难度）

### 工程化与运维

- CI/CD：GitHub Actions 跑 pytest + node check + harness（低难度）
- Alembic 迁移：消灭手写 DDL 与 ORM 的两份 schema 真相（中难度）
- `request_id` 贯通结构化日志（低难度）
- Prometheus 指标 + Grafana 面板（中难度）
- Docker Compose 全链路实测（待有 Docker 环境）

### 产品功能

- 心理量表接入（PHQ-9 / GAD-7）：定期测评 → 分数趋势 → 与风险阈值联动（中难度）
- 群体心理态势仪表盘：全校风险分布 / 话题热度（中难度）
- 教师与管理员权限细分（低难度）
- 企业微信 / 钉钉 webhook 告警通道（低难度）

---

## 贡献指南

欢迎提交 Issue 与 Pull Request。为保障主分支质量与评测可信度，请先阅读以下约定。

### 参与流程

```bash
# 1. Fork 本仓库后克隆到本地
git clone https://github.com/<你的用户名>/aegis-psych-agent.git
cd aegis-psych-agent

# 2. 新建分支（勿直接向 main 提交）
git checkout -b feat/<简短描述>     # 新功能
git checkout -b fix/<简短描述>      # 缺陷修复
git checkout -b docs/<简短描述>     # 文档更新

# 3. 开发并提交（遵循下方 commit 规范）
git add .
git commit -m "feat: 新增 XXX 能力"

# 4. 推送并创建 Pull Request
git push origin feat/<简短描述>
```

### 提交前自检清单

请在发起 PR 前确保以下条件全部满足：

- [ ] `python -m pytest tests -q` 全部通过
- [ ] 修改前端后执行 `node --check static/login.js static/student.js static/admin.js`
- [ ] 新增配置项已同步写入 `.env.example` 与本 README 的 [配置说明](#配置说明) 表格
- [ ] 新增依赖已写入 `requirements.txt`
- [ ] 未向仓库提交任何 `AEGIS_TRAINING_ROOT` 下的训练产物（脚本、数据、adapter、merged 模型、GGUF、报告）
- [ ] 未提交 `.env`、`data/` 下的本地数据与密钥文件

### Commit 规范

采用 Conventional Commits 前缀，示例：

| 前缀 | 用途 |
| :--- | :--- |
| `feat:` | 新功能 |
| `fix:` | 缺陷修复 |
| `refactor:` | 重构（不改变外部行为） |
| `perf:` | 性能优化 |
| `docs:` | 文档更新 |
| `test:` | 测试增删 |
| `chore:` | 构建 / 依赖 / 工具链 |

### 评测真实性原则（本项目核心约束）

1. **禁止为提升指标而修改金标样本**。`eval/fixtures/` 下的数据集视为不可随意变更的基准，任何调整需在 PR 中说明理由，并同步更新本文档的指标口径说明。
2. **允许非满分的真实通过率**。评测的目的是暴露边界，不是展示满分。
3. **引用指标必须注明口径与日期**，不得将不同轮次、不同开关配置下的数字混用。
4. 新增能力建议同步补充对应的评测用例或 harness suite。

### 代码组织约定

- 新增 Agent：在 `app/agents/` 实现并在 runtime factory 注册，确保三档运行时（`autonomous` / `langgraph` / `ordered`）均可调用
- 新增工具：必须在 `app/tools/contracts.py` 声明契约（角色、风险等级、审批要求、脱敏字段、最大重试次数），禁止绕过 ToolJob 直连执行
- 新增记忆层：遵循 L1~L4 分层职责，避免将事实抽取逻辑散落到单个 Agent 内部
- 涉及风险判定：必须保证规则通道兜底始终有效，任何模型通道失败都应安全降级

### Issue 建议

提交 Issue 时请包含：复现步骤、运行环境（OS / Python 版本 / `AI_PROVIDER` 与 `AGENT_RUNTIME` 取值）、相关日志或 trace。涉及安全问题的 Issue 请避免公开披露具体学生数据。

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源发布，版权归 **shangguanyunji663** 所有（Copyright (c) 2026）。

MIT 许可允许在保留版权声明的前提下自由使用、复制、修改、合并、发布、分发、再许可与销售本软件，但本软件「按原样」提供，**不含任何明示或暗示的担保**。

**附加条款（请一并遵守）**

> 本项目为心理支持场景的**工程学习与系统展示**项目，**不提供医学诊断，不能替代专业心理咨询或危机干预服务**。
> 未经专业评估，不建议将其直接用于真实生产心理咨询服务。
> 评测数据与指标反映测试集表现，**不等同于临床有效性评估**。

在二次分发或部署时，请确保使用者同样知悉上述声明。

---

<div align="center">

如果这个项目对你有帮助，欢迎 Star 或提交 PR。

Made with care for campus mental-health support engineering.

</div>

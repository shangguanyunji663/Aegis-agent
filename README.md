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
| Agentic RAG | 所有消息都检索知识库会增加噪声，尤其普通陪伴类对话容易被知识文档带偏 | 通过 CHAT / CONSULT / RISK 意图路由决定是否检索，混合 BM25 + 向量检索，并支持元数据过滤和 rerank |
| 工具治理与 MCP | 高风险预警、Excel 记录、邮件通知不能由模型越权直接执行 | 工具调用先生成 `ToolJob`，经角色、风险等级、审批、脱敏和审计后进入队列；支持 internal 和 FastMCP 两种后端 |
| 后台 Tool Queue | 外部工具慢、失败或限流时，不应阻塞学生端流式回复 | 独立 worker 支持依赖调度、重试延迟、邮件限流、dead letter、ExcelRecord 和 AlertRecord 持久化 |
| Engineering Harness | Agent 项目只看 demo 容易高估完成度，需要可重复验证 | 提供 pytest、RAG eval、综合 eval 和 harness runner，覆盖路由、风险、安全、RAG、API、工具队列等链路 |

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
| RAG | BM25, vector retrieval, Chroma optional backend, metadata filter, rerank |
| 工具协议 | FastMCP, governed ToolJob, background worker |
| 存储 | SQLite local mode, optional PostgreSQL, optional Redis lock |
| 前端 | 原生 HTML/CSS/JavaScript, student/admin 双端页面 |
| 工程验证 | pytest, custom eval runner, RAG eval runner, harness runner |
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

# 后端测试
python -m pytest -q

# 前端脚本语法检查
node --check static/login.js static/student.js static/admin.js

# 综合评测
python -m eval.run_eval

# RAG 独立评测
python -m app.rag_eval.runner

# 工程 Harness 验证
python -m app.harness.runner --suite all --output data/harness/latest.json

# 查看 MCP 能力
python -m app.mcp_tools.server --list
```

## 评测结果

当前仓库包含一套可重复运行的工程验证脚本，不依赖人工点击 demo 判断效果。

| 验证项 | 覆盖内容 | 最近验证结果 |
| --- | --- | --- |
| 单元与接口测试 | API、认证、风险识别、Agent runtime、MCP tools、评测 runner | `43 passed` |
| RAG 独立评测 | 66 条多主题心理支持检索样本，包含 expected source 和 expected terms | `HitRate 1.0000`, `MRR 0.9924`, `NDCG@K 0.9722` |
| 综合评测 | 路由、风险、安全、Skill、multi-turn、RAG summary、scaled benchmark | `all_passed=true`, `scaled_benchmark_total=150` |
| Harness 验证 | Risk Safety、Agent Routing、Standard Skills、RAG、API、Tool Queue 等链路 | `7/7 passed` |

> 评测数据用于工程回归和能力展示，不等同于临床有效性评估。

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
├── scripts/                      # 本地与 Compose 启动脚本
├── docs/                         # 架构、安全和演示文档
├── Aegis项目逐文件学习指南.md      # 从零构建式逐模块学习指南
├── docs/records/                 # 四轮迭代记录(重构/提速/注册MySQL/LangGraph)
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
| `VECTOR_BACKEND` | 向量后端，支持本地或 Chroma 配置 |
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
- [第五轮深度增强(风险双通道/FC/A·B评测/Judge/Checkpoint)](docs/records/DEEP-ENHANCEMENTS.md)

## 待改进与优化(Roadmap)

> 按「实现难度 × 实现意义」盘点的演进清单;带 ✅ 的已在本仓库落地,详见 [docs/records](docs/records/) 各轮说明文档。

### 安全与合规(心理场景立身之本)
- ✅ **风险评估双通道**:规则关键词 ∪ 轻量 LLM 二次评估,任一通道判高危即高危,规则兜底(`RISK_LLM_CHANNEL_ENABLED`)
- 危机转介资源可配置化:学校心理中心/紧急联系方式从硬编码改为按校配置、管理端可编辑(低难度)
- 对话数据字段级加密存储(中难度)
- 账号安全补齐:登录失败锁定、密码强度策略、会话撤销列表(低难度)
- 用户数据导出与删除(低难度)

### Agent 与算法深度
- ✅ **Function Calling 真接入**:GLM 自主选择回复技能,规则白名单兜底(`FUNCTION_CALLING_ENABLED`)
- ✅ **三运行时 A/B 评测**:langgraph/autonomous/ordered 同数据集对比延迟/trace/LLM 调用数(`--suite runtime-ab`)
- ✅ **LLM-as-Judge**:模型为回复打共情性/安全性/结构性分数,进入评测报告
- ✅ **LangGraph Checkpoint**:SqliteSaver 检查点持久化,长对话跨进程可恢复
- 记忆系统升级:滚动摘要 → 结构化记忆(用户画像+情绪轨迹+历史会话向量检索)(高难度)
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

# Aegis 第一轮模块化重构方案与变更记录

> 分支:`improve-code` · 时间:2026-08 · 性质:**纯结构性重构,业务逻辑零改动**(唯一功能增量:补齐 X-Request-ID / X-Trace-ID 中间件)
> 验证:`pytest 43/43 通过` · `harness 7/7 套件通过` · `pyflakes 干净` · `uvicorn 冒烟 + 登录 + SSE 正常`

***

## 1. 重构动机

初版代码在快速迭代中形成了典型的"有机生长"结构,主要问题:

| 问题      | 具体表现                                                                                    | 危害                           |
| ------- | --------------------------------------------------------------------------------------- | ---------------------------- |
| 上帝文件    | `app/repository.py` 1379 行:一个千行 `DatabaseStore` 大类 + BM25/重排/分词等纯算法 + 知识切块 + 记忆摘要 + 死代码 | 无法单测检索算法;改一处怕动全身             |
| 路由闭包堆积  | `app/main.py` 576 行,约 45 个路由全部以闭包形式塞在 `create_app()` 里                                  | 无法按领域拆分 review;依赖靠闭包捕获而非显式注入 |
| 重复实现    | `_loads`/`_now` 各复制 4 份(且时区语义不一致);看板读取函数 3 份;高危关键词表硬编码 4 处                              | 安全词表改一处漏三处的隐患                |
| 死代码     | 整个 `app/store.py`(JsonStore)从未被导入;repository 里 6 个被 `ReportCaseService` 取代的方法;多处未用导入    | 误导读者;pyflakes 噪声             |
| 提示词散落   | 中文系统提示词硬编码在 `llm.py`/`agents.py`/`agent_models.py`/`autonomous_agents.py` 四处            | 安全文案无法集中审计                   |
| 数据混入代码包 | 12 篇知识库 `.md` 和 RAG 评测数据集放在 `app/` 导入包内                                                 | 代码与数据边界模糊                    |
| 名不副实    | `static/app.js` 实为登录页脚本;"harness"/"runtime" 各有两三种含义                                     | 认知负担                         |

## 2. 重构原则

1. **不改业务逻辑**:只做移动、拆分、去重、删除;函数体逐字保留。
2. **去重时保语义**:三份看板意图推断函数其实有细微差异(是否看板风险预判、是否硬词回退),用参数化开关收编而非强行统一。
3. **每阶段回归**:每完成一个包的迁移即跑全量 pytest,保证随时可停。
4. **对外入口不变**:`uvicorn app.main:app`、`python -m app.init_db`、`python -m app.harness.runner`、`python -m app.mcp_tools.server`、`python -m app.rag_eval.runner`、`python -m eval.run_eval` 全部保持原样。

## 3. 新目录结构总览

```text
app/
├── main.py              # 应用入口:create_app 装配 + 中间件 + 路由注册(~90 行)
├── config.py            # pydantic-settings 全局配置
├── models.py            # 领域模型(新增 PendingReport.from_dict 统一转换)
├── entities.py          # SQLAlchemy ORM 实体(16 张表)
├── database.py          # 引擎/会话工厂/建表/遗留迁移/就绪检查
├── assessment.py        # 规则式风险评估(高危词表单一来源)
├── skills.py            # SkillRegistry 技能注册与工具 schema
├── core/                # 横切原语
│   ├── auth.py          #   PBKDF2 口令、会话令牌、AuthPrincipal
│   ├── privacy.py       #   敏感字段脱敏、内部信息泄漏检测、输入消毒
│   ├── runtime.py       #   RuntimeServices:Redis 限流/分布式锁(进程内降级)
│   └── utils.py         #   loads_dict/loads_or/dumps/now_utc/now_utc_naive
├── llm/                 # 模型后端
│   ├── client.py        #   LLMClient 协议 + Mock/OpenAI/Ollama + 工厂
│   └── prompts.py       #   支持回复与查询改写的消息模板
├── agents/              # 智能体层
│   ├── classic.py       #   六个单轮 Agent(Memory/Lead/Risk/Knowledge/Counselor/Companion)
│   ├── model_profiles.py#   每 Agent 模型档案(温度/提示词/提供方)
│   ├── runtime.py       #   AgentRegistry + AgentRuntimeRunner(有序执行计划)
│   ├── harness.py       #   AegisAgentHarness(单轮入口包装)
│   └── orchestrator.py  #   PsychOrchestrator(双运行时切换)
├── autonomous/          # 自治协作子系统
│   ├── events.py        #   事件枚举/任务/消息/产物/协作黑板(纯数据)
│   ├── registry.py      #   能力枚举/AgentProfile/决策/候选注册表
│   ├── board.py         #   黑板共享读取(意图/风险推断,参数化保语义)
│   ├── coordinator.py   #   认领制协调器(任务派生/认领/验收)
│   ├── agents.py        #   六个自治 Agent(包装单轮 Agent)
│   └── runtime.py       #   AutonomousAgentRuntime(黑板→聊天响应)
├── rag/                 # 检索子系统
│   ├── text.py          #   中英混合分词/计数/余弦
│   ├── scoring.py       #   BM25/词法重排/向量融合/邻块扩展
│   ├── chunking.py      #   frontmatter 解析/元数据过滤/滑窗切块
│   ├── memory.py        #   滚动会话记忆摘要
│   └── vector_store.py  #   Chroma 后端 + 本地哈希降级
├── repository/          # 持久化仓储
│   └── store.py         #   DatabaseStore(955 行,死方法已删)
├── tools/               # 工具治理
│   ├── contracts.py     #   ToolContract 契约与受治理载荷
│   ├── gateway.py       #   internal/MCP 双后端网关
│   └── mcp_client.py    #   MCP stdio 客户端
├── services/            # 业务服务
│   ├── report_case.py   #   报告/个案/交接摘要/工具任务派发
│   ├── tool_executor.py #   Excel/邮件/预警/JSONL 副作用执行
│   ├── tool_governance.py#  执行前契约/角色/风险授权
│   ├── tool_queue.py    #   队列服务 + 后台 worker(重试/死信/限流)
│   └── tool_records.py  #   ExcelRecord/AlertRecord 持久化
├── api/                 # HTTP 路由层(自 main.py 拆出)
│   ├── schemas.py       #   全部 Pydantic 请求模型
│   ├── deps.py          #   current_principal/require_admin/audit 依赖
│   ├── middleware.py    #   X-Request-ID/X-Trace-ID 追踪中间件
│   ├── pages.py         #   / /student /admin 页面
│   ├── system.py        #   /api/health /api/readiness /api/agent/status /api/skills
│   ├── auth_routes.py   #   /api/auth/*
│   ├── chat.py          #   /api/chat(+/stream)、/api/sessions*
│   └── admin.py         #   /api/admin/*(~20 个后台接口)
├── evaluation/          # 评测
│   ├── runner.py        #   八套指标聚合运行器
│   ├── datasets.py      #   150 条规模化基准语料
│   └── report_html.py   #   HTML 报告渲染
├── harness/             # 工程 Harness
│   ├── factory.py       #   共享装配工厂(消除 run_eval 重复)
│   └── runner.py        #   场景回放 + 7 套工程套件 CLI
├── mcp_tools/server.py  # FastMCP 工具服务(可选依赖)
└── rag_eval/runner.py   # RAG 独立评测 CLI
```

## 4. 旧 → 新文件映射

| 旧路径                                | 新路径                                               | 说明                                               |
| ---------------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| `app/auth.py`                      | `app/core/auth.py`                                | 平移                                               |
| `app/privacy.py`                   | `app/core/privacy.py`                             | 平移                                               |
| `app/runtime.py`                   | `app/core/runtime.py`                             | 平移                                               |
| —                                  | `app/core/utils.py`                               | **新增**:收编 4 份 `_loads`、4 份 `_now`、`_json`        |
| `app/llm.py`                       | `app/llm/client.py` + `app/llm/prompts.py`        | 客户端与提示词分离                                        |
| `app/agents.py`                    | `app/agents/classic.py`                           | 删除死方法 `compose`                                  |
| `app/agent_models.py`              | `app/agents/model_profiles.py`                    | <br />                                           |
| `app/agent_runtime.py`             | `app/agents/runtime.py`                           | <br />                                           |
| `app/agent_harness.py`             | `app/agents/harness.py`                           | 删除未被消费的 `AegisToolPlan` 与恒为 None 的分支             |
| `app/orchestrator.py`              | `app/agents/orchestrator.py`                      | `_report_from_dict` 改用 `PendingReport.from_dict` |
| `app/autonomous_events.py`         | `app/autonomous/events.py`                        | <br />                                           |
| `app/autonomous_registry.py`       | `app/autonomous/registry.py`                      | <br />                                           |
| `app/autonomous_coordinator.py`    | `app/autonomous/coordinator.py`                   | 底部 3 个重复函数删除                                     |
| `app/autonomous_agents.py`         | `app/autonomous/agents.py`                        | 底部 3 个重复函数删除;去未用导入                               |
| `app/autonomous_runtime.py`        | `app/autonomous/runtime.py`                       | 类内重复方法删除                                         |
| —                                  | `app/autonomous/board.py`                         | **新增**:黑板读取单一实现                                  |
| `app/repository.py`(1379 行)        | `app/repository/store.py`(955 行)+ `app/rag/*`     | 检索算法/切块/记忆摘要全部拆出                                 |
| `app/vector_store.py`              | `app/rag/vector_store.py`                         | <br />                                           |
| `app/tool_contracts.py`            | `app/tools/contracts.py`                          | <br />                                           |
| `app/tool_gateway.py`              | `app/tools/gateway.py`                            | <br />                                           |
| `app/mcp_client.py`                | `app/tools/mcp_client.py`                         | 删除死函数 `extract_job_id`/`queue_case_tools`        |
| `app/evaluation.py`                | `app/evaluation/{runner,datasets,report_html}.py` | 数据集与 HTML 模板拆出                                   |
| `app/main.py`(576 行)               | `app/main.py`(\~90 行)+ `app/api/*`                | 路由按领域拆为 7 个模块                                    |
| `app/store.py`                     | **删除**                                            | JsonStore 死文件                                    |
| `app/knowledge/*.md`               | `knowledge/*.md`                                  | 数据移出导入包                                          |
| `app/rag_eval/aegis-rag-eval.json` | `eval/fixtures/aegis-rag-eval.json`               | 评测数据归口                                           |
| `static/app.js`                    | `static/login.js`                                 | 名实相符(登录页脚本)                                      |
| —                                  | `app/harness/factory.py`                          | **新增**:共享装配工厂                                    |

## 5. 删除清单(均经全仓 grep 验证无引用)

- `app/store.py` 整文件(JsonStore,零引用)
- `repository.py`:`execute_tool_job`、`append_tool_output`、`_report_dict`、`_ensure_case`、`_ensure_case_tool_jobs`、`_case_dict`、`_handoff_summary`、`_follow_up_suggestion`(被 `ReportCaseService` 取代)、`session_belongs_to_user`、`recent_messages`
- `agents.py`:`CounselorAgent.compose`(无调用方)
- `agent_harness.py`:`AegisToolPlan`/`tool_plan`(计算后从未被消费)、`stream` 中 outcome 恒为 None 的死分支
- `mcp_client.py`:`extract_job_id`(与 gateway 内实现重复)、`queue_case_tools`
- `database.py`:模块级 `engine`/`SessionLocal`/`get_db`/`session_scope` 单例(零引用,`create_schema`/`readiness_check` 的默认引擎改为按需 `build_engine()`)
- 各文件未用导入(main.py 的 time/uuid4/Request、repository 的 RiskLevel、evaluation 的 asdict、autonomous\_agents 的 CompanionAgent、tests 的 ReportStatus 等约 10 处)

## 6. 去重明细(保留各调用点原语义)

| 重复项                                                       | 原位置                                                                | 收编到                                                                                                                            |
| --------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `_loads`(dict 守卫版)×2                                      | tool\_queue / tool\_records                                        | `core.utils.loads_dict`                                                                                                        |
| `_loads`(默认值版)×2                                          | repository / report\_case                                          | `core.utils.loads_or`                                                                                                          |
| `_now`(naive UTC)×2 + auth.utcnow                         | repository / report\_case                                          | `core.utils.now_utc_naive`                                                                                                     |
| `_now`(aware UTC)×2                                       | tool\_queue / tool\_records                                        | `core.utils.now_utc`                                                                                                           |
| `_json`                                                   | tool\_records                                                      | `core.utils.dumps`                                                                                                             |
| `_risk_from_board` ×3                                     | autonomous\_agents / autonomous\_runtime / autonomous\_coordinator | `autonomous/board.risk_from_board`(三份逐字相同)                                                                                     |
| `_intent_from_board` ×3(有差异!)                             | 同上                                                                 | `autonomous/board.intent_from_board(use_board_risk=…, use_hard_terms=…)` —— agents=双开,runtime=关硬词回退,coordinator=关看板风险预判,行为逐点保留 |
| `_hard_high_risk` ×2 + `HIGH_TERMS`                       | autonomous\_agents / autonomous\_coordinator / assessment          | `autonomous/board.hard_high_risk` 引用 `assessment.HIGH_TERMS`(词表内容验证一致)                                                         |
| `PendingReport` 字典转换 ×3                                   | orchestrator / autonomous\_runtime / (反向 report\_dict)             | `models.PendingReport.from_dict`                                                                                               |
| `build_local_orchestrator` ≈ `build_harness_orchestrator` | eval/run\_eval.py / harness/runner.py                              | `app/harness/factory.py`                                                                                                       |
| 双重 `settings = runtime_settings or get_settings()`        | main.py 86/91 行                                                    | 删除重复行                                                                                                                          |

## 7. 唯一功能增量:请求追踪中间件

`tests/test_api.py::test_readiness_and_auth_flow` 断言响应包含 `X-Request-ID`/`X-Trace-ID` 头,但原代码没有实现(重构前该测试失败)。新增 `app/api/middleware.py`:

- 每个请求生成 `req-*`/`trace-*` ID 并写入响应头;请求方自带同名头时沿用,便于链路串联。
- 属纯增量,不修改任何既有路径行为。重构后 43/43 测试全部通过。

## 8. 环境与配置变更

- `requirements.txt`:`mcp` 钉版为 `mcp>=1.0,<2`(mcp 2.x 移除了 `mcp.server.fastmcp`,与本项目代码不兼容,曾导致 2 个 MCP 测试失败)
- `config.py`:`knowledge_dir` 默认值 `app/knowledge` → `knowledge`;`rag_eval_dataset` → `eval/fixtures/aegis-rag-eval.json`
- `.env.example` / `.env`:`KNOWLEDGE_DIR=knowledge`
- `.gitignore`:补充 `.conda/`
- Dockerfile 无需改动(`COPY . /app` 已覆盖新目录)

## 9. 验证记录

| 验证项                                        | 结果                                                          |
| ------------------------------------------ | ----------------------------------------------------------- |
| `pytest tests/`                            | **43 passed, 0 failed**(重构前 42 passed / 1 failed)           |
| `pyflakes app/ eval/ tests/`               | 干净(仅 database.py 中带注释的有意惰性导入)                               |
| `python -m compileall`                     | 通过                                                          |
| uvicorn 冒烟                                 | `/api/health` UP;登录成功;响应含 `x-request-id`/`x-trace-id`       |
| `python -m app.mcp_tools.server --list`    | 正常输出能力清单                                                    |
| `python -m app.harness.runner --suite all` | **7/7 套件通过**(risk/routing/skills/rag/api/tool-queue/scaled) |
| 变更规模                                       | 87 个文件,+1734 / −1552 行                                      |

## 10. 遗留说明

- `database.migrate_legacy_schema` 仍与 `entities.py` 存在两份 schema 真相(手写 DDL 迁移),建议后续引入 Alembic 统一。
- `agents/classic.py` 中路由关键词表、`skills.py` 中技能触发词表仍为硬编码,可后续外置为配置。
- `McpToolGateway` 在同步方法内使用 `asyncio.run`,如需高并发可改造为原生异步。


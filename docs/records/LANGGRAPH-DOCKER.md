# Aegis 第四轮功能:LangGraph 编排 + Redis/Chroma 激活 + Docker(第四次提交说明)

> 分支:`improve-code` · 时间:2026-08 · 系列:[REFACTORING.md](REFACTORING.md) → [OPTIMIZATION.md](OPTIMIZATION.md) → [AUTH-MYSQL.md](AUTH-MYSQL.md) → 本篇
> 验证:`pytest 47/47`(含 4 个 LangGraph 新用例)· 全栈激活端到端 · SSE 直播确认

---

## 1. 目标与背景

对照目标能力清单,本轮补齐三项"代码在、未启用"的深度缺口:

| 缺口 | 本轮处理 |
| --- | --- |
| 多 Agent 编排缺少 LangGraph(仅有自研黑板 runtime) | 接入 LangGraph StateGraph 作为**主推运行时**,自研黑板保留为兜底/对照 |
| Redis 代码完整但 `.env` 未配置,限流/锁/记忆缓存全走进程内降级 | 激活并验证 |
| Chroma 代码完整但 `VECTOR_ENABLED=false`,向量检索走本地哈希降级 | 激活;因用户无向量模型额度,**嵌入改用 chromadb 内置本地 MiniLM(零外部依赖)** |
| docker-compose 用的还是 PostgreSQL,与本机 MySQL 事实矛盾 | 改为 mysql:8.0(本机无 Docker,已修文件待有环境时验证) |

## 2. LangGraph 接入(核心)

### 2.1 三档运行时
`AGENT_RUNTIME=langgraph`(主推)/ `autonomous`(自研认领制黑板,兜底)/ `ordered`(最简流水线)。三种运行时**复用同一批单轮 Agent 与安全规则**,只换编排机制——面试可讲"同一业务三种编排的对照"。

### 2.2 图设计(app/agents/langgraph_runtime.py)
```
START → load_memory → assess_risk → route_intent
                                      │ 条件边 _skip_context
                      companion+low ──┼── 直接 → compose
                      其他 ───────────┘→ context(RAG检索+稳定练习) → report(仅HIGH)
                                          → compose(标准Skill+提案) → finalize(终稿) → END
```
- 状态 `GraphState(TypedDict, total=False)`:`trace/skills` 用 `Annotated[list, operator.add]`,节点返回增量、LangGraph 自动合并
- 图只编译一次,每次对话 `invoke` 全新初始状态,线程安全
- `finalize` 节点仅低风险传 `on_token` 直播回调——与另两个运行时的安全门控完全一致
- 产出复用 `AutonomousRunOutcome`(board=None),orchestrator 统一收敛为 ChatResponse

### 2.3 编排器与状态上报
- `PsychOrchestrator`:惰性创建 langgraph runtime(不用不导入,可选依赖);`_run_langgraph` 镜像自治路径的事件发射/落库/SSE
- `/api/agent/status` 如实上报:`requested/active/scheduler/langgraph` 四字段,langgraph 启用时显示 `langgraph_state_graph / enabled`

### 2.4 与自研黑板的取舍(README 表述已同步修正)
LangGraph 提供声明式图结构与生态;自研黑板的认领制调度、SAFETY_OVERRIDE 一票否决、不可变快照是本项目差异化深度——两者并存,主推+兜底。

## 3. Redis 激活(实测)

`.env` `REDIS_URL=redis://localhost:6379/0`(本机 6379 已有服务)。验证:`/api/readiness` `redis: up`;`memory_backend_status` `primary=redis+sqlite`——限流计数、分布式锁、会话记忆缓存、Agent 私有记忆缓存全部切到 Redis,SQLite 仍为持久层。

## 4. Chroma 激活 + 本地嵌入(关键取舍)

**背景**:用户 KEY 仅有 GLM-4.7-Flash 聊天权限,**无向量模型额度**。

**方案**:新增 `EMBEDDING_PROVIDER=local|openai`(默认 openai 兼容 API 不变):
- `local`:chromadb 内置 `DefaultEmbeddingFunction`(MiniLM ONNX)——离线、零 key、零费用
- ChromaVectorBackend 重构:`_open_collection()` 统一建客户端/集合;`embed_texts` 本地/API 双路径
- `.env`:`EMBEDDING_PROVIDER=local` + `VECTOR_ENABLED=true`

**实测**:向量重建 12 chunks(3 秒);检索质量:考试压力→exam-season-guidance/sleep/anxiety,焦虑心慌→anxiety,关系冲突→relationships-and-family——中文检索由 BM25 主导、向量补充,混合融合下命中正确。`knowledge_status`:`backend=chroma, embedding_model=local-minilm, available=true`。

## 5. 测试密封性修复(本轮发现的真实工程问题)

**问题**:`.env` 新配置(REDIS/VECTOR/langgraph/EMBEDDING_PROVIDER)通过 pydantic-settings 泄漏进未显式固定配置的测试构造器,导致 7 个用例失败。

**修复原则**:测试不依赖开发者本机 .env——
- `tests/test_orchestrator.py build_orchestrator`、`tests/test_api.py build_client`:显式钉 `agent_runtime="autonomous", redis_url="", vector_enabled=False`
- `app/harness/factory.py`:装配改为密封 Settings(不吸 .env)
- 两个专测"OpenAI 路径缺 key"的检索用例:钉 `embedding_provider="openai"`
- `build_orchestrator` 的 `mkdir(parents=True, exist_ok=True)`:构造器可重复调用(根因修复,优于调用方绕路)

## 6. Docker(本机无 Docker,如实说明)

- `docker-compose.yml`:postgres:16 → **mysql:8.0**(utf8mb4、root/123456、卷持久化),app 的 `DATABASE_URL` 同步,新增 `EMBEDDING_PROVIDER: local`
- **未验证原因**:本机 `docker` 命令不可用。文件已按 MySQL 故事修正,待有 Docker 环境时 `docker compose up --build` 一键验证(app+mysql+redis+chroma 四容器)
- 本机全栈已用"直装"方式等效验证(MySQL+Redis 直连 + Chroma 内嵌持久化)

## 7. 涉及文件

| 文件 | 变更 |
| --- | --- |
| `app/agents/langgraph_runtime.py` | **新增**:StateGraph 编排六 Agent |
| `app/agents/orchestrator.py` | 三档分流 + `_run_langgraph` |
| `app/api/system.py` | agent_status 如实上报三档 |
| `app/config.py` | `embedding_provider` |
| `app/rag/vector_store.py` | 本地嵌入模式 + 初始化重构 |
| `app/harness/factory.py` | 密封装配 |
| `tests/test_langgraph_runtime.py` | **新增** 4 用例(低风险检索/高风险模板/companion 跳过 RAG/三档一致) |
| `tests/test_orchestrator.py` `test_api.py` `test_retrieval_eval.py` | 密封性钉配置 |
| `docker-compose.yml` | mysql:8.0 + EMBEDDING_PROVIDER |
| `.env` / `.env.example` | AGENT_RUNTIME=langgraph、REDIS_URL、VECTOR_ENABLED、EMBEDDING_PROVIDER |
| `requirements.txt` | +langgraph |

## 8. 验证记录

- pytest:**47/47**(43 原有 + 4 LangGraph)
- 三档运行时同消息风险判定一致(autonomous/ordered/langgraph 均 LOW)
- langgraph 低风险:counseling,知识检索 trace,GLM 真实回复;高风险:报告创建+本地安全模板(`plan:safety_template`)
- SSE 直播在 langgraph 运行时下工作(标准咨询首 token 4.13s——含查询改写+检索两次 LLM;81 个真实增量)
- 全栈 readiness:`database: up, redis: up, vector: chroma`

## 9. 遗留与建议

- Docker compose 未实测(本机无 Docker),待有环境验证
- MiniLM 对中文语义较弱,当前靠 BM25 主导;若未来获得向量模型额度,改 `EMBEDDING_PROVIDER=openai` + `OPENAI_EMBEDDING_MODEL` 即可切回 API 嵌入
- LangGraph 的 checkpoint/LangSmith 观测未接,可作为后续增强

# Aegis 第二轮：响应提速 + 真流式输出 + 管理端折叠

> 分支:`improve-code` · 时间:2026-08 · 系列:[REFACTORING](REFACTORING.md) → 本篇
> 性质:**响应提速 + 真流式输出 + 管理端折叠,纯性能与交互优化轮次**
> 验证:`pytest 43/43` · SSE 实测首 token 1.35s · 浏览器实测打字机与折叠交互

***

## 1. 问题诊断

### 1.1 响应太慢(~20-30s)的根源
| 层 | 问题 | 占比 |
| --- | --- | --- |
| 模型 | GLM-4.7-Flash 是深度思考模型,每次调用先生成约 1000 字内部推理再出正文(实测单次 15-47s) | ~90% |
| 调用结构 | 一次咨询对话串行两次 LLM 调用(检索词改写 + 回复生成) | 叠加 |

### 1.2 "整段文字突然弹出"的根源
学生端前端**本来就在用 SSE 并逐字渲染**——问题在后端:
1. `handle_stream` 把全部事件攒进列表、整条管线跑完才返回,HTTP 层再一次性倾泻(端到端缓冲);
2. token 事件是答案生成完毕后按 48 字符"假切块"补发的,不是模型真实输出流。

### 1.3 管理端可用性
9 个面板无任何折叠机制;Agent Trace 面板一次渲染 100 条、每条带完整回复文本,占据数屏空间,要看下面的板块必须大量滚动。

## 2. 优化项清单

### A1 关闭深度思考(单次调用 47s → 1.5s,实测)
- `app/config.py` 新增 `llm_thinking_enabled: bool = False`(环境变量 `LLM_THINKING_ENABLED`)
- `OpenAICompatibleClient` 在请求载荷注入 `thinking: {"type": "disabled"}`(智谱 GLM-4.x 系列参数;探测确认 glm-4.7-flash 支持且生效)
- 默认关闭;需要更"深思"的回复时设 `LLM_THINKING_ENABLED=true`

### A2 LLM 客户端真流式
- `LLMClient` 协议新增 `stream_support_reply(context, on_token) -> str | None`
- `OpenAICompatibleClient`:`stream:true` + 逐行解析 SSE,每个 delta 回调 `on_token`(`post_json_stream`)
- `OllamaClient`:ndjson 流式(`post_ndjson_stream`)
- `MockLLMClient`:返回 None → 走模板兜底,mock 行为零变化
- 中途异常返回已积累文本(用户已看到的不回退),一字未得才返回 None 回退阻塞调用

### A3 流式回调穿线(安全门控:仅低风险直播)
多 Agent 架构中 RiskGuardian 必须先对回复做泄漏/安全复核再验收,"直播"与"先审后发"天然冲突。取舍(已确认):**低风险直播,中/高风险审后输出**。
- 穿线链:`orchestrator._run_autonomous`(构造 TOKEN_EMITTED 实时发射器)→ `AutonomousAgentRuntime.run(on_reply_token=)` → `AutonomousRuntimeServices.on_reply_token` → Counselor/Companion 自治 Agent 在 `risk_from_board` 为 LOW 时传入 `finalize_plan(on_token=)`
- `CounselorAgent.finalize_plan(on_token=None)`:HIGH 恒走模板;低/中优先流式,失败回退阻塞调用
- ordered 路径同样按 `risk_level is LOW` 门控
- 直播过真实 token 后跳过结尾的 `_token_chunks` 假切块(防重复);done 事件始终携带复核终稿

### A3+ SSE 链路队列化(真直播的最后一环)
`/api/chat/stream` 重构:管线在后台线程执行,事件经 `queue.Queue` 实时推给响应生成器——彻底移除"跑完才倾泻"的端到端缓冲;异常兜底路径(error+done)同样走队列。`handle_stream`/`AegisAgentHarness.stream` 增加 emit 直通参数。

### A4 学生端 UI(student.js + styles.css)
- 等待期三点打字动画(`.typing-dots`),首 token 到达自动替换
- route/skill/report 事件渲染为气泡下方一行小状态(风险等级/已检索知识库/已生成报告),提升等待感知
- done 事件用复核终稿覆盖气泡(终稿保险);error 事件显示"重试中"

### B 管理端折叠(admin.html/js + styles.css)
- 9 个面板全部支持展开/收起:头部折叠按钮(chevron 旋转过渡)+ `.card-body` 显隐
- 状态按面板 id 记入 localStorage,刷新后保持;默认仅 TRACES 收起(用户痛点)
- Trace 行副标题(完整回复文本)CSS line-clamp 截断为两行,点击行仍可在右侧详情面板看完整 JSON

## 3. 实测数据(优化前后)

| 指标 | 优化前 | 优化后 |
| --- | --- | --- |
| 单次 LLM 调用(同提示词实测) | 47.2s(思考)/ ~15s(均值) | **1.5s** |
| 咨询对话总耗时(SSE 端到端) | ~30s | **4.2s**(陪伴类 3.1s) |
| 首个可见字符 | ~30s(等全部完成) | **1.35s**(真流式首 token) |
| 高风险回复 | — | 0.7s(本地模板,不经模型) |
| 直播 token 数/次 | 0(全部为事后假切块) | ~117-154(真实增量) |

浏览器实测:发送 1.2s 后气泡内已出现正文并持续打字;终稿与直播内容一致(安全复核未改稿时逐字相同);Agent Trace 默认收起、点击展开(100 行可见)、再点 CASES 收起(行不可见)、刷新后状态保持。

## 4. 本轮文件清单

| 文件 | 变更 |
| --- | --- |
| `app/config.py` | +`llm_thinking_enabled` |
| `app/llm/client.py` | thinking 注入;`stream_support_reply`×3;`post_json_stream`/`post_ndjson_stream` |
| `app/agents/classic.py` | `finalize_plan(on_token)` 流式分支 |
| `app/autonomous/agents.py` | services 增 `on_reply_token`;两处 act 门控传参 |
| `app/autonomous/runtime.py` | `run(on_reply_token)` 透传 |
| `app/agents/orchestrator.py` | `handle_stream(emit)` 直通;双路径 token 发射器与假切块跳过 |
| `app/agents/harness.py` | `stream(emit)` 直通 |
| `app/api/chat.py` | SSE 队列化 + 后台线程 |
| `static/student.js` / `styles.css` | 打字动画/状态行/终稿覆盖 |
| `static/admin.html` / `admin.js` / `styles.css` | 9 面板折叠 + Trace 截断 + localStorage 记忆 |
| `.env` / `.env.example` | +`LLM_THINKING_ENABLED=false` |

## 5. 验证记录

- `pytest tests/`:43/43 通过(mock 路径流式返回 None,行为不变)
- `node --check`:student/admin/login 三个 JS 通过
- SSE 实测(Python 客户端 + 浏览器):三类消息(低风险咨询/低风险陪伴/高风险)延迟与内容见上表;高风险走模板 0.7s 返回,符合"高风险不经模型"设计
- 浏览器(实际 UI):学生端打字机与终态、管理端折叠交互与状态记忆,全部通过

## 6. 设计取舍说明

- **直播仅限低风险**:RiskGuardian 的泄漏/安全复核必须先于用户可见,这是项目"规则优先"哲学的延续;低风险直播的残余风险(模型在直播中输出内部字段)由系统提示词禁止 + done 终稿覆盖兜底,且高风险路径完全不直播。
- **思考默认关闭**:心理支持回复对深度推理需求有限,实测关闭后回复质量未见下降、延迟降 30 倍;保留开关供需要时启用。
- **假切块保留**:中/高风险与非流式后端(如模型不支持流式)仍靠 `_token_chunks` 提供打字机观感,作为兜底而非主路径。

## 7. 遗留与建议

- GLM-4.7-Flash 关思考后单次 ~1.5-2s,如需进一步压缩可换 `glm-4.6v-flash`(实测 2.9s 含网络)或减小 `knowledge_top_k`
- route/skill 状态行目前仅在事件到达时更新;自治模式下这些事件在轮次结束时回放,若要"过程可见"需将黑板事件实时外发(可在 coordinator 轮内加 emit 回调,属后续增强)
- 管理端 Trace 仍一次渲染 100 条(已截断显示);如数据量再增长可加后端分页

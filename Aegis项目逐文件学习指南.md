# Aegis 项目学习指南 — 从零构建一个校园心理支持多 Agent 平台

> 本文档按照「如果你要从头写这个项目，你会怎么思考和编码」的顺序组织。它不是一份 API 清单，而是一份引导式蓝图：先讲清楚「为什么这样设计」（架构思路）、「谁负责什么、怎么协作」（模块职责与流程）、「为什么选这些技术」（选型理由）、「怎么把它跑起来」（环境搭建），最后才逐文件拆解「每一站具体怎么写」（动手实现）。
>
> 读者定位：刚接触 Agent 应用开发、有 Python 基础的学生。你不需要先懂 LangChain 或 RAG——本文档从「为什么需要这个东西」讲起。读完并按引导走完，你应当能依据思路独立搭出结构相同、功能一致的项目，而不是照抄代码。
>
> 文档结论的「正确性」以仓库当前 `main` 分支为准；本文档在多处给出「为什么这么选」的判断，便于你在自己的项目里做取舍。

***

<a id="how-to-use"></a>

# 如何使用本指南（先读这一页）

> 本节是整份指南的「导航页」：先用 2 分钟确定适合你的学习路径，再按路径跳读；任何时候迷路了，回到本页的目录或文末术语表即可。

## 四类读者，四条路径

| 你是… | 建议路径 | 预计投入 | 怎么走 |
| --- | --- | --- | --- |
| 想先看看效果 | 路径 A · 快速体验 | 约 1 小时 | 读 1.1 → 按 4.2 跑起来 → 按 4.5 三步验证 → 照「总结三」实操。其余章节用到再回来查。 |
| 零基础系统学习 | 路径 B · 全程跟学 | 1~2 周 | 从第零部分补齐概念 → 按第一~五部分顺序通读 → 每站完成「动手试一试」与「练习」。 |
| 有经验、想查特定专题 | 路径 C · 专题跳读 | 按需 | 用下方「专题地图」直接定位；每站开头的「为什么先写它」都可独立成篇。 |
| 要把它讲给别人 / 裁剪成自己的项目 | 路径 B + 第七部分 | 2~3 周 | 全程跟学后，用「总结四」的从零重建检查清单逐项自测。 |

**路径 C · 专题地图**（四个最受关注的话题，各自的最短阅读路线）：

- **多 Agent 协作**：1.5 → 2.2 → 第 7 站（全书核心）→ 8.1 / 8.4 → 第 13 站 `runtime-ab` 套件
- **RAG 检索**：第三部分「BM25 + Chroma」条目 → 第 9 站（重点 9.7）→ 第 10 站 `search_knowledge` → 第 13 站 RAG 评测
- **安全与工具治理**：1.2 设计哲学 → 第 3 站 → 2.2 / 2.3 → 第 11 站 → 第 13 站 `risk` 套件
- **评测体系**：4.7 命令速查 → 第 13 站 → 第 14 站 tests 说明 → 4.9 开发工作流

## 每一站的固定结构

第五部分的每一站都按同一结构展开，便于查阅与跳读：

1. **为什么先写它** —— 该站在依赖图中的位置与设计动机；
2. **怎么写** —— 关键代码片段 + 逐段解读（请对照真实源码读）；
3. **动手试一试** —— 一段可直接复制运行的示例与预期输出；
4. **常见易错点** —— 新人最常踩的坑，先看一遍能省掉大半调试时间；
5. **练习** —— 2~3 道递进练习，附验证方式。

## 全书总目录

| 部分 | 内容 | 回答的问题 |
| --- | --- | --- |
| [第零部分](#part-0) | [预备知识与术语表](#glossary) | 「这个词是什么意思？」 |
| [第一部分](#part-1) | 架构设计思路 | 「为什么这样设计？」 |
| [第二部分](#part-2) | 模块职责与交互流程 | 「谁负责什么、怎么协作？」 |
| [第三部分](#part-3) | 关键技术选型理由 | 「为什么选这些技术？」 |
| [第四部分](#part-4) | 环境搭建与运行步骤 | 「怎么把它跑起来？」 |
| [第五部分](#part-5) | 从零动手 · 14 站实现地图 | 「每一站具体怎么写？」 |
| [第六部分](#faq) | 常见问题解答（FAQ） | 「卡住了 / 想不通，看哪里？」 |
| [第七部分](#part-7) | 总结与自检清单 | 「怎么确认自己学会了？」 |

快速跳转：[第〇章 学习路线总览](#station-0) · [第 1 站](#station-1) · [第 2 站](#station-2) · [第 3 站](#station-3) · [第 4 站](#station-4) · [第 5 站](#station-5) · [第 6 站](#station-6) · [第 7 站](#station-7) · [第 8 站](#station-8) · [第 9 站](#station-9) · [第 10 站](#station-10) · [第 11 站](#station-11) · [第 12 站](#station-12) · [第 13 站](#station-13) · [第 14 站](#station-14) · [术语表](#glossary) · [FAQ](#faq)

## 三条使用建议

1. **先跑通，再阅读**：环境搭建只需十几分钟（第四部分），跑通后读每一站都能随手用「动手试一试」验证理解，比纯阅读快得多。
2. **对照源码读**：本文所有代码片段都标注了出处文件；片段是为讲清主干做了删节，完整行为以源码为准。
3. **卡住先查 FAQ**：第六部分按「概念 / 运行排错 / 学习建议」归类了高频问题；仍解决不了再回到对应章节细读。

***

<a id="part-0"></a>

# 第零部分：预备知识与术语表（零基础从这里开始）

> 读者定位是「有 Python 基础、刚接触 Agent 应用开发」。本部分回答两个问题：**我需要先会什么？** **文档里的术语都是什么意思？** 读完即可无障碍进入第一部分；后续章节遇到生词，随时回到 [术语表](#glossary) 查。

## 0.1 预备知识自检清单

| 领域 | 需要掌握到… | 不会怎么办 |
| --- | --- | --- |
| Python | 函数、类、`dataclass`、`Enum`、类型注解；能读懂（不必会写）`async/await` | 先过一遍官方教程；本文用到新语法时会就地给一句解释 |
| 命令行 | 会 `cd`、`pip`、`python -m` | 对照 4.2 逐行抄即可，每条命令都有注释 |
| HTTP | 知道「请求-响应」「JSON」「状态码」 | 第 12 站开头有 3 分钟版背景说明 |
| SQL | 知道「表、行、列」即可 | ORM 会替你写 SQL，1.3 / 1.4 有最小背景 |
| 大模型 | 用过任意聊天产品即可 | 0.2 从「LLM 是什么」讲起 |

## 0.2 十分钟概念速成

每个概念按「一句话定义 → 在本项目长什么样 → 详见」三段展开：

- **LLM（大语言模型）**：读入文字、预测后续文字的模型，项目里用来生成回复、改写检索词、辅助判风险。本项目把它抽象成 `LLMClient` 协议；`AI_PROVIDER=mock` 时用本地假模型替代——这是「默认可本地运行」承诺的基石。→ 第 5 站。
- **Prompt（提示词）**：喂给模型的文字指令与上下文。`llm/prompts.py` 把「系统角色 + 记忆 + 知识 + 技能约束」按结构拼装成一次调用的输入。→ 5.2。
- **Token**：模型处理文字的最小单位（约一个词/半个词/一个字）。聊天「逐字直播」就是逐 token 推送。→ 2.2。
- **Agent（智能体）**：能「感知上下文 → 决策 → 调用能力（技能/检索/工具）→ 产出」的软件角色。本项目有六类 Agent，各有「名片」（能力、系统提示词、工具权限）。→ 第 6、7 站。
- **多 Agent 协作**：多个 Agent 围绕共享状态分工——谁认领任务、产出什么、谁验收。本项目用「黑板 + 认领制」实现，是全书核心。→ 第 7 站。
- **RAG（检索增强生成）**：回答前先从知识库检索相关片段，把片段连同问题一起喂给模型——让模型「开卷考试」。流水线 = 分词 → 召回（BM25/向量）→ 融合 → 重排。→ 第 9 站。
- **BM25**：经典词频打分算法：查询词在某文档出现越多、且该词越稀有，得分越高。可解释、零成本、零延迟。→ 9.2。
- **嵌入 / 向量检索**：把文字压成一串数字（向量），语义相近的文字向量距离近，用余弦相似度检索；能命中「睡不好 ↔ 失眠」这类词面不重叠的同义表达。→ 9.6 / 9.7。
- **Rerank（重排）**：对召回候选做精细二次排序，把最相关的顶到最前。本项目用纯 Python 四路词法信号加权实现。→ 9.7.3。
- **SSE（Server-Sent Events）**：服务器向浏览器单向持续推送文本的 HTTP 协议，聊天「打字机效果」的标准做法。→ 第三部分 SSE 条目、2.2。
- **ORM**：把数据库表映射成 Python 类，用对象而非 SQL 字符串读写数据。本项目用 SQLAlchemy 2.0。→ 1.3 / 1.4。
- **依赖注入**：模块不自己 new 依赖，而是「从外面递进来」——测试时递假的进去就能隔离。本项目随处可见（`SkillRegistry` 的回调、FastAPI 的 `Depends`）。→ 第 4 站、12.2。
- **Function Calling（工具调用）**：让模型从白名单里挑一个函数并给出参数，由**代码**执行。模型只「点菜」，不「下厨」。→ 第 4 站。
- **MCP（Model Context Protocol）**：把「工具」封装成跨进程标准服务的协议。本项目工具网关可在 internal / MCP 两种后端间切换，治理不变。→ 11.6。
- **黑板模式（Blackboard）**：协作各方的中间产物写到一块「只增不删」的黑板上，任何人随时读取、推断全局状态。→ 7.1。
- **SCD-2（缓慢变化维度第二型）**：数据仓库术语——旧值不删，标记生效区间，保留完整演变史。项目用它管理「用户事实」。→ 9.5。
- **常用评测指标**：HitRate@k=前 k 条结果里命中的比例；MRR=首个相关结果排名倒数的平均；NDCG=考虑排名位置的加权质量分；FPR=误报率（把正常表达判成高风险的比例）。→ 第 13 站。

## 0.3 术语表

<a id="glossary"></a>

按主题分组；每条给出本项目内的标准叫法（全文统一按此书写，检索时直接搜中文词即可）。

**模型与提示**

| 术语 | 对应代码 / 配置 | 在本项目中的含义 |
| --- | --- | --- |
| 模型后端 | `LLMClient` | 协议 + Mock / OpenAI 兼容 / Ollama 三实现（第 5 站） |
| mock 模式 | `AI_PROVIDER=mock` | 无外部 key 的本地假模型，所有 LLM 方法返回 `None` → 触发模板兜底 |
| 风险双通道 | `assess_message` ∪ `assess_risk` | 规则通道与 LLM 通道取并集，任一判 high 即 high（第 3 站） |
| 真流式 | `stream_support_reply` | 模型 token 一边生成一边经 SSE 推给前端（8.1） |

**检索与记忆**

| 术语 | 对应代码 / 配置 | 在本项目中的含义 |
| --- | --- | --- |
| 知识块 | `KnowledgeChunk` | 知识文档切块后的最小检索单元，带元数据与可选向量（1.3） |
| 混合检索 | `KNOWLEDGE_FUSION_MODE` | BM25 + 向量双路召回 → weighted / RRF 融合 → rerank（9.7） |
| 邻块扩展 | `expand_best_hit` | 把冠军块的同源相邻块拼回来，防答案被「拦腰截断」（9.7.4） |
| 记忆四层 | L1~L4 | Agent 私有 / 用户事实（SCD-2）/ 会话摘要 / 原话窗口（9.5） |
| 滚动摘要 | `build_memory_summary` | 每轮一行、超字符预算丢最旧（9.4） |

**协作与运行时**

| 术语 | 对应代码 / 配置 | 在本项目中的含义 |
| --- | --- | --- |
| 黑板 | `CollaborationBlackboard` | 一轮对话的共享状态，append-only、克隆式不可变（7.1） |
| 工件 | `AgentArtifact` | Agent 发布到黑板的一切中间产物（memory/intent/risk/…）（7.1） |
| 认领制 | claim-based | Agent 按「能力匹配 + 置信度」主动认领任务（7.4） |
| 安全一票否决 | `SAFETY_OVERRIDE` | 该事件发出后黑板风险恒为 HIGH，不可被后续评估覆盖（7.5） |
| 预算护栏 | `AGENT_MAX_ROUNDS` 等 | 轮次上限 / 每轮认领上限 / 单 Agent 认领上限（7.4） |
| 三档运行时 | `AGENT_RUNTIME` | autonomous（默认）/ ordered / langgraph（1.5、8.4） |

**治理与安全**

| 术语 | 对应代码 / 配置 | 在本项目中的含义 |
| --- | --- | --- |
| 待审报告 | `PendingReport` | 高风险对话产生、等管理员审批的报告（2.3） |
| 工具任务 | `ToolJob` | 一切外部副作用的受治理封装：先审批，后异步执行（第 11 站） |
| 契约 | `ToolContract` | 每个工具的「谁能调、什么风险、要不要审批、脱敏哪些字段」（11.1） |
| 死信 | `DeadLetterRecord` | 重试超限后落入的可运营失败队列（11.3） |
| 脱敏 | `redact_payload` | 敏感字段替换为 `[redacted]`，存储侧与输出侧双覆盖（2.2） |
| 输入消毒 | `sanitize_user_input` | 进模型前压缩空白、把「手机号」等替换成中性说法（2.2） |

**工程与评测**

| 术语 | 对应代码 / 配置 | 在本项目中的含义 |
| --- | --- | --- |
| 会话 | `ChatSession` | 一次多轮对话的容器，带归属（owner）校验（1.3） |
| trace | `AgentRunTrace` | 每一步 Agent 动作的落库痕迹，管理端可回放（第 10 站） |
| 工程 Harness | `app/evaluation/harness` | 8 套件端到端回放，失败退出码 1 可接 CI（第 13 站） |
| 技能 | `SkillSpec` | 注册成表的能力单元；人工策展与自动蒸馏两类（第 4 站） |
| 蒸馏 | `SKILL_DISTILL_ENABLED` | 把反复出现的技能组合固化成 auto SKILL.md（4.1） |

## 0.4 行文约定

- 风险等级一律写 HIGH / MEDIUM / LOW（对应 `RiskLevel` 枚举）；「高危」= HIGH；
- 「待审报告」= PendingReport，「工具任务」= ToolJob，「黑板」= CollaborationBlackboard，「安全复核」= RiskGuardian 对回复提案的审查；
- 代码片段若标注文件路径即出自该文件，为讲清主干有删节；`...` 表示省略与本节无关的字段；
- 所有命令默认在项目根目录、已激活虚拟环境（见 4.2）的前提下执行。

***

<a id="part-1"></a>

# 第一部分：架构设计思路（先理解「为什么」）

## 1.1 我们要解决什么问题

校园心理支持场景里，一个「聊天机器人」远远不够。用户（学生）和管理者（辅导员/学校心理中心）关心的东西完全不同：

-   学生侧  关心的是：能不能放心倾诉、对话是否连续、遇到危机时有没有人管。
-   管理侧  关心的是：谁有风险、风险多高、有没有留下可追溯的记录、外部动作（通知家长/老师/建档）有没有被审批和审计。

如果只做一个聊天框，会出现三个真实矛盾，这正是本项目设计的起点：

1.   「普通聊天」不该被过度检索和过度工具化。   学生说「今天好累」，如果每次都去知识库检索、都要调工具，回复质量反而被噪声拖垮。需要「先判断意图，再决定要不要检索/调工具」。
2.   「高风险表达」必须进入可审计流程。   涉及自伤、危机的表达，不能只由模型「回复一句安抚」就结束——它需要人审、脱敏、重试、留痕，且工具执行不能由模型越权直接触发。
3.   「多 Agent 协作」不能只是顺序调用。   单个 Lead Agent 串行分派，复杂场景下没有中间产物、没有任务认领、没有验收点，一旦出错无法复盘。

>   一句话定位：Aegis 不是聊天机器人，而是把「学生侧即时支持」与「管理侧可审计干预」拆成两套独立信息架构，并用一套后端 Agent Runtime 统一处理意图路由、记忆注入、RAG 检索、风险报告、trace 落库与工具计划。

## 1.2 四条贯穿全程的设计哲学

记住这四条，后面每个模块你都会看到它们的影子：

1.   安全前置、规则优先  ：高风险判断靠确定性关键词规则（`assessment.py`），不靠模型输出。LLM 永远拿不到「是否高危」的最终决定权——它只是「双通道」里的辅助通道，且失败/超时自动回退纯规则。
2.   治理与业务正交  ：工具只管「做事」，而「谁能调、什么风险等级能调、要不要审批、哪些字段要脱敏、失败怎么重试」统一在契约层（`tools/contracts.py`）拦截。业务代码不再散落 `if role == admin` 之类的判断。
3.   确定性可回放  ：多 Agent 协作的全部中间状态落在 append-only 黑板（blackboard）上，事件进 trace 落库。任何一次回复都能复盘「谁认领了什么、产出什么、被谁驳回、最终怎么验收」。
4.   默认可本地运行  ：`AI_PROVIDER=mock` 时不需要任何外部 API key，整条闭环（含评测）照样跑通。这是对「学习友好」和「演示友好」的关键承诺。

## 1.3 分层架构总览

把系统想象成一组同心圆 + 一条主线：最外层是两个前端（学生端 / 管理端），往里是 HTTP 层，再往里是 Harness（统一编排入口），再往里是 Agent Runtime（三档可切换的协作引擎），最底层是 RAG、工具治理、持久化与评测。

```mermaid
flowchart LR
    subgraph 前端
      Student["学生端 /student"]
      Admin["管理端 /admin"]
    end
    subgraph HTTP层
      API["FastAPI API 层<br/>鉴权 / 限流 / 路由"]
    end
    subgraph 编排层
      Harness["AegisAgentHarness<br/>脱敏 / 上下文 / trace / 报告"]
    end
    subgraph 运行时层[三档运行时可切换]
      Runtime["Autonomous Blackboard<br/>/ Ordered / LangGraph"]
    end
    subgraph 能力层
      Agents["六类 Agent<br/>Memory/Lead/Risk/Knowledge/Counselor/Companion"]
      RAG["Hybrid RAG<br/>BM25 + Vector + Rerank"]
      Tools["工具治理<br/>ToolJob + 契约 + 审计"]
    end
    subgraph 基础设施
      Store["持久化<br/>SQLite / MySQL / PG"]
      Queue["后台 Tool Queue Worker"]
      Eval["评测闭环<br/>pytest / eval / harness"]
    end

    Student --> API
    Admin --> API
    API --> Harness
    Harness --> Runtime
    Runtime --> Agents
    Runtime --> RAG
    Runtime --> Tools
    Harness --> Store
    Tools --> Queue
    Queue --> Store
    Admin --> Eval
    Eval --> Store
```

## 1.4 为什么是「双端分离 + 中间 Harness」

-   双端分离  ：学生倾诉体验和管理员处置流程关注点不同，混在一起会让产品边界混乱、权限模型复杂。`/student` 提供对话与会话记忆，`/admin` 提供报告、个案、trace、知识库、工具队列、评测。
-   中间 Harness  ：Agent 调用、上下文注入、风险报告、trace 落库、消息持久化、工具计划如果散落在业务/路由代码里，既难审计也难复用。`AegisAgentHarness` 把它们收口成薄适配层——路由层因此可以保持「参数校验 + 鉴权 + 限流」的纯净，不碰任何 Agent 细节。这也是「让 HTTP 层与 Agent 世界解耦」的标准做法。

## 1.5 为什么「三个运行时」同时存在

这是本项目最有教学价值的设计之一。`AGENT_RUNTIME` 可切换三档：

| 运行时              | 编排方式                                | 定位                                       |
| ---------------- | ----------------------------------- | ---------------------------------------- |
| `autonomous`（默认） | 自研 append-only 黑板 + 认领制协调器          | 真正的多 Agent 协作：共享状态、任务认领、产物验收、安全 override |
| `ordered`        | 六类单轮 Agent 按固定顺序跑                   | 最简链路，便于理解「每个 Agent 各做一步」                 |
| `langgraph`      | LangGraph `StateGraph` 声明式状态图 + 条件边 | 工业级编排，带 `SqliteSaver` 检查点，长对话可恢复         |



为什么三个运行时都要存在：三者复用同一批 Agent 与安全规则，只是「调度方式」不同。这让读者可以：先读 `ordered` 理解每个零件，再读 `autonomous` 理解真实协作，最后对比 `langgraph` 理解工业方案——并且用「三运行时 A/B 评测」证明换引擎不改业务语义（三档运行时判定彼此一致）。

## 1.6 一次对话的宏观数据流（俯瞰）

先建立全局印象，细节在后续章节展开：

```
学生输入
 → HTTP 层(限流 + 归属校验)
 → Harness(输入消毒 + 会话解析)
 → Orchestrator(三运行时开关,默认 autonomous)
 → AutonomousRuntime(建黑板 → Coordinator 认领循环)
      Memory 读取 → Lead 路由意图 → Risk 评估风险
      → Knowledge 检索(RAG) → Counselor/Companion 产出回复提案
      → RiskGuardian 安全复核(不通过则打回修订)
      → FINAL_ACCEPTED
 → 落库(assistant 消息 + 记忆更新 + AgentRunTrace)
 → ChatResponse(JSON / SSE)
 [异步,管理端] 审批高风险报告 → 建个案 → 派 5 个 ToolJob → Worker 执行 → 落记录
```

***

<a id="part-2"></a>

# 第二部分：模块职责与交互流程

## 2.1 模块职责矩阵

这张表是后续阅读地图的「索引」。每个模块回答三个问题：负责什么 / 对外暴露什么 / 依赖谁。

| 模块                                                       | 核心职责                                                                                                 | 对外关键接口                                                                                           | 主要依赖               |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------ |
| `app/config.py`                                          | 全局配置（env / .env 映射，全部带安全默认值）                                                                         | `Settings`、`get_settings()`                                                                      | pydantic-settings  |
| `app/models.py`                                          | 领域模型（Intent/RiskLevel/ChatResponse 等纯数据词汇表）                                                          | 枚举、`dataclass`、SSE 映射                                                                            | 仅标准库               |
| `app/entities.py`                                        | ORM 实体（19 张表，含第十三轮新增的 L2 事实表）                                                                                        | `Base` 下的实体类                                                                                     | SQLAlchemy         |
| `app/database.py`                                        | 引擎/会话工厂/建表/迁移/就绪检查                                                                                   | `build_engine`、`build_session_factory`、`create_schema`                                           | SQLAlchemy         |
| `app/assessment.py`                                      | 确定性风险评估（规则通道单一事实来源）                                                                                  | `assess_message()`                                                                               | 无（纯函数）             |
| `app/skills.py`                                          | 注册式执行 Skill、人工策展 Skill、使用观察器与自动蒸馏/重载                                                                                 | `SkillRegistry`、`response_skill_names()`                                                         | store 回调注入         |
| `app/core/`                                              | 横切原语：auth（口令/会话）、privacy（脱敏/消毒）、runtime_services（Redis 限流锁，可降级）、network（出站 URL 校验，SSRF 防护）、utils | 各类工具函数                                                                                           | redis（可选）          |
| `app/llm/`                                               | 模型后端：client（Mock/OpenAI/Ollama 三实现 + 工厂）、prompts（提示词）                                                | `LLMClient`(Protocol)、`build_llm_client()`                                                       | httpx/urllib       |
| `app/agents/classic.py`                                  | 六个单轮智能体（各司其职、无状态）                                                                                    | `MemoryAgent`/`RiskGuardianAgent`/`LeadAgent`/`KnowledgeAgent`/`CounselorAgent`/`CompanionAgent` | llm、skills、rag     |
| `app/agents/orchestrator.py`                             | 装配六 Agent + 双/三运行时切换总入口                                                                              | `PsychOrchestrator`                                                                              | 上述全部               |
| `app/agents/harness.py`                                  | Runtime Harness：脱敏/会话解析/报告/trace 收口                                                                  | `AegisAgentHarness`                                                                              | orchestrator、store |
| `app/agents/langgraph_runtime.py`                        | LangGraph StateGraph 运行时 + 检查点                                                                       | `LangGraphRuntime`                                                                               | langgraph          |
| `app/autonomous/`                                        | 自治协作：events（协议）、registry（能力/决策）、board（共享读）、coordinator（认领循环）、agents（六自治 Agent）、runtime（黑板→响应）        | `AutonomousAgentRuntime`                                                                         | llm、rag、store      |
| `app/rag/`                                               | 检索与记忆子系统：text（分词）、scoring（BM25/rerank/融合）、chunking（切块/元数据）、facts（L2 事实抽取与渲染）、memory（L3 摘要）、vector\_store（Chroma/本地降级） | `DatabaseStore.search_knowledge`（组装检索流水线）                                                        | chromadb（可选）       |
| `app/repository/store.py`                                | 持久化总闸（约 1146 行，第十三轮新增 L4/L2 方法后更新）                                                                               | `DatabaseStore`                                                                                  | entities、rag       |
| `app/tools/`                                             | 工具治理：contracts（契约）、gateway（internal/MCP 网关）、mcp\_client                                              | `governed_payload()`、`build_tool_gateway()`                                                      | store              |
| `app/services/`                                          | 业务服务：report\_case（审批后编排）、tool\_executor（真实副作用）、tool\_queue（队列/worker）、tool\_records、tool\_governance | `ReportCaseService`、`ToolQueueWorker`                                                            | store、tools        |
| `app/api/`                                               | HTTP 路由：schemas/deps/middleware/pages/system/auth\_routes/chat/admin                                 | RESTful + SSE 接口                                                                                 | FastAPI、harness    |
| `app/mcp/`                                               | MCP 边界：server（FastMCP 工具服务）/ client（stdio 客户端）（可选后端）                                       | `@mcp.tool` 暴露的工具                                                                                | store、contracts    |
| `app/evaluation/`（含 `harness/`）、`eval/`              | 评测闭环：runner / rag（双口径+消融）/ datasets / report\_html / runtime\_ab / judge / harness（factory 装配工厂 + runner 场景回放） | `eval.run_eval`、`app.evaluation.harness.runner`                                                 | store、llm          |
| `static/`、`tests/`                                       | 双端原生前端 + pytest 单测（历史验证结果应以运行日期和环境为准）                                                                                 | HTML/JS 页面、测试                                                                                    | —                  |

## 2.2 学生端对话主流程（时序图）

```mermaid
sequenceDiagram
    participant U as 学生(浏览器)
    participant API as chat.py(SSE)
    participant H as AegisAgentHarness
    participant O as PsychOrchestrator
    participant R as AutonomousRuntime
    participant C as Coordinator+Agents
    participant S as DatabaseStore

    U->>API: POST /api/chat/stream
    API->>API: 限流 + 归属校验 + 鉴权
    API->>H: run(message, session_id)
    H->>H: sanitize_user_input + ensure_session
    H->>O: 路由到 _run_autonomous
    O->>R: run(session_id, message)
    R->>C: 建黑板 + TURN_STARTED → 认领循环
    C->>S: 读 Memory / 写 Memory
    C->>C: Lead 路由 / Risk 评估 / Knowledge 检索 / 产出提案
    C->>C: RiskGuardian 安全复核(不通过→修订循环)
    R-->>H: AutonomousRunOutcome(intent/risk/response/trace)
    H->>S: 落 assistant 消息 + 记忆 + trace
    H-->>API: 事件流(emit)
    API-->>U: SSE 逐字推送(低风险真流式)
```

要点：低风险对话在生成的同时逐字直播（真流式，首字延迟≈模型首 token）；中/高风险回复经安全复核通过后才输出，不直播。

## 2.3 风险识别与报告闭环（时序图）

```mermaid
sequenceDiagram
    participant S as 学生
    participant R as RiskGuardian
    participant H as Harness/Store
    participant A as 管理端
    participant RC as ReportCaseService
    participant Q as ToolQueueWorker
    participant T as 真实副作用

    S->>R: 表达高风险内容
    R->>R: assessment(规则) ∪ llm.assess_risk(双通道)
    R->>H: 建 PendingReport + SAFETY_OVERRIDE 事件
    H->>H: 回复用本地安全模板(模型无决定权)
    A->>A: 查看待审报告 / trace
    A->>RC: 审批(APPROVED, 风险≥MEDIUM)
    RC->>RC: ensure_case + ensure_case_tool_jobs(5 个 ToolJob)
    RC->>Q: 入队 alert/email/ledger/handoff/follow_up
    Q->>T: 后台执行(重试/限流/死信)
    T->>T: Excel/Alert/Email/Handoff/审计落记录
```

要点：高风险场景下，模型不碰外部动作；一切副作用都先变成受治理的 `ToolJob`，经审批、脱敏、审计后才由后台 worker 异步执行。

## 2.4 工具治理与后台执行（时序图）

```mermaid
sequenceDiagram
    participant Svc as ReportCaseService
    participant GW as ToolGateway(Internal/MCP)
    participant Store as DatabaseStore
    participant W as ToolQueueWorker
    participant Ex as tool_executor
    participant Ext as Excel/SMTP/Webhook/文件

    Svc->>GW: create_tool_job(kind, payload, role, approved)
    GW->>Store: governed_payload() 角色/风险/审批/脱敏 校验
    alt 校验失败
        Store->>Store: 仍写审计(rejected) + 抛异常
    else 校验通过
        Store->>Store: 落 ToolJob(PENDING)
    end
    W->>Store: run_pending(批量领取)
    W->>W: 依赖就绪? / 限流? / 重试延迟?
    W->>Ex: execute(kind, payload, attempts)
    Ex->>Ext: 真实副作用
    alt 成功
        Store->>Store: 标记 SUCCESS + 落 ExcelRecord/AlertRecord
    else 超限失败
        Store->>Store: 写 DeadLetterRecord(可运营失败)
    end
```

要点：契约在入队前统一关卡（责任链），被拒绝的调用也要留痕；worker 用「生产者-消费者」模型把副作用异步化，不阻塞学生端；失败可重试、可进死信。

## 2.5 模块装配与依赖关系（谁创建谁）

`app/main.py` 的 `create_app()` 是整张依赖图的「装配中心」，顺序即依赖顺序：

```
settings → engine/会话工厂 → create_schema
 → DatabaseStore(默认账号 + 知识库种子)
 → RuntimeServices(Redis 限流/锁,可降级)
 → SkillRegistry(注入 store 回调)
 → LLM 客户端
 → PsychOrchestrator(registry, store, llm)
 → AegisAgentHarness(orchestrator, store)
 → ToolGateway(按 TOOL_BACKEND 选 internal/mcp)
 → ToolQueueWorker(lifespan 启停)
```

所有实例挂到 `app.state.*`，路由通过 `request.app.state.xxx` 显式获取——这是「依赖注入」的轻量实现，比初版「45 个路由闭包捕获变量」可读、可测得多。

***

<a id="part-3"></a>

# 第三部分：关键技术选型理由

> 这部分是「为什么选它」。每个条目给：选了什么 → 为什么 → 替代方案 → 代价/取舍。便于你在自建项目时做判断。

### FastAPI + Uvicorn

- **选了**：FastAPI 作 Web 框架，Uvicorn 作 ASGI 服务器。
- **为什么**：类型注解即文档、依赖注入（`Depends`）天然适合「鉴权依赖」、原生支持 `StreamingResponse`（SSE 流式输出）、异步性能足够。
- **替代**：Flask（同步、SSE 不自然）、Django（重、异步心智负担）。
- **代价**：需要理解 `async`/`await` 与 lifespan；本项目真正异步的只有 HTTP 层，Agent 计算仍是同步调用（够用）。

### Pydantic + pydantic-settings

- **选了**：`pydantic-settings` 的 `BaseSettings` 做全局配置，`pydantic` 模型做请求/响应 schema。
- **为什么**：环境变量 + `.env` 自动映射、大小写不敏感、字段带安全默认值（不写任何 `.env` 也能本地跑）、类型校验。这是「配置即数据」的工程化落地。
- **替代**：手写 `os.getenv` + `argparse`，会散落常量、缺类型、无默认值管理。
- **代价/取舍**：`extra="ignore"` 让未知变量被忽略（避免误拼字段直接崩溃，但也意味着拼写错误不报错——是可接受的取舍）。

### SQLAlchemy 2.0（ORM）+ SQLite / MySQL / PostgreSQL

- **选了**：SQLAlchemy 2.0 声明式 ORM，`DatabaseStore` 作读写总闸；SQLite 默认、MySQL/PG 可切换。
- **为什么**：声明式实体与领域模型解耦（models 是「怎么说」，entities 是「怎么存」）；`pool_pre_ping` + `pool_recycle` 防断连；SQLite `check_same_thread=False` 兼容后台线程；同一套 ORM 实体兼容三种数据库。
- **替代**：裸 `sqlite3`/SQL 字符串（无类型、易 SQL 注入、难迁移）、Django ORM（绑定框架）。
- **代价/取舍**：手写 `migrate_legacy_schema()` 与 ORM 是「两份 schema 真相」的遗留债（正路是 Alembic）；小项目手写迁移能用，正规项目应上 Alembic。

### LangGraph（三档运行时之一）

- **选了**：`langgraph` 的 `StateGraph` 作声明式状态图编排，挂 `SqliteSaver` 检查点。
- **为什么**：条件边、声明式节点、`TypedDict` 状态 + `Annotated[list, operator.add]` 增量合并、图编译一次后每次 `invoke` 新状态（天然线程安全）、检查点支持长对话跨进程恢复（`get_state(session_id)` 可读最近终态）。
- **替代**：手写状态机（易出错、难维护）、只用顺序流水线（无分支/回退）。
- **代价/取舍**：引入额外依赖与心智模型；作者特地保留 `autonomous`/`ordered` 作为对照与兜底，避免「工具绑架业务」。

### 自研 append-only Blackboard + 认领制（核心运行时）

- **选了**：不依赖任何框架的黑板模式 + claim-based 协调器。
- **为什么**：多 Agent「协作」需要真实语义——谁认领、凭什么（能力+置信度）、产出什么、如何验收。`append_artifact` 每次克隆出新黑板（不可变快照），协作过程天然可回放、无共享状态竞争；`SAFETY_OVERRIDE` 事件实现安全「一票否决」；`REVISION_REQUESTED` 实现「提案→复核→修订」循环。
- **替代**：单 Lead 串行分派（伪协作、无中间产物）、纯 LangGraph（也支持，但自研版更易做教学演示与对照评测）。
- **代价/取舍**：自研调度逻辑需要自己保证终止（轮次/每轮认领/单 Agent 认领三道预算护栏）；`force_response` 保证学生端永远有答案。

### BM25 + Chroma 本地 MiniLM + Rerank（混合 RAG）

- **选了**：BM25（词频，中文用 bigram）与可选向量检索融合，Chroma 作向量库；启用 Chroma 时可选 chromadb 内置 MiniLM 本地嵌入（`EMBEDDING_PROVIDER=local`）或 OpenAI 兼容嵌入，最后用纯 Python 四路词法信号加权 rerank。
- **为什么**：
  - BM25 可解释、零成本、零延迟，且中文补二元组后词频统计更准（不引 jieba 的轻量取舍）。
  - 本地 MiniLM 可让「向量库是真的、嵌入是离线的」；不需要向量模型额度。
  - rerank 用 `base*0.55 + (余弦*0.75+关键词*0.25)*0.25 + 覆盖率*0.15 + 短语命中*0.05`，纯 Python，零额外模型成本。
- **替代**：
  - 纯向量检索：中文语义高度依赖嵌入模型质量——不同模型对中文的理解差异很大（如「考试压力」和「焦虑失眠」在低质量嵌入中可能距离很远），且商业向量模型需要 API 额度，无 KEY 时完全不可用；
  - 纯 BM25：只做词频匹配，缺乏语义泛化能力——学生说「我最近睡不好」，可能无法命中包含「失眠」「睡眠质量」的知识块；
  - 引入 jieba/重模型：依赖与成本上升。
- **代价/取舍**：`VECTOR_ENABLED=false`（代码默认）会禁用向量召回，但仍保留 BM25 + 条件 rerank；`LocalVectorBackend`（哈希 bigram 伪向量 + 本地余弦）是**已启用向量**但 Chroma 不可用、或显式选择 local 后端时的降级实现，不是关闭向量开关后的替代品。`Settings.embedding_provider` 的代码默认是 `openai`，`.env.example` 以 `local` 提供无密钥演示示例，应当区分这两种“默认”。

### Redis（可选，限流/锁）

- **选了**：`redis` 作限流计数与分布式锁后端，但**连不上立即降级**到进程内实现。
- **为什么**：限流窗口与「防止两个管理员同时触发批处理」的锁是运维增强，不是功能必需。
- **替代**：纯进程内字典（单机够用，但多实例无效）。
- **代价/取舍**：`check_rate_limit`/`lock` 必须写「Redis 实现 + 本地退化实现」两份，语义一致——这是可选依赖的代价，也是本地零依赖可跑的前提。

### SSE（Server-Sent Events）

- **选了**：`StreamingResponse` + `text/event-stream` 做真流式。
- **为什么**：学生端要「逐字直播」的陪伴感；SSE 比 WebSocket 简单（单向）、与 FastAPI 天然契合。
- **替代**：WebSocket（双向、过重）、轮询（延迟高、浪费）。
- **代价/取舍**：流式请求在「连接建立阶段」才重试，一旦开始接收 delta 就不再回退（避免已直播的 token 被丢掉）；流中出错也补发 `error+done` 事件，前端不白屏。

### FastMCP（`mcp>=1.0,<2`，可选工具后端）

- **选了**：`mcp` 包的 FastMCP 作工具协议，支持 internal / FastMCP 两种后端。
- **为什么**：工具调用先生成受治理 `ToolJob`，再经角色/风险/审批/脱敏/审计进入队列；`McpToolGateway` 通过 stdio 拉起 FastMCP server 子进程调用**同一套受治理工具**——协议变、治理不变。
- **替代**：让模型直接 function-call 外部 API（越权、不可审计、不可重试）。
- **代价/取舍**：MCP 路径是可选增强（默认 `internal`）；治理契约不随后端切换而失效，这是「治理与业务正交」的体现。

### pytest + 自研评测闭环（工程化验证）

- **选了**：pytest 单测（历史验证数量需附日期/环境） + `evaluation/runner`（真实指标）+ `evaluation/harness/runner`（8 套件端到端回放）+ RAG 专项 eval + 三运行时 A/B + LLM-as-Judge。
- **为什么**：Agent 项目「只看 demo 容易高估完成度」。评测用 **mock LLM 保证确定性**，测的是「系统」不是「模型运气」；harness 失败退出码 1，可接 CI。
- **替代**：纯手工点 demo（不可重复、不可回归）。
- **代价/取舍**：维护数据集与套件有成本，但换来「改一个词（如 `HIGH_TERMS`）跑一遍评测就能确认没破坏安全边界」。

### Docker + docker-compose（部署）

- **选了**：`python:3.12-slim` 基础镜像 + 多服务 compose（app / mysql / redis / chroma）。
- **为什么**：一键起完整生产近似环境；默认本地模式仍可用 SQLite（compose 里也可切）。
- **替代**：裸机部署（需手动装 MySQL/Redis/Chroma）。
- **代价/取舍**：Compose 全链路实测依赖 Docker 环境；本地零依赖模式仍是首选学习路径。

### 其他依赖的取舍

- `cryptography`：口令用 PBKDF2-HMAC-SHA256 而非引 bcrypt，零额外依赖达及格线。
- `openpyxl`：高风险台账真写 Excel，不引重依赖。
- `pypdf`：管理端知识库上传 PDF 惰性导入（用到才 import）。
- `httpx`：异步 HTTP 客户端（SMTP/外部调用备用）。
- 不引 `jieba`/`yaml`：中文分词用 bigram、frontmatter 手写解析，刻意控制依赖面，降低「新人装不上」的门槛。

***

<a id="part-4"></a>

# 第四部分：环境搭建与运行步骤（引导式）

> 目标：不依赖任何外部 API key，把系统本地跑通，并发一条消息、看一次风险闭环。

## 4.1 环境要求

-   Python  ：3.12（Docker 用 `python:3.12-slim`；本地建议 ≥3.10，SQLAlchemy 2.0 需要）。
-   网络  ：默认 `AI_PROVIDER=mock` 完全离线；接 OpenAI/Ollama/Chroma/Redis/SMTP 才需要网络或本地服务。
-   操作系统  ：Linux/macOS/Windows 均可；Windows 路径用反斜杠激活脚本即可。

## 4.2 方式一：本地 venv（推荐学习路径）

```bash
# 1) 进入项目根
cd aegis-psych-agent

# 2) 建虚拟环境
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3) 装依赖（requirements.txt 已固定版本范围）
pip install -r requirements.txt

# 4) 准备配置
cp .env.example .env               # 之后按需改 .env

# 5) 初始化数据库 + 知识库种子
python -m app.init_db

# 6) 启动服务
uvicorn app.main:app --host 127.0.0.1 --port 8091
```

如果要使用已经通过八门槛验收的 v9 QLoRA 风险模型，先启动 D 盘隔离推理服务，再启动 FastAPI：

```bat
set AEGIS_TRAINING_ROOT=D:\AegisTraining
set AEGIS_QLORA_MODEL_DIR=%AEGIS_TRAINING_ROOT%\exports\aegis-risk-qwen3.5-2b-v9-merged
%AEGIS_TRAINING_ROOT%\envs\qlora-qwen35\python.exe ^
  %AEGIS_TRAINING_ROOT%\training\scripts\serve_risk_qlora.py ^
  --model-dir "%AEGIS_QLORA_MODEL_DIR%"
```

确认 `http://127.0.0.1:8301/health` 返回 `status=ok` 后即可完成本地 smoke test；该 localhost 地址不要写入应用 `.env`。应用集成必须使用受保护的公网 HTTPS endpoint：

```ini
RISK_QLORA_ENABLED=true
RISK_QLORA_URL=https://your-approved-qlora.example.com
RISK_QLORA_TIMEOUT_SECONDS=8
```

再执行上面的 FastAPI 启动命令。不开启时 `RISK_QLORA_ENABLED=false`，行为保持原样；服务超时、不可达或 JSON 非法时自动回退规则。训练根目录、模型路径和服务脚本位置均可按机器改为其他 `AEGIS_*` 配置，不要求使用 `D:\AegisTraining`。


打开浏览器：

- 首页：<http://127.0.0.1:8091>
- 学生端：<http://127.0.0.1:8091/student>
- 管理端：<http://127.0.0.1:8091/admin>

默认演示账号：

| 角色  | 用户名       | 密码            |
| --- | --------- | ------------- |
| 学生  | `student` | `student123!` |
| 管理员 | `admin`   | `admin123!`   |

> 教师注册需邀请码（默认 `aegis-teacher`，由 `AUTH_TEACHER_INVITE_CODE` 配置）。生产务必修改。

## 4.3 配置 `.env`：最小可运行 vs 进阶

`.env.example` 是推荐配置清单；但要区分三类值：**`Settings` 代码默认**、**示例文件建议值**和**部署时由 `.env`/系统环境变量覆盖的值**。例如 `embedding_provider` 的代码默认是 `openai`，`.env.example` 则推荐 `local` 以便无外部密钥演示；本地开发者自己的 `.env` 不属于仓库默认。最小可运行可直接使用代码默认（`AI_PROVIDER=mock`、SQLite、`VECTOR_ENABLED=false`、Redis 空）。按组理解关键变量：

| 分组  | 变量                                                           | 作用                                 | 默认                               |
| --- | ------------------------------------------------------------ | ---------------------------------- | -------------------------------- |
| 模型  | `AI_PROVIDER`                                                | `mock`/`openai`/`ollama`           | `mock`                           |
| 模型  | `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`OPENAI_MODEL`            | OpenAI 兼容端点                        | 空 / api.openai.com / gpt-4o-mini |
| 模型  | `OLLAMA_BASE_URL`/`OLLAMA_MODEL`                             | 本地 Ollama                          | 127.0.0.1:11434 / qwen2.5:7b     |
| 模型  | `LLM_THINKING_ENABLED`                                       | 深度思考（接 GLM 建议关）                    | `false`                          |
| 模型  | `LLM_SUPPORT_TEMPERATURE`                                    | 支持性回复采样温度（偏高更真人）                   | `0.6`                            |
| 风险  | `RISK_LLM_CHANNEL_ENABLED`                                   | 通用 LLM 风险通道；`RISK_QLORA_ENABLED=true` 时由 QLoRA 接管 | `true`                           |
| 风险  | `RISK_QLORA_ENABLED` / `RISK_QLORA_URL` / `RISK_QLORA_TIMEOUT_SECONDS` | v9 QLoRA 隔离服务开关 / 地址 / 超时 | `false` / `https://qlora-endpoint.example.invalid` / `8` |
| 技能  | `FUNCTION_CALLING_ENABLED`                                   | 模型在白名单内自主选技能                       | `true`                           |
| 检索  | `EMBEDDING_PROVIDER`                                         | `openai`（代码默认）/ `local`（离线 MiniLM 示例）      | `openai`（`.env.example` 推荐 `local`）                          |
| 检索  | `VECTOR_ENABLED` / `VECTOR_BACKEND`                          | 是否启用向量 / 后端                        | `false` / `chroma`               |
| 检索  | `KNOWLEDGE_FUSION_MODE` / `KNOWLEDGE_CACHE_ENABLED`          | 加权/RRF 融合 / 进程内缓存开关              | `weighted` / `false`             |
| 记忆  | `MEMORY_RECENT_MESSAGES` / `MEMORY_SUMMARY_MAX_CHARS`        | L4 原话窗口 / L3 摘要上限                  | 15 / 3000                        |
| 技能  | `SKILL_DISTILL_ENABLED` / `SKILL_DISTILL_MIN_REPEAT` / `SKILL_DISTILL_DIR` | 是否蒸馏 / 重复阈值 / 输出目录 | `true` / 3 / `skills/auto` |
| 运行时 | `AGENT_RUNTIME`                                              | `autonomous`/`ordered`/`langgraph` | `autonomous`                     |
| 运行时 | `AGENT_MAX_ROUNDS` / `AGENT_FINAL_ACCEPTANCE_MIN_CONFIDENCE` | 预算护栏                               | 8 / 0.6                          |
| 限流  | `CHAT_RATE_LIMIT_PER_MINUTE` / `REDIS_URL`                   | 聊天限流 / 可选 Redis                    | 40 / 空                           |
| 工具  | `TOOL_BACKEND`                                               | `internal`/`mcp`                   | `internal`                       |
| 工具  | `ALERT_EMAIL_DELIVERY_MODE`                                  | `log`/`smtp`                       | `log`                            |
| 工具  | `TOOL_QUEUE_*`                                               | worker 轮询/批量/线程/重试                 | 2s/20/4/5s                       |
| 存储  | `DATABASE_URL`                                               | SQLite / MySQL / PG                | `sqlite:///data/aegis.sqlite`    |
| 认证  | `AUTH_DEFAULT_*` / `AUTH_TEACHER_INVITE_CODE`                | 默认账号 / 教师邀请码                       | 见上表                              |



**切到 MySQL 8.0（可选）**：在 `.env` 设

```bash
DATABASE_URL=mysql+pymysql://root:你的密码@localhost:3306/aegis?charset=utf8mb4
```

首次启动自动建库建表（utf8mb4）；旧 SQLite 数据可用 `python -m scripts.migrate_sqlite_to_mysql` 一键迁移（旧文件保留备份）。

## 4.4 初始化到底做了什么

`python -m app.init_db` → `create_schema()` 惰性导入全部 ORM 实体后 `create_all`；`DatabaseStore` 在 `create_app` 时还会 `ensure_default_users()`（建演示账号）与 `seed_knowledge_dir()`（遍历 `knowledge/` 下的 `.md`/`.txt`，当前仓库提交 24 篇 Markdown 文档，切块、可选嵌入、写入 `KnowledgeChunk`）。所以「启动即带知识库」。

## 4.5 验证：三步跑通闭环

1.   普通对话  ：学生端登录 `student/student123!`，发「我最近考试压力很大，晚上睡不着」。管理端 `/admin` 应能搜到对应知识、看到会话 trace。
2.   风险闭环  ：发「我不想活了」。观察：学生端得到本地安全模板回复（mock 下也是）→ 管理端出现「待审报告」→ 审批 → 「工具任务」全部 `success`（可在死信/审计页核对）。
3.   代码护栏  ：往 `app/assessment.py` 的 `HIGH_TERMS` 加一个词，跑 `python -m pytest tests -q` 与 `python -m app.evaluation.harness.runner --suite risk`——体会「单一来源 + 评测护栏」让修改变安全。

## 4.6 方式二：Docker Compose

```bash
docker compose up --build
```

Compose 启动 app + MySQL 8.0 + Redis + Chroma。若要在容器里启用向量检索，在 `.env` 设 `VECTOR_ENABLED=true`、`VECTOR_BACKEND=chroma`、`EMBEDDING_PROVIDER=local`；若使用 OpenAI 兼容嵌入，再额外注入 `OPENAI_API_KEY`。PostgreSQL 驱动可供自行部署的数据库使用，但不在当前 Compose 拓扑内。访问地址同 4.2。

## 4.7 常用命令速查

```bash
# 初始化数据库
python -m app.init_db

# 后端测试（tests/ 目录；联调脚本已迁至 scripts/smoke_chat.py，不在收集范围）
python -m pytest tests -q

# 前端脚本语法检查
node --check static/login.js static/student.js static/admin.js

# 综合评测
python -m eval.run_eval

# RAG 独立评测(双口径 + 消融)
python -m app.evaluation.rag

# 本地性能 benchmark(并发/延迟/吞吐/缓存/ToolJob)
python -m scripts.run_benchmark

# 工程 Harness 验证(8 套件)
python -m app.evaluation.harness.runner --suite all --output data/harness/latest.json

# 三运行时 A/B
python -m app.evaluation.harness.runner --suite runtime-ab

# 查看 MCP 能力
python -m app.mcp.server --list
```

## 4.8 常见问题与排错

-   `ModuleNotFoundError`  ：没激活 venv 或没装依赖——回到 4.2 第 2、3 步。
-   SQLite 多线程报错  ：确认用的是 `sqlite:///...` 且 `check_same_thread=False`（代码已处理；若自改 engine 注意这点）。
-   向量检索不工作  ：`VECTOR_ENABLED=false` 会关闭向量召回，但 BM25 + 条件 rerank 仍可用；想要向量召回需设 `VECTOR_ENABLED=true`，再选择 Chroma 或 local-hash 后端。`LocalVectorBackend` 是已开启向量时的本地降级，不是关闭向量后的替代品。
-   邮件/预警没发出  ：默认 `ALERT_EMAIL_DELIVERY_MODE=log`，只写日志；要真发需配 `SMTP_*`。
-   限流误伤  ：本地演示调小 `CHAT_RATE_LIMIT_PER_MINUTE` 或调大；Redis 为空时走进程内限流。
-   改代码后行为异常  ：优先跑 `python -m pytest tests -q` + harness，再用 4.5 的「风险闭环」手动验证，避免只信 demo。

## 4.9 建议的开发工作流

1. 先 `python -m pytest tests -q` 确立基线；历史“约 71 项通过”只对应特定日期和依赖环境，当前数量以实际收集结果为准。
2. 小步修改 → 跑相关单测 + 对应 harness 套件（如改风险逻辑跑 `--suite risk`）。
3. 涉及编排/运行时时跑 `runtime-ab` 确认三档判定一致。
4. 涉及回复质量时跑 LLM-as-Judge（接真模型时）或 `test_reply_style.py` 守底线。
5. 需要可重复的 eval/Harness 时，显式关闭 `SKILL_DISTILL_ENABLED` 或把自动 Skill 输出目录隔离；否则重复调用可能写入 `data/skill-usage.json` 和 `skills/auto/`，污染后续基线。
6. 提交前 `python -m app.evaluation.harness.runner --suite all`。

***

<a id="part-5"></a>

# 第五部分：从零动手 — 14 站实现地图

> 下面每一站对应一个文件/模块。引导式学习法：先读「为什么先写它」，再对照源码走一遍，最后尝试不抄代码、凭理解重写一遍该站。每站末尾另有三件套——「动手试一试」（可直接复制运行的示例与预期输出）、「常见易错点」、「练习」：零基础读者建议每站都完成三件套再前进，有经验的读者可只挑练习。

<a id="station-0"></a>

## 第〇章 学习路线总览

Aegis 是一个「学生倾诉 + 风险识别 + 管理员处置」的完整闭环系统。从头写它，你会经过 14 站：

```
第 1 站   地基          config / models / entities / database   — 先把"数据形状"立起来
第 2 站   安全底座      core/(auth / privacy / runtime / utils)— 账号、脱敏、限流先于一切功能
第 3 站   风险评估      assessment.py                            — 确定性规则,不依赖大模型
第 4 站   技能层        skills.py                                — 把"能力"注册成可调用单元
第 5 站   模型后端      llm/(client + prompts)                  — 让"大脑"可插拔
第 6 站   单轮智能体    agents/classic.py                        — 六个各司其职的角色
第 7 站   自治协作      autonomous/(黑板 + 认领制)              — 多 Agent 真正的协作机制
第 8 站   编排与 Harness agents/orchestrator + langgraph + harness — 把一切串成一次对话(三档运行时)
第 9 站   RAG 检索      rag/(分词/打分/切块/向量)                — 知识库如何被"检索"出来
第 10 站  持久化仓储    repository/store.py                      — 所有表的读写总闸
第 11 站  工具治理      tools/ + services/                       — 高风险动作必须被管住
第 12 站  HTTP 层       api/ + main.py                           — 把能力暴露成接口
第 13 站  评测闭环      evaluation/(含 harness/) + eval/     — 用数据证明系统有效
第 14 站  收尾          static/ + tests/                         — 双端界面与质量兜底
```



**贯穿全程的四条设计哲学**（见第一部分 1.2）：安全前置规则优先 / 治理与业务正交 / 确定性可回放 / 默认可本地运行。

***

<a id="station-1"></a>

## 第 1 站 地基：config / models / entities / database

### 1.1 app/config.py — 全局配置



**为什么先写它**：后面每个模块都要读配置（模型提供方、知识库路径、限流阈值……），配置层必须最先就位。

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///data/aegis.sqlite"
    ai_provider: str = "mock"          # mock / openai / ollama
    knowledge_dir: str = "knowledge"   # 知识库目录(项目根下)
    agent_runtime: str = "autonomous"  # autonomous / ordered / langgraph 三档开关
    agent_max_rounds: int = 8
    agent_final_acceptance_min_confidence: float = 0.6
    ...
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

- `BaseSettings` 来自 `pydantic-settings`：环境变量和 `.env` 文件自动映射到字段（`AI_PROVIDER=xxx` → `ai_provider`），大小写不敏感。
- 每个字段都有安全默认值——你不写任何 .env，系统也能本地跑。
- `project_root` 属性 + `resolve_path()` 把「相对路径配置」统一解析到项目根，兼容从任意工作目录启动：

```python
@property
def project_root(self) -> Path:
    return Path(__file__).resolve().parents[1]

def resolve_path(self, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else self.project_root / path
```

- `@lru_cache` 的 `get_settings()` 保证全进程只有一份配置实例。



**学习要点**：配置是「数据」不是「代码」；用带默认值的声明式字段替代散落各处的常量；`.env.example` 是给使用者的配置说明书。

### 1.2 app/models.py — 领域模型（纯数据）

这一层定义全项目通用的词汇表，不依赖任何其他 app 模块（测试时可以单独 import 它）：

```python
class Intent(str, Enum):        # 意图:companion 陪伴 / counseling 咨询 / risk 风险 / research 查资料
    COMPANION = "companion" ...

class RiskLevel(str, Enum):     # 风险三级分流,整个系统的"红绿灯"
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"
```

继承 `str, Enum` 是个小技巧：`RiskLevel.HIGH == "high"` 直接成立，和 JSON/数据库里的字符串无缝互转。

核心数据类（全部 `@dataclass`，纯 JSON 可序列化）：

- `SkillResult` — 一次技能调用的结果（`name/output/side_effect`），`side_effect=True` 表示产生了外部副作用（如建报告）。
- `AgentTrace(agent, action, detail)` — 一条执行痕迹，三个字符串，最终拼成管理端可读的时间线。

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "PendingReport":
    """从仓储层返回的报告字典重建 PendingReport(统一各处重复的转换逻辑)。"""
    return cls(id=data["id"], session_id=data["session_id"], ...,
               risk_level=RiskLevel(data["risk_level"]),
               status=ReportStatus(data["status"]), ...)
```

- `RuntimeEvent` + `sse_event` 属性 — 把内部事件类型映射为 SSE 前端事件名（`RUN_COMPLETED → "done"`），流式输出的协议适配就在这一个小字典里。
- `ChatResponse` — 一次对话的最终产物；`StreamEvent` — SSE 事件的信封。



**学习要点**：领域模型层要保持「零依赖」（只依赖标准库），它决定了整个系统的公共语言；`str+Enum` 是做配置类枚举的惯用法。

### 1.3 app/entities.py — ORM 实体（19 张表）

SQLAlchemy 2.0 声明式实体，和 `models.py` 的关系是：models 是「怎么说」，entities 是「怎么存」。

代表表：`ChatSession`（会话，含 `owner_user_public_id` 归属）、`ChatMessage`、`SessionMemory`（滚动记忆摘要）、`AuthUser`/`AuthSession`（口令与令牌）、`PsychologicalReport`（风险报告）、`RiskCase`+`CaseNote`（个案）、`KnowledgeChunk`（知识切块）、`ToolJob`/`ToolAuditRecord`/`DeadLetterRecord`（工具任务/审计/死信）、`ExcelRecord`/`AlertRecord`（副作用记录）、`AgentPrivateMemory`（Agent 私有记忆）、`AgentModelProfile`（每 Agent 模型档案）、`UserMemoryFact`（L2 用户事实，SCD-2 有效期版本，见 9.5）、`AdminAuditLog`（管理端审计）。

注意两个细节：

- 时间字段统一用 `now()` 工厂生成不带时区的 UTC——和历史行为保持一致（数据库里已存的是 naive 时间）。
- `KnowledgeChunk` 同时存 `content`（原文）、`metadata_json`（元数据）、`embedding_json`（本地降级用的向量）——一个表兼容「有无向量库」两种部署。

### 1.4 app/database.py — 引擎与会话工厂（支持 SQLite / MySQL 双后端）

`DATABASE_URL` 形如 `mysql+pymysql://user:pass@host:3306/aegis?charset=utf8mb4` 时走 MySQL：pymysql 驱动、`pool_recycle=3600` 防闲置断连、首次启动自动 `CREATE DATABASE IF NOT EXISTS`（utf8mb4）。SQLite 则是零依赖本地模式，两套后端共享同一套 ORM 实体。

```python
def _engine_kwargs(database_url: str) -> dict:
    kwargs = {"pool_pre_ping": True}          # 取连接前先 ping,自动剔除断连
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}  # 允许后台线程共用
    return kwargs

def build_session_factory(runtime_settings=None):
    return sessionmaker(bind=build_engine(runtime_settings), autoflush=False, autocommit=False)
```

-   工厂而非模块级单例  ：测试要用独立的 tmp 数据库，每个调用方自建 engine。
- `create_schema()` 里 `from app import entities` 是惰性导入——先注册全部 ORM 实体到 `Base.metadata`，再 `create_all`。
- `migrate_legacy_schema()`：对旧库手写 `ALTER TABLE`/`CREATE TABLE` 补列补表，保证升级不丢数据。它与 entities.py 是两份 schema 真相，是已知的遗留债（见 REFACTORING.md 第 10 节）。
- `readiness_check()` 只做 `SELECT 1`，是 `/api/readiness` 的依据——和 `/api/health`（进程活着）区分。



**学习要点**：SQLite 要跨线程必须 `check_same_thread=False`（本项目有后台工具 worker 线程）；「建表」与「迁移」是两件事，小项目手写迁移能用，正规项目上 Alembic。

#### 动手试一试：让「配置即数据」跑给你看

把下面内容存为项目根目录下的 `try_station1.py`（后续各站示例同理，都要放在项目根目录运行，`app` 包才可导入），执行 `python try_station1.py`：

```python
from app.config import Settings, get_settings
from app.models import Intent, RiskLevel

s = Settings()                      # 不写 .env 也能实例化:每个字段都有安全默认值
print(s.ai_provider, s.database_url, s.agent_runtime)
print(s.resolve_path("knowledge"))  # 相对路径 → 绝对路径(相对项目根)

print(RiskLevel.HIGH == "high")     # str+Enum:与 JSON/数据库里的字符串无缝比较
print(Intent("risk"))               # 从字符串反构枚举
print(get_settings() is get_settings())  # @lru_cache:全进程只有一份配置
```

预期输出（路径随机器不同而不同）：

```text
mock sqlite:///data/aegis.sqlite autonomous
D:\PythonProject\aegis-psych-agent\knowledge
True
Intent.RISK
True
```

#### 常见易错点

- **以为必须写 `.env` 才能跑**：`Settings` 每个字段都有安全默认值，`.env` 只用来覆盖默认值。同时记住 4.3 强调的三层区别：`Settings` 代码默认 ≠ `.env.example` 建议值 ≠ 你本机的 `.env`。
- **把领域模型和 ORM 实体混为一谈**：`models.py` 是「怎么说」（零依赖、可单独 import），`entities.py` 是「怎么存」（依赖 SQLAlchemy）。业务代码只应 import 前者。
- **自建 engine 忘了 `check_same_thread=False`**：后台工具 worker 线程与请求线程共用 SQLite 连接，不加这条会偶发 `SQLite objects created in a thread...` 报错。
- **改了配置不生效**：`get_settings()` 带 `@lru_cache`，进程内只读一次；改 `.env` 要重启服务，测试里则应显式传 `Settings(...)` 覆盖（tests 正是这么做的）。

#### 练习

1. 给 `Settings` 加一个字段 `demo_greeting: str = "hello"`，在 `.env` 写 `DEMO_GREETING=hi` 验证覆盖生效。（验证：`python -c "from app.config import get_settings; print(get_settings().demo_greeting)"`）
2. 打开 `data/aegis.sqlite`（任意 SQLite 工具），数一数有多少张表，与 `entities.py` 里 19 个 `Base` 子类一一对应。
3. 思考题：如果 `models.py` import 了 SQLAlchemy，「测试可以单独 import 它」会失去什么？（写下答案，与 1.2 的学习要点对照）

***

<a id="station-2"></a>

## 第 2 站 安全底座：core/

地基立好后，先写「任何功能上线前必须有的东西」：谁能用（认证）、哪些字段不能见（脱敏）、请求会不会打爆（限流）。

### 2.1 core/auth.py — 口令与会话

```python
def make_password_hash(password: str, salt: str | None = None) -> tuple[str, str]:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return salt_value, digest.hex()

def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = make_password_hash(password, salt)
    return hmac.compare_digest(digest, expected_hash)   # 恒时比较,防时序侧信道
```

- PBKDF2-HMAC-SHA256、12 万轮迭代、随机盐——不引入 bcrypt 依赖也能达到及格线的口令存储。
- `verify_password` 用 `hmac.compare_digest` 而非 `==`：避免「比较耗时差异」泄露前缀。
- 会话令牌 `secrets.token_urlsafe(32)`；`AuthPrincipal`（frozen dataclass）是「当前登录者」的轻量表示，贯穿所有路由依赖。
- `random_id(prefix)` 生成 `usr-xxx`/`audit-xxx` 这类可读 ID——日志里一眼看懂类型。

### 2.2 core/privacy.py — 脱敏与输入消毒

```python
SENSITIVE_PAYLOAD_FIELDS = {"api_key", "email", "message", "password", "phone",
                            "precise_location", "session_token", "student_id", "student_name", "token"}
INTERNAL_RESPONSE_TERMS = ("report_id", "risk-", "内部评分", "confidence")
```

- `redact_payload(payload, fields)` 递归把敏感字段替换为 `"[redacted]"`，返回 `(脱敏后, 命中字段列表)`——命中列表用于审计记录「哪些字段被藏了」。
- `contains_internal_response_leak(text)`：安全复核的关键——任何要发给学生的回复，先过这个函数——只要包含 `report_id`/`risk-`/`confidence` 等内部词汇，就会被 RiskGuardian 打回重写。
- `sanitize_user_input(text)`：进入模型前的预处理——压缩空白，并把「手机号/电话/身份证」替换成「联系方式/证件」，降低模型诱导输出个人敏感信息的概率。



**学习要点**：心理场景的隐私是合规底线；脱敏要同时覆盖「存储侧」（payload 进审计表之前）和「输出侧」（回复发给用户之前）两个面。

### 2.3 core/runtime_services.py — RuntimeServices（限流与锁）

```python
class RuntimeServices:
    def __init__(self, settings: Settings):
        ...
        if settings.redis_url.strip():
            try:
                import redis
                self.redis_client = redis.Redis.from_url(...)
                self.redis_client.ping()          # 连不上立即降级
                self._redis_available = True
            except Exception:
                self.redis_client = None          # 本地无 Redis 也能跑
```

- `check_rate_limit(key, limit, window)`：Redis `INCR+EXPIRE` 计数窗口；无 Redis 时用进程内 `dict[str, list[float]]` 模拟——同一个接口两种实现，语义一致——这是「可选依赖」的标准写法。
- `lock(name, ttl)` 上下文管理器：Redis `SET NX EX`；本地退化为过期时间表。用在「手动跑工具任务」接口上，防止两个管理员同时触发批处理。

### 2.4 core/utils.py — 统一工具函数（去重产物）

初版里 `_loads`（JSON 容错解析）在 4 个文件各有一份、`_now` 也有 4 份——而且有两种时区语义（带/不带 tzinfo）。重构时按原语义分别收编：

```python
def loads_dict(value: str) -> dict[str, Any]: ...   # 必须是 dict,否则 {}(队列/记录场景)
def loads_or(raw: str, default: Any) -> Any: ...    # 失败给默认值(仓储场景)
def now_utc() -> datetime: ...                      # aware UTC(服务层新代码)
def now_utc_naive() -> datetime: ...                # naive UTC(与库中历史数据一致)
```



**学习要点**：去重前先确认「真的相同」。两份 `_now` 语义不同（naive/aware），强行统一会改变数据库写入行为——正确做法是命名出两种语义，让调用点各取所需。

### 2.5 core/network.py — 出站 URL 安全校验（SSRF 防护）

服务端一切对外 HTTP 调用（当前唯一消费者是第 5 站的 `RiskQloraClient`，第十四轮 QLoRA 安全集成引入）共享同一道闸门：

```python
def validate_public_http_url(value: str) -> ParseResult:
    """校验出站 URL 及其 DNS 解析结果:仅允许 http(s) 公网地址,
    拒绝 localhost、环回、私有、保留等非公网目标;重定向跟随前复检。"""
```

两个关键设计：其一，不仅检查 URL 字面，还解析主机并对 DNS 返回的**每一个地址**做公网校验——防「域名指向内网 IP」的 DNS rebinding；其二，`safe_urlopen` 在每次打开连接与**每次重定向**时都复用同一道闸门，而不是只在入口查一次。它与 2.2 的脱敏是同一思想的两个面：2.2 防「坏内容进来」，这里防「数据出去」。

#### 动手试一试：脱敏、消毒与恒时比较

```python
# try_station2.py —— python try_station2.py
from app.core.privacy import redact_payload, sanitize_user_input, contains_internal_response_leak
from app.core.auth import make_password_hash, verify_password

out, hit = redact_payload({"student_name": "张三", "phone": "13800000000", "note": "无"},
                          {"student_name", "phone"})
print(out, hit)
# {'student_name': '[redacted]', 'phone': '[redacted]', 'note': '无'} ['phone', 'student_name']

print(sanitize_user_input("请打我电话 13800000000，  我   很难受"))
# 请打我联系方式 13800000000， 我 很难受   ← 电话→「联系方式」,空白被压缩

print(contains_internal_response_leak("你的报告编号 risk-abc123 已生成"))  # True → 要打回重写
print(contains_internal_response_leak("听起来真的很不容易，先一起做几次深呼吸好吗？"))  # False → 放行

salt, digest = make_password_hash("admin123!")
print(verify_password("admin123!", salt, digest), verify_password("wrong!", salt, digest))
# True False
```

#### 常见易错点

- **用 `==` 比较口令摘要**：字符串 `==` 在首个不同字符处提前返回，「比较耗时差异」可被侧信道利用；必须用 `hmac.compare_digest` 恒时比较。
- **脱敏只做存储侧**：审计表里脱了敏，不代表回复里没漏——输出侧还有 `contains_internal_response_leak` 把关，两面缺一不可。
- **混淆 `now_utc` 与 `now_utc_naive`**：两者语义不同（带/不带时区），强行统一会改变数据库写入行为；与库中历史数据交互时用 naive 版本。
- **把 Redis 当功能依赖**：`RuntimeServices` 连不上 Redis 会**立即降级**为进程内实现；单机演示「没装 Redis」不是报错原因，别顺着这条线排错。

#### 练习

1. 把 `home_address` 加入脱敏字段集合，写一个单测验证 `redact_payload` 命中它（参照 `tests/` 里既有断言风格）。
2. 构造一句含「手机号 + 连续空格」的消息，对比 `sanitize_user_input` 前后差异，解释为什么要在进模型前做。
3. 思考题：`AuthPrincipal` 为什么用 frozen dataclass？如果它是可变的，路由中途被改写角色会发生什么？（对照 1.2 的「不可变」思想）

***

<a id="station-3"></a>

## 第 3 站 assessment.py — 确定性风险评估



**为什么在 LLM 之前写它**：这是全系统最重要的安全组件，而且完全不依赖模型——mock 模式下它就是「大脑」的安全部分。

```python
HIGH_TERMS = ["自杀", "轻生", "不想活", "结束生命", "suicide", "kill myself",
              "一了百了", "离开这个世界", "结束这一切", "结束自己的生命",
              "活下去的理由", "活下去的力气", "不再醒来", "永远睡过去",
              "活着多余", "解脱", "死了算了", "做傻事"]   # 后 12 个为隐喻式表达
THIRD_PERSON_MARKERS = ["新闻", "电影", "朋友", "论文", "听说", "别人", ...]  # 语境保护,防误升级
MEDIUM_TERMS = ["伤害自己", "自残", "崩溃", "撑不住", "绝望", "panic", "hopeless"]
DEPRESSED_TERMS = ["抑郁", "低落", "难过", "无助", "depress"]
ANXIETY_TERMS = ["焦虑", "压力", "考试", "睡不着", "失眠", "panic", "anxious"]
```

词表按「显式高危 → 隐喻式高危」两层设计：后 12 个词用于弥补对「一了百了」「解脱」等隐喻式自杀意念的漏判；`THIRD_PERSON_MARKERS` 则在命中高危词后检查语境——「新闻里有人轻生」「写自杀预防论文」这类提及**他人/虚构情境**的表达不升级为自身风险（规则引擎没有指代消解能力，用保守启发式先降误报，自身语境的隐喻表达交给 LLM 通道补召回）。

`assess_message(text) -> AssessmentResult` 是纯函数：先匹配 HIGH（命中即 `risk_level=HIGH, confidence=0.95, report_eligible=True, escalation_policy="create_pending_report_and_require_admin_review"`），再 MEDIUM，再按抑郁/焦虑词给出 LOW，最后兜底「普通陪伴」。

返回的 `AssessmentResult` 不只是等级，还带处置策略（`recommended_stance`/`escalation_policy`）：

- HIGH → `immediate_safety`：本地安全模板回复 + 建待审报告。
- MEDIUM → `stabilize_and_refer`：稳定练习 + 转介指引。
- LOW → 倾听陪伴。

`as_skill_output()` 把结果转成扁平 dict，供技能层透传。



**学习要点（风险双通道）**：`assess_message` 是规则通道；`RiskGuardianAgent` 会再用可选模型通道复核——通用 LLM 或开启 `RISK_QLORA_ENABLED` 后的 v9 QLoRA 隔离服务，严格 JSON、8s 短超时；两通道取并集，任一判 high 即 high；模型失败/超时/mock 一律回退纯规则，输出 `risk_channels` 溯源。

- **第十四轮真实 QLoRA 验收**：v9 使用新提示词契约 v2，在冻结 stress 87 条上八门槛全部通过：FPR 0、隐喻新增 +6、medium 召回 0.88、第三人称准确率 0.82、P95 1.37s。推理服务脚本位于 `D:\AegisTraining\training\scripts\serve_risk_qlora.py`，路径可通过 `AEGIS_TRAINING_ROOT` / `AEGIS_QLORA_MODEL_DIR` 覆盖。
- **第十一轮历史双路径验证**：150 条语料的 baseline/stub/GLM 数字仍保留在 `data/eval/risk_dual_path.json`，只代表历史测试替身，不代表当前 v9 生产模型。
- `HIGH_TERMS` 是单一事实来源——`autonomous/board.py` 的 `hard_high_risk()` 也引用它，改关键词只改一处。
- 规则评估可解释（命中了哪个词一目了然）、可单测、零成本零延迟。代价是召回有限，隐喻式高危由模型通道补强。

#### 动手试一试：三条消息看懂规则引擎

```python
# try_station3.py —— python try_station3.py
from app.assessment import assess_message

for text in ["我最近睡不着，压力好大",
             "最近感觉活着多余，做什么都没意思",
             "新闻里有人轻生，太让人难过了"]:
    r = assess_message(text)
    print(r.risk_level.value, "|", r.recommended_stance, "|", r.matched_indicators)
```

预期输出：

```text
low | supportive_planning | ['压力', '睡不着']
high | immediate_safety | ['活着多余']
low | supportive_planning | ['高危词（轻生）出现在提及他人/虚构情境的语境，判定为非自身风险，不升级']
```

第三行就是第三人称保护的现场：词命中了，但语境不是自身，不升级；「活着多余」这类隐喻表达则被新增的隐喻词表抓到。两者的分工（规则兜显式、LLM 通道补隐喻、第三人称防误报）正是双通道设计的动机。

#### 常见易错点

- **往 `HIGH_TERMS` 加词后只手动试两句就上线**：正确流程是跑 `python -m pytest tests -q` + `python -m app.evaluation.harness.runner --suite risk`，看高风险召回与误报（FPR）有没有同时变坏——评测护栏就是为这一刻准备的（4.5 第 3 步）。
- **在规则层里调 LLM**：`assess_message` 是纯函数、零延迟、可单测，这是它敢当「单一事实来源」的资本；任何模型调用都只能出现在第二通道。
- **把「第三人称不升级」当漏判**：这是刻意的保守启发式（防把「同学轻生的新闻」误升级），自身语境的隐喻由 LLM 通道兜底——两条通道职责不同，别在规则层复刻 LLM 的能力。
- **忽略返回值里的处置策略**：只拿 `risk_level` 自己 if-else，会丢掉 `recommended_stance` / `escalation_policy` 这层「风险 → 动作」映射，下游会写出一堆平行逻辑。

#### 练习

1. 加一个你自己想到的隐喻式高危词，先预测它对语料的影响，再跑 `--suite risk` 验证预测（召回与 FPR 是否同向变化）。
2. 找一句会被 MEDIUM 命中的话，打印完整 `AssessmentResult`，解释 `rationale`、`summary` 与 `matched_indicators` 的关系。
3. 思考题：HIGH 的 `escalation_policy` 为什么叫 `create_pending_report_and_require_admin_review`？它对应第 11 站闭环里的哪条链路？

***

<a id="station-4"></a>

## 第 4 站 skills.py — 技能注册表



**设计思路**：Agent 需要的能力（评估风险/检索知识/稳定练习/建报告）统一注册成 `SkillSpec`，而不是散落在各 Agent 里：

```python
@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    side_effect: bool                                  # 是否有外部副作用
    handler: Callable[..., SkillResult]

    def openai_schema(self) -> dict[str, Any]: ...     # 直接导出为 OpenAI function-calling 工具描述
```

`SkillRegistry.__init__` 注册 4 个内置技能：

| 技能                      | 副作用   | 实现                                                 |
| ----------------------- | ----- | -------------------------------------------------- |
| `assess_risk`           | 否     | 调 `assess_message`（第 3 站）                          |
| `search_knowledge`      | 否     | 优先用注入的 `knowledge_search`（真 RAG）；无注入时退化为关键词计分的本地检索 |
| `grounding_exercise`    | 否     | 返回固定三步「60 秒稳定练习」                                   |
| `create_pending_report` |   是   | 构造 `PendingReport` 并通过 `report_sink` 落库            |

注意构造参数的依赖注入：

```python
SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge, settings=settings)
#                    ↑目录            ↑报告落库回调        ↑检索回调              ↑自动蒸馏配置
```

技能层不 import 仓储，而是接收函数——测试时可以塞假函数，这就是它可单测的原因。

另一条线是**人工策展 Skill**：当前仓库有 7 个 `skills/*/SKILL.md` 文档，带 frontmatter。`response_skill_names(intent, risk, text)` 先按规则给出白名单（高风险 → 安全计划 + 交接摘要；命中「失眠」→ 睡眠支持……），`standard_context(names)` 再拼成提示词注入。这是「用文档约束模型输出结构」的轻量做法。

### 4.1 Skill 自动蒸馏闭环（第十三轮）

第十三轮在“注册式执行 Skill”和“人工策展 Skill”外增加第三层：**自动 Skill**。它的目标不是让模型随意改写业务逻辑，而是把被反复使用的、已经受规则白名单约束的基础 Skill 组合沉淀为一份可检查的 `SKILL.md`。

```text
规则/Function Calling 选出基础 Skill
    ↓
SkillUsageObserver 记录 intent|risk|sorted-manual-skill-names
    ↓（同一模式默认第 3 次出现）
_distill_skill() 写入 skills/auto/<slug>/SKILL.md
    ↓
重载标准 Skill 索引；后续相同模式自动追加该 auto Skill
```

关键实现点：

- 使用计数持久化为单个 JSON 对象：`data/skill-usage.json`；它记录的是组合模式的出现次数，而不是逐行日志。
- 自动 Skill frontmatter 带 `origin: auto`、触发意图/风险和包含的基础 Skill；正文是确定性模板，重复组合会获得相同的融合约束，而不是让模型自由生成未审查建议。
- 自动 Skill 会参与**后续**的匹配；当前触发蒸馏的那一轮不会把刚生成的名称回填到当次白名单。
- `record_skill_usage()` 会先过滤 `origin=auto` 的 Skill，因此 auto Skill 不会触发下一层 auto Skill，避免递归膨胀。
- 当前实现达到阈值后会直接写文件、重载并参与后续注入；**尚未实现**人工审核状态、管理员启停、版本回滚或审计工作台。正式部署应限制 `skills/auto/` 写权限、纳入版本控制，并在启用前增加审核门禁。

`_split_frontmatter` 手写解析 YAML 头——不引入 yaml 依赖的取舍（知识文档的 frontmatter 解析在 `rag/chunking.py`，两者格式相似但容错策略不同：技能解析遇到坏文档直接跳过，知识解析静默忽略坏行）。



**学习要点**：`side_effect` 标记让「哪些技能会改变世界」一眼可见，后续审计/评测都依赖它；把 LLM 工具描述（`openai_schema`）作为技能的一等公民——第五轮已接真 function calling（`agents/skill_selection.py`）：规则先定白名单（安全边界不变），模型在白名单内自主挑选技能与顺序，失败/幻觉名回退整个白名单。

#### 动手试一试：注册、白名单与 Function Calling 描述

```python
# try_station4.py —— python try_station4.py
from pathlib import Path
from app.models import Intent, RiskLevel
from app.skills import SkillRegistry
import json

# 依赖注入:两个回调都给假的——技能层可脱离数据库单测
reg = SkillRegistry(Path("knowledge"),
                    report_sink=lambda r: print("[假落库]", r.id),
                    knowledge_search=lambda q: [{"content": "先做几次深呼吸"}])

out = reg.get("grounding_exercise").handler("我有点撑不住")
print(out.name, out.side_effect, list(out.output))
# grounding_exercise False ['title', 'steps']

# 同一份 SkillSpec 可直接导出为 OpenAI function-calling 工具描述
print(json.dumps(reg.get("assess_risk").openai_schema(), ensure_ascii=False)[:80], "...")

# 规则白名单:意图 + 风险 + 文本共同决定注入哪些策展 Skill
print(reg.response_skill_names(Intent.RISK, RiskLevel.HIGH, "我不想活了"))
# ['supportive_response_baseline', 'high_risk_safety_plan', 'counselor_handoff_summary']
print(reg.response_skill_names(Intent.COUNSELING, RiskLevel.LOW, "我最近睡不着"))
# ['supportive_response_baseline', 'sleep_routine_support']
```

#### 常见易错点

- **传字符串而不是枚举**：`response_skill_names("risk", "high", ...)` 不报错，但白名单永远只剩 `['supportive_response_baseline']`——函数内部用 `is` 比较枚举，字符串与枚举恒不相等。务必传 `Intent.RISK` / `RiskLevel.HIGH`。
- **在技能里 import 仓储**：技能层只认回调（`report_sink` / `knowledge_search`），一旦 import 就失去了可单测性——这是本项目的纪律，不是巧合。
- **把 `side_effect=True` 的技能当纯查询用**：`create_pending_report` 会真的改变世界（建报告）；编排层与审计都依赖这个标记区分「读」与「写」。
- **开着自动蒸馏做基线评测**：`SKILL_DISTILL_ENABLED=true` 时重复模式会写 `skills/auto/` 与 `data/skill-usage.json`，污染下一次基线（4.9 第 5 条）。做可复现评测先关掉或隔离输出目录。

#### 练习

1. 注册一个自定义技能 `suggest_music`（无副作用），导出并完整打印它的 OpenAI schema。
2. 用 `Intent.COMPANION / RISK` × `RiskLevel.LOW / HIGH` 四种组合调用 `response_skill_names`，归纳出白名单矩阵（哪个意图 + 哪个风险 → 哪些技能）。
3. 对比 `skills/` 下人工策展 SKILL.md 与 `skills/auto/` 的 frontmatter 差异（`origin` 字段），解释为什么要防止 auto Skill 触发下一层蒸馏。

***

<a id="station-5"></a>

## 第 5 站 llm/ — 模型后端

### 5.1 llm/client.py — 协议 + 三实现 + 工厂

```python
class LLMClient(Protocol):
    provider: str
    model: str
    def status(self) -> dict: ...
    def generate_support_reply(self, context: LLMContext) -> str | None: ...
    def stream_support_reply(self, context, on_token) -> str | None: ...      # 真流式直播
    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None: ...
    def assess_risk(self, text: str) -> dict | None: ...                      # 风险双通道
    def chat_with_tools(self, system, user, tools) -> list[str] | None: ...   # Function Calling
    def judge_reply(self, message, reply) -> dict | None: ...                 # LLM-as-Judge
```

`LLMContext` 是喂给模型的结构化上下文包：用户消息、意图、风险等级、**L2 当前有效用户事实、L3 会话摘要、L4 最近原话窗口**、知识片段、稳定练习、技能约束——回复生成所需的一切都显式传入，模型不自己「想」。

协议从最初的「一问一答」长成了多通道客户端：回复生成（阻塞）、回复直播（流式）、查询改写（RAG）、风险复核（双通道）、技能选择（FC）、质量评审（Judge）。新增通道全部遵守同一条铁律：失败/超时/mock 返回 None，调用方优雅降级——这正是全系统「LLM 永远不是安全关键路径」的落点。

三个实现（风险通道另有独立 QLoRA 实现）：

- `MockLLMClient`：方法都返回 `None`（None 就代表「请走本地模板兜底」）。这让无 key 环境下整条链路（含高风险处置）照常可测。测试中还派生了 `MetaphorAwareStubClient`（`tests/test_risk_dual_channel.py`），模拟 LLM judge 的隐喻检测行为，用于第十一轮历史双路径验证。
- `OpenAICompatibleClient`：`client.py` 用 urllib 裸调 `{base_url}/chat/completions`，支持智谱等 OpenAI 兼容端点的 `thinking:{"type":"disabled"}` 参数（默认关闭深度思考，大幅降低延迟）。第六轮起支持性回复使用独立温度 `LLM_SUPPORT_TEMPERATURE`（默认 `0.6`，偏口语更像真人；风险评估/改写/评审仍固定 `0.0`）。
- `OllamaClient`：调 `/api/chat`，本地模型零成本；仅负责通用 Ollama 通道。
- `RiskQloraClient`：`RISK_QLORA_ENABLED=true` 时由 `PsychOrchestrator` 注入 RiskGuardian，调用隔离 Transformers 服务的 v9 QLoRA 模型；URL 强制公网 http(s)（经 `core/network.py` 校验，拒绝 localhost、环回、私有和保留地址——本地 `127.0.0.1:8301` 服务仅供独立 smoke test，见 4.2），服务失败/超时/非法 JSON 返回 `None`，回退规则。

`build_llm_client(settings)` 负责通用客户端装配；RiskGuardian 的 QLoRA 替换由编排器配置开关控制。

**风险 judge prompt**（`RISK_ASSESS_SYSTEM_PROMPT`，`app/llm/client.py`；训练侧同源 `data_contract.py`）：LLM 通道的核心提示词，判定 high/medium/low 三档。当前契约 v2 已移除宽泛的「不配」「活着多余」示例，保留明确指向不存在/停止生存的表达，并标注第三人称/虚构语境不视为自身 high（"新闻里有人轻生/写论文提到自杀/朋友直播自杀"）。输出严格 JSON（`{"risk_level": "...", "reason": "..."}`），`_parse_risk_json()` 容忍代码块包裹与前后杂文。

### 5.2 llm/prompts.py — 提示词模板

系统提示词是安全边界的一部分，值得整段读：

```python
system = (
    "你是校园心理支持产品中的咨询回复生成器。"
    "只能提供支持性倾听、问题澄清、自助练习和求助准备；不能诊断，不能承诺保密，不能替代专业咨询。"
    "高风险安全分流由上游规则处理，你不得输出内部风险分数、报告编号或后台审计细节。"
    "回复要使用简体中文，温和、具体、简洁。"
)
```

四句话分别划定：能力边界 / 禁止事项 / 与规则层的分工 / 输出风格。用户消息模板把 **L2 当前有效状态、L3 摘要、L4 原话**、意图、风险、知识、练习、技能逐块拼装，并显式要求“L2 优先，和摘要冲突的旧状态视为过期”；上下文工程就是把「该给的信息」按结构喂给模型。

第六轮把提示词从「机器人模板」改成「真人陪伴风格」：不再自称「咨询回复生成器」，改为「你是 Aegis，校园心理支持助手」；指令从「先共情→1-3步骤→开放问题」改成灵活对话指导（短句口语、长度匹配用户消息、一次最多一个问题、建议最多两条且只在合适时给）。历史摘要/知识/练习字段仍动态注入，但加了防泄漏指示——禁止把「用户提到/系统回应重点」等内部标签原文放进回复里。



**学习要点**：提示词放独立文件便于审计；`prompts.py` 与 `client.py` 互相只用类型注解引用（`TYPE_CHECKING`），不产生运行时循环依赖。

#### 动手试一试：mock 客户端与「None 即兜底」

```python
# try_station5.py —— python try_station5.py
from app.config import get_settings
from app.llm.client import build_llm_client, LLMContext
from app.models import Intent, RiskLevel

client = build_llm_client(get_settings())   # 默认 AI_PROVIDER=mock
print(type(client).__name__, client.status())
# MockLLMClient {'provider': 'mock', ...}

ctx = LLMContext(message="我睡不着", intent=Intent.COUNSELING, risk_level=RiskLevel.LOW,
                 memory_summary="", knowledge_snippets=[], grounding_steps=[])
print(client.generate_support_reply(ctx))   # None ← None 就是「请走本地模板兜底」的信号
```

`LLMContext` 就是「上下文工程」的形状：模型生成回复所需的一切（消息、意图、风险、L2 事实 / L3 摘要 / L4 原话、知识片段、练习、技能约束）都显式递进来，模型不自己「想」。

#### 常见易错点

- **把 `None` 当异常处理**：全协议约定「失败 / 超时 / mock → 返回 None」，调用方据此走模板兜底；把 None 抛成异常反而破坏了降级链。
- **两个风险开关混为一谈**：`build_llm_client` 只按 `AI_PROVIDER` 装配**通用**客户端；风险通道的 QLoRA 替换由 `PsychOrchestrator` 按 `RISK_QLORA_ENABLED` 另行注入——一个是「大脑」，一个是「风险复核员」。
- **以为温度只有一个**：支持性回复用 `LLM_SUPPORT_TEMPERATURE`（默认 0.6，偏口语更像真人），风险评估 / 改写 / 评审固定 0.0（要稳定）；调错对象会同时伤安全与质量。
- **随手改系统提示词**：`prompts.py` 的四句话划定了「能力边界 / 禁止事项 / 分工 / 风格」，改动等于改安全边界，改完必须回归评测（第 13 站）。

#### 练习

1. 实现一个 `EchoLLMClient`（只实现 `generate_support_reply` 返回固定句子，其余方法返回 None），在第 8 站的最小全链路里替换 mock，观察回复变化。
2. 对比 `MockLLMClient().status()` 与 `OpenAICompatibleClient` 的 status 字段差异，想清楚「status 为什么也是协议的一部分」（管理端 agent-status 页要用它）。
3. 阅读 `RISK_ASSESS_SYSTEM_PROMPT`，找出「第三人称 / 虚构语境不视为自身 high」的提示词依据——它与第 3 站的规则启发式如何互补？

***

<a id="station-6"></a>

## 第 6 站 agents/classic.py — 六个单轮智能体

这一层是「每个角色做一件小事」，全部是无状态类（除 Counselor 持有 registry/llm）：

| Agent               | 方法                                         | 职责                                                             |
| ------------------- | ------------------------------------------ | -------------------------------------------------------------- |
| `MemoryAgent`       | `load / update`                            | 加载 L2 当前事实、L3 摘要和 L4 原话窗口；回复后更新 L3 并抽取 L2 事实 |
| `RiskGuardianAgent` | `assess / create_report`                   | 调 assess\_risk 技能（规则∪LLM 双通道取并集，详见第 3 站）；HIGH 时建待审报告       |
| `LeadAgent`         | `route`                                    | 关键词路由：高危→RISK；资料词→RESEARCH；咨询词或 MEDIUM→COUNSELING；否则 COMPANION |
| `KnowledgeAgent`    | `search / rewrite_query`                   | LLM 改写检索词（失败退化原文前 60 字）+ 检索                                    |
| `CounselorAgent`    | `grounding / compose_plan / finalize_plan` | 组装 ResponsePlan 并生成最终回复                                        |
| `CompanionAgent`    | —                                          | 空类，低风险陪伴的「占位角色」（回复实际复用 Counselor 的模板路径）                        |

重点看 `CounselorAgent.finalize_plan` 的分层兜底：

```python
def finalize_plan(self, plan: ResponsePlan) -> tuple[str, AgentTrace]:
    fallback = self._fallback_answer(...)          # ① 先无条件构造模板回复
    if risk_level is RiskLevel.HIGH:
        return fallback, ...                       # ② 高风险:永远用模板,不给模型机会
    context = LLMContext(...)                      # ③ 低/中风险:组装上下文问模型
    generated = self.llm_client.generate_support_reply(context)
    if generated:
        return generated.strip(), ...              # ④ 模型可用:用生成结果
    return fallback, ...                           # ⑤ 模型不可用/mock:模板兜底
```

`_fallback_answer` 的模板按风险分三档开头（高危段直接给出「联系可信任的人/心理中心/紧急服务」），再拼 L3 摘要回显、稳定练习、知识首条、意图化收尾——这就是 mock 模式下学生看到的回复来源。注意边界：L2/L4 已传入真实 LLM Prompt，但当前模板兜底主要读取 L3 摘要；因此 L2/L4 对“贴着原话、避免引用过期状态”的改善主要体现于真实 LLM 可用的路径。



**学习要点**：每个方法都返回 `AgentTrace`——「做事」与「留痕」是绑定的；安全关键路径（HIGH）与模型路径在 ② 处显式分流，这是「规则优先」哲学的落点。

#### 动手试一试：亲手路由一次

```python
# try_station6.py —— python try_station6.py
from app.agents.classic import LeadAgent
from app.models import RiskLevel

agent = LeadAgent()
for text, risk in [("我不想活了", RiskLevel.HIGH),
                   ("帮我查一下减压的方法", RiskLevel.LOW),
                   ("最近总是和室友闹矛盾", RiskLevel.LOW)]:
    intent, trace = agent.route(text, risk)
    print(intent.value, "|", trace.agent, trace.action, "|", trace.detail)
```

预期输出：

```text
risk | LeadAgent route | intent=risk, risk=high
research | LeadAgent route | intent=research, risk=low
companion | LeadAgent route | intent=companion, risk=low
```

`trace` 的 `agent/action/detail` 三元组就是管理端 trace 时间线里的一行——「做事」与「留痕」在这一个返回值里完成绑定。

#### 常见易错点

- **给 `route` 传字符串当风险等级**：与第 4 站同款坑——`risk_level is RiskLevel.HIGH` 对字符串恒为 False，高危消息会被当普通消息路由。
- **以为 `CompanionAgent`「没实现」是偷懒**：它是刻意占位——低风险陪伴复用 Counselor 的模板路径；保留类名是为了 trace 里角色可读，也为未来独立化留位。
- **只看 `finalize_plan` 的成功分支**：读这段代码的正确姿势是盯住「高风险」与「模型不可用」两条路怎么走（②⑤ 处）——分层兜底才是安全哲学的落点。
- **把「companion 跳过检索」顺手优化掉**：这是有序流水线里显式写的短路（普通聊天不必检索），有对应单测守护；自己加逻辑前先跑 `python -m pytest tests -q`。

#### 练习

1. 往 `LeadAgent` 的咨询词表加一个你常用的词，用上面的脚本验证路由变化，再跑全量测试看是否有测试守护路由边界。
2. 在第 8 站的最小全链路里分别用 HIGH 与 LOW 消息触发 `_fallback_answer`，逐段对照其拼装顺序（高危开头 / 摘要回显 / 练习 / 知识 / 收尾）。
3. 思考题：为什么每个方法都返回 `AgentTrace`，而不是在方法内部自己写日志？（提示：trace 的归属、排序与落库时机由谁决定？）

***

<a id="station-7"></a>

## 第 7 站 autonomous/ — 自治黑板协作（项目的心脏）

单轮 Agent 只是零件。真正的多 Agent 协作在这一站：六个自治 Agent 围绕只增不删的黑板块认领任务、发布产物、互相评审。

### 7.1 autonomous/events.py — 纯数据协议

先定义「协作的语言」：

- `AgentEventType`：TURN\_STARTED / TASK\_CREATED / TASK\_CLAIMED / ARTIFACT\_PUBLISHED / SAFETY\_OVERRIDE / REVISION\_REQUESTED / FINAL\_ACCEPTED / BUDGET\_EXHAUSTED …
- `AgentTask`：带 `required_capabilities`（能力要求）、`priority`、`metadata`。
- `AgentArtifact`：`(owner, kind, payload, confidence, task_id, metadata)`——一切中间产物，kind 取值：`memory`/`intent`/`risk`/`context`/`response_proposal`/`safety_review`/`pending_report`。
- `CollaborationBlackboard`：核心结构，`turn_id/session_id/user_input` + `tasks/artifacts/messages/events` 四个列表。

```python
def append_artifact(self, artifact: AgentArtifact) -> "CollaborationBlackboard":
    clone = self._clone()          # ① 深拷贝自己
    clone._artifacts = [*self._artifacts, artifact]   # ② 追加新列表
    return clone                   # ③ 返回新板,旧板不动
```



**不可变（immutable）设计**：每个 append/append\_event 都克隆出新黑板。为什么？——同一轮里任何时刻截取的 board 都是一致快照，协作过程天然可回放、可 debug，不存在「谁偷偷改了共享状态」。

### 7.2 autonomous/registry.py — 能力与决策

- `AgentCapability` 五种能力：MEMORY / UNDERSTANDING / SAFETY / CONTEXT / RESPONSE。
- `AgentProfile(name, capabilities, system_prompt, memory_policy, tool_permissions)`：Agent 的「名片」。`tool_permissions` 声明它可触碰的工具——权限是声明的，不是散落的 if——。
- `AutonomousAgentRegistry.candidate_decisions_for(task, board)`：过滤出能力匹配的 Agent，逐个问 `decide()`，把愿意认领的按置信度排序——认领制（claim-based）的核心——。

### 7.3 autonomous/board.py — 黑板共享读取（去重产物）

协作双方（协调器、Agent、运行时）都要「看一眼黑板推断当前状态」。此前三份近似拷贝，重构收编为：

```python
def risk_from_board(board) -> RiskLevel:
    # 所有 risk 工件取最高;任何 SAFETY_OVERRIDE 事件 → 直接 HIGH

def intent_from_board(board, *, use_board_risk=True, use_hard_terms=True) -> Intent:
    # ① 板上风险 HIGH → RISK(use_board_risk)
    # ② 有 intent 工件 → 用它
    # ③ 否则按硬高危词回退(use_hard_terms)→ RISK,不然 COMPANION
```

两个开关不是多余——原三份实现语义确有差异——：runtime 版不做硬词回退、coordinator 版不做风险预判。参数化让「历史行为逐点保留」且差异显式可见。`hard_high_risk()` 引用 `assessment.HIGH_TERMS`，安全词表全项目只此一份。

### 7.4 autonomous/coordinator.py — 认领制协调器

`AutonomousCoordinator.run(board)` 主循环（不超过 `max_rounds` 轮）：

```
每轮:
  1. _derive_missing_work   派生缺失任务:没有 memory 工件→建"读记忆"任务;
                           没有 intent→建"路由"任务;…没有 response→视条件建"提案"任务;
                           有新提案但没 safety_review → 建"安全复核"任务
  2. _try_accept_final      已有提案+复核通过+置信度≥阈值 → accept_final,结束
  3. _claim_candidates      各 Agent decide() 认领,按(任务优先级, 置信度)排序,
                           每轮最多 max_claims_per_round 个、每 Agent 最多 max_claims_per_agent 次
  4. 逐个执行:agent.act(task, board) → board.apply_turn_result(...)
  5. 回到 1
```

预算护栏体现在三处：轮次上限（超了发 `BUDGET_EXHAUSTED`）、每轮认领上限、单 Agent 认领上限。`force_response=True` 分支保证即使前置缺失也会被逼着产出一个回复——学生端永远有答案——。

### 7.5 autonomous/agents.py — 六个自治 Agent

`BaseAutonomousAgent` 提供公共设施：`_artifact()`（造产物）、`_message()`（发消息）、`client()`（按档案取专属模型）、`private_memory()/remember()`（读写 Agent 私有记忆）。

每个子类实现 `decide()`（要不要认领）+ `act()`（做事发产物）。最值得读的是 `RiskGuardianAutonomousAgent`——它身兼两职：

1.   独立评估  （`_assess`）：调单轮 RiskGuardian，产出 `risk` 工件；HIGH 时追加 `pending_report` 工件 + 发 `SAFETY_OVERRIDE` 事件（这个事件会让 `risk_from_board` 永远返回 HIGH，即使后续有人评估成 LOW——安全一票否决——）。
2.   复核回复  （`_review_response`）：对每个新提案做安全审查——

```python
if contains_internal_response_leak(answer):        # 泄漏内部字段?
    approved = False; reason = "response leaks internal implementation ..."
if risk is RiskLevel.HIGH and not any(term in answer for term in ["安全", "可信任的人", "紧急", "学校心理中心"]):
    approved = False; reason = "high-risk response lacks immediate safety guidance"
```

不通过就发 `critique` 工件 + `REVISION_REQUESTED` 事件 + 创建 CRITICAL 修订任务——Counselor 重新写，再送审，直到通过才可能被验收，。

### 7.6 autonomous/runtime.py — 黑板 → 聊天响应

`AutonomousAgentRuntime.run(session_id, message)` 是自治模式的总入口：

1. 组装 `AutonomousRuntimeServices`（store/registry/llm/模型档案）与六个自治 Agent；
2. 建黑板、发 `TURN_STARTED`，交给协调器跑到收敛；
3. 取 `accepted_artifact() or latest_artifact("response_proposal")` 的 answer（空则兜底一句话）；
4. 落 assistant 消息、更新记忆、发 `ARTIFACT_PUBLISHED`；
5. 从黑板抽取结果组装 `AutonomousRunOutcome`（intent/risk/skills/trace/pending\_report/response\_plan）——各种 `_xxx_from_board` 把四散的工件收敛成 API 需要的形状。



**学习要点**：黑板模式 + 认领制让「协作」有真实语义（谁认领、凭什么、产出什么），而不是假装的顺序调用；SAFETY\_OVERRIDE 的一票否决和 revise 循环是多 Agent 安全治理的样板。

#### 动手试一试：亲眼看黑板「不可变」

> ⚠️ **导入顺序**：本示例必须**先** `import app.agents.orchestrator`，**再**导入 `app.autonomous.*`。直接先导 `app.autonomous` 下的任何模块会触发包间循环导入（`app/agents/__init__.py` 会提前加载 orchestrator，而 orchestrator 又要导 `app.autonomous.runtime`，此时 `app.autonomous.agents` 还没初始化完），报 `cannot import name 'AutonomousRuntimeServices' from partially initialized module`。这是当前仓库已知的一个包初始化顺序坑，详见 FAQ Q8。

```python
# try_station7.py —— python try_station7.py
from app.agents.orchestrator import PsychOrchestrator   # ← 必须先导这个
from app.autonomous.events import CollaborationBlackboard, AgentArtifact

board = CollaborationBlackboard(turn_id="t1", session_id="s1", user_input="你好")
new_board = board.add_artifact(AgentArtifact(id="a1", owner="LeadAgent",
                                             kind="intent", payload={"intent": "companion"},
                                             confidence=0.9))
print(board is new_board, len(board.artifacts), len(new_board.artifacts))
# False 0 1  ← 旧板原封不动,新板多一条:append 即克隆
```

把这段语义搬进你自己的多 Agent 系统，就获得了「任意时刻截图即一致快照」的调试能力——这正是「确定性可回放」的地基。

#### 常见易错点

- **先导 `app.autonomous.*` 再导别的**：见上方的循环导入警告——新手极易在这里卡住半天；记住口诀「orchestrator 优先」。
- **以为黑板是可变共享对象**：所有 `add_*` / `append_*` 都返回**新板**；拿着旧板继续判断会读到「过期快照」。协调器循环里必须使用最新返回值。
- **把 `SAFETY_OVERRIDE` 当普通事件**：它一发出，`risk_from_board` 恒返回 HIGH——后续任何 Agent 把风险评成 LOW 都翻不了案。不要写「覆盖」它的逻辑，也不要在评测里把它当噪声过滤。
- **给协调器加「再跑几轮试试」的贪心**：轮次 / 每轮认领 / 单 Agent 认领三道护栏是防死循环的预算上限；放宽前先想清楚终止条件——`force_response` 已保证学生端永远有答案，多跑未必更好。

#### 练习

1. 用黑板模拟一次「提案 → 复核打回 → 修订」：手工 add 一个 `response_proposal` 工件、一个 `approved=False` 的 `safety_review`，再 add 修订版提案，并对照 7.5 检查你的事件顺序。
2. 写一个小函数 `timeline(board)`：把 `board.events` 打印成「时间戳 · 类型 · 谁」的时间线，体会管理端 trace 的数据来源。
3. 思考题：克隆式不可变会不会内存爆炸？（提示：黑板的生命周期 = 一轮对话一次 `run`，run 结束即可整体回收；对照 7.6。）

***

<a id="station-8"></a>

## 第 8 站 编排与 Harness — agents/orchestrator + harness

### 8.1 orchestrator.py — PsychOrchestrator

构造函数一次性装配：六个单轮 Agent + AgentRegistry + AgentRuntimeRunner + AgentModelRegistry + AutonomousAgentRuntime。

`_run()` 开头的分流是双/三运行时开关：

```python
if getattr(self.settings, "agent_runtime", "autonomous") == "autonomous":
    return self._run_autonomous(message, session_id, emit)   # 默认:黑板自治
# 否则:有序流水线(第 6 站的 Agent 按固定顺序跑)
```

有序路径（`agent_runtime="ordered"`）同样值得读一遍：load memory → assess risk → route →（companion 跳过检索！）→ search\_knowledge → grounding → HIGH 则 create\_report → 选标准 Skill → compose\_plan → finalize\_plan → 存消息/更新记忆/落 trace。每步都经 `runtime_runner.run_step()` 包裹（记录 AGENT\_STARTED/RUN\_FAILED 事件）。

两条路径最终都汇成 `ChatResponse`。`_run_autonomous` 额外把黑板事件流翻译成 RuntimeEvent 发给 `emit`——这就是 SSE 流式输出的来源。低风险对话支持真流式：回复生成的 token 经回调链（services.on\_reply\_token → finalize\_plan → stream\_support\_reply）实时推给 SSE，首字延迟≈模型首 token 延迟；中/高风险不直播，必须等 RiskGuardian 安全复核通过后输出。直播过真实 token 后，结尾的模拟切块 `_token_chunks()` 会自动跳过，避免重复。

### 8.2 harness.py — AegisAgentHarness

HTTP 与 Agent 世界之间的薄适配层，职责就三件：

```python
def _prepare(self, message, session_id, owner_user_public_id):
    original_input = message.strip()
    model_input = sanitize_user_input(original_input)      # ① 输入消毒
    owned_session_id = self.store.ensure_session(...)      # ② 归属会话解析
    return original_input, model_input, owned_session_id   # ③ 交给 orchestrator
```

`stream()` 把 `handle_stream` 的事件转发给 emit 回调。路由层因此可以保持「参数校验 + 鉴权 + 限流」的纯净，不碰任何 Agent 细节。

### 8.3 model\_profiles.py — 每 Agent 模型档案

`DEFAULT_AGENT_MODEL_PROFILES` 为六个 Agent 声明默认温度（记忆/路由/安全 0.0、知识 0.1、咨询 0.2、陪伴 0.3）与系统提示词，启动时写入 `agent_model_profiles` 表。`client_for(agent_name)`：档案是 `inherit` 就返回全局客户端，否则按档案的 provider/model 现造一个——让「安全评估用小模型、回复生成用大模型」成为一行配置——。

### 8.4 langgraph\_runtime.py — LangGraph StateGraph（三档运行时之一）

`LangGraphRuntime` 用 LangGraph 的声明式状态图编排同一批单轮 Agent：`START → load_memory → assess_risk → route_intent →（条件边：companion+low 直接跳 compose，否则）→ context → report（仅 HIGH）→ compose → finalize → END`。状态 `GraphState` 是 TypedDict，`trace/skills` 字段用 `Annotated[list, operator.add]` 让节点返回增量自动合并；图只编译一次，每次对话 invoke 新状态，天然线程安全；finalize 仅低风险传 `on_token` 直播回调，安全门控与另两个运行时一致。`AGENT_RUNTIME=langgraph|autonomous|ordered` 三档切换（默认 **autonomous**），是「同一业务、三种编排」的活教材。图还挂了 SqliteSaver 检查点（thread\_id=会话 ID，`LANGGRAPH_CHECKPOINT_ENABLED`），`get_state(session_id)` 可读取最近终态——长对话跨进程断点可恢复。

### 8.5 runtime.py — AgentRegistry / AgentRuntimeRunner

有序路径的执行骨架：`run_step(agent_id, action, call)` 统一包裹「取 Agent → 执行 → 记事件 → 异常记 RUN\_FAILED 再抛」。仅 60 行，却让有序路径的每一步都可观测。

#### 动手试一试：20 行跑通「最小全链路」

不启动 HTTP 服务、不配任何 key，在临时 SQLite 上把「学生输入 → 自治协作 → 回复 / 报告」整条链路跑一遍（这正是 `tests/test_orchestrator.py` 的装配方式）。存为项目根目录 `try_station8.py` 后运行：

```python
import tempfile, pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.entities import Base
from app.config import Settings
from app.repository.store import DatabaseStore
from app.skills import SkillRegistry
from app.agents.orchestrator import PsychOrchestrator

tmp = pathlib.Path(tempfile.mkdtemp())
kdir = tmp / "knowledge"; kdir.mkdir()
(kdir / "exam.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")

engine = create_engine(f"sqlite:///{tmp/'t.sqlite'}", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
settings = Settings(database_url=f"sqlite:///{tmp/'t.sqlite'}",
                    tool_output_dir=str(tmp / "tools"), redis_url="",
                    vector_enabled=False, agent_runtime="autonomous")
store = DatabaseStore(sessionmaker(bind=engine, autoflush=False, autocommit=False), settings=settings)
store.seed_knowledge_dir(kdir)
orch = PsychOrchestrator(SkillRegistry(kdir, store.add_report, store.search_knowledge), store)

resp = orch.handle("我最近考试压力很大，晚上睡不着", session_id="s-demo")
print(resp.intent.value, resp.risk_level.value, [s.name for s in resp.skills], len(resp.trace))

resp2 = orch.handle("我不想活了", session_id="s-demo")
print(resp2.risk_level.value, resp2.pending_report is not None, resp2.answer[:18])
```

预期输出（mock 模式下会伴随一条「回退模板」的日志提示，属预期行为；trace 条数随版本浮动）：

```text
counseling low ['assess_risk', 'search_knowledge'] 42
high True 我很在意你刚才提到的危险信号。此刻请
```

第一条消息走了「路由 → 检索 → 模板回复」的正常链路；第二条命中 `HIGH_TERMS` → 规则引擎判 high → 自治运行时追加 `pending_report` 工件 + `SAFETY_OVERRIDE` 事件，回复来自**本地安全模板**而非模型。

#### 常见易错点

- **调用不存在的 `orch.run()`**：编排器的公开方法是 `orchestrator.handle()`（阻塞）/ `handle_stream()`（SSE）；`run()` 是 Harness 与各运行时上的方法，别混层。
- **把本机 `.env` 带进实验**：示例显式传 `Settings(...)` 并关掉 Redis / 向量，就是为了隔离你本机的配置——这叫「测试密封」，tests 里同样如此。
- **切 `AGENT_RUNTIME` 后预期逐字段一致**：三档运行时复用同一批 Agent 与安全规则，**判定**一致（`--suite runtime-ab` 守护），但 trace 形状与事件粒度不同——对比看语义，不看逐字段。
- **在高风险回复里找模型生成的痕迹**：HIGH 路径永远本地模板（第 6 站 ② 处分流）；想看模型发挥，用低风险消息接真模型。
- **直接跑 `orch.handle` 却先导了 `app.autonomous`**：回到第 7 站的导入顺序警告——`orchestrator` 优先。

#### 练习

1. 把 `settings.agent_runtime` 依次改为 `ordered` / `langgraph` 重跑脚本，对比两次 `resp.trace` 的形态差异（条数、粒度、事件类型）。
2. 第二次 `handle` 之后，检查 `resp2.pending_report` 的 `risk_level` 与 `status` 字段——它此刻在等谁做什么？（答案在第 11 站）
3. 用 `store.list_traces()` 取回 trace，与管理端 `/admin` 的 trace 页面对照，找出同一次对话在两边的对应关系。

***

<a id="station-9"></a>

## 第 9 站 rag/ — 检索子系统

### 9.1 text.py — 分词

```python
def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())  # 英文整词、中文单字
    compact = "".join(ch for ch in text.lower() if "\u4e00" <= ch <= "\u9fff")
    grams.extend(compact[i:i + 2] for i in range(...))                   # 中文再补二元组
```



**为什么中文要 bigram**：单字粒度太碎（「考试」和「考/试」混在一起），BM25 的词频统计会失真；补上二元组让常用双字词成为可统计单元——不引 jieba 的轻量取舍。

### 9.2 scoring.py — 打分

- `bm25_scores`：教科书式 BM25（k1=1.5, b=0.75），中文用 bigram 词表。
- `rerank_score`：四路词法信号加权：——`base*0.55 + (余弦*0.75+关键词*0.25)*0.25 + 覆盖率*0.15 + 短语命中*0.05`。纯 Python，零模型成本，却显著改善排序。
- `fused_score` + `normalize_scores`：向量分与 BM25 分各自 min-max 归一后按权重（默认 0.65/0.35）线性融合。
- `expand_best_hit`：冠军块合并同源相邻块——切块会把答案拦腰截断，这一步把邻居拼回来。

### 9.3 chunking.py — 知识文档处理

`parse_knowledge_document` 解析 frontmatter（topic/audience/risk\_level/source\_type/last\_reviewed）；`metadata_matches` 做元数据过滤；`chunk_text` 是滑窗切块（size-overlap 步进）。

### 9.4 memory.py — 会话记忆摘要

```python
new_line = f"用户提到：{compact_sentence(user_message, 120)}；系统回应重点：{compact_sentence(assistant_answer, 160)}"
# 从最新往旧收集,超过 max_chars 停止 → 反转拼接
```

滚动摘要：每轮一行，超预算从最旧开始丢——心理对话「最近的上下文最重要」，这个丢弃方向是对的。

### 9.5 L1/L2/L3/L4 记忆分层、冲突规则与 Prompt 注入（第十三轮）

长对话不能只靠“把全部历史塞进 Prompt”，也不能只靠“滚动摘要”。Aegis 将记忆拆成四层：每层回答不同问题，并在注入模型时明确优先级。

| 层级 | 存储与作用域 | 存什么 | 读写时机 | 是否进入回复 Prompt |
| --- | --- | --- | --- | --- |
| **L1 Agent 私有记忆** | `agent_private_memories`；`agent_name + session_id` 隔离 | Agent 的协作策略、已完成任务等内部记录 | 各自治 Agent 按需读写 | 不作为统一用户画像直接注入 |
| **L2 用户事实** | `user_memory_facts`；登录用户按 `owner_user_id` 跨会话聚合，匿名会话以 `session_id` 隔离 | 睡眠、情绪、学业/人际压力、求助进展，以及有限的年级/专业背景 | 每轮回复后确定性抽取并写入；下一轮加载 | **是，且优先级最高** |
| **L3 会话摘要** | `session_memories`；会话级 | 历史对话压缩要点 | 每轮追加并按字符预算裁剪 | 是，但可能含过期状态 |
| **L4 原话窗口** | `chat_messages`；会话级精确读取 | 最近 `MEMORY_RECENT_MESSAGES` 条角色/内容原文 | 每轮加载，默认 15 条 | 是，用于贴近近期措辞 |

#### L2：为什么要采用 SCD-2（有效期版本）

`UserMemoryFact` 不会物理删除旧状态，而是维护：

```text
fact_key       同一事实槽位，例如 sleep_state
fact_value     当前值，例如 “睡眠困扰:睡不着”
effective_from 该值开始生效的时间
effective_until NULL 表示当前有效；被新值替代后写入截止时间
superseded_by  替代它的新事实 public_id
```

写入规则是一个简化版 Slowly Changing Dimension Type 2：

1. 当前有效行的值相同 → 判定重复，不写新行；
2. 当前有效行的值不同 → 截断旧行 `effective_until`，再插入新行；
3. 没有当前有效行 → 直接插入新行；
4. 正常回复 Prompt 只读取 `effective_until IS NULL` 的行，完整历史仅供审计/回溯。

所以“上周睡不着”后来变为“睡眠已经恢复”时，旧事实仍可追溯，却不会和新事实同时喂给模型。L3 摘要仍可能保留旧文本，因此 prompt 明确规定：**L2 当前有效状态优先；L3 与 L2 冲突时视 L3 为过期。**

#### `facts.py`：确定性抽取，而不是诊断模型

`app/rag/facts.py` 使用规则模式抽取睡眠、情绪、学业压力、人际困扰与求助进展；同时抽取有限的年级/专业背景。它不对用户进行医学诊断，也不从模糊表达推断人格或病史。这样做的收益是成本低、结果稳定、可复核；代价是遇到新表达时需要补规则，未来可以增加“LLM 候选 + 规则审查”的可选增强层。

#### L4 与当前消息去重：三运行时为何不同

- **ordered** 路径在当前用户消息落库前读取 L4，因此窗口天然不含本轮消息；
- **autonomous / langgraph** 路径先落库再加载记忆，因此将 `exclude_current=message` 传给 `recent_messages()`，只移除末尾与当前输入一致的用户消息；
- 三条路径都会将 L2/L3/L4 传给 `compose_plan()`，再进入 `LLMContext` 和 `build_messages()`。

这一细节避免同一句话既出现在“当前用户消息”又出现在“近期对话原文”中，降低模型重复回应的概率。

### 9.6 vector\_store.py — 向量后端

`build_vector_backend(settings)` 按配置返回：

- `VECTOR_ENABLED=false`（代码默认）：返回禁用向量后端，检索仍继续执行 BM25、加权融合/条件 rerank 和邻块扩展，只是不产生向量候选。
- `ChromaVectorBackend`：真向量库，chromadb 持久化（cosine 空间），支持快照。嵌入有两种来源，由 `EMBEDDING_PROVIDER` 决定：
  - `local`（`.env.example` 的推荐示例）：chromadb 内置 MiniLM 本地嵌入——离线、零 KEY、零费用；
  - `openai`（`Settings` 代码默认）：OpenAI 兼容 `/embeddings` API（需向量模型额度）。
- `LocalVectorBackend`：哈希 bigram 伪向量 + 本地余弦；当向量已启用但 Chroma 不可用、或显式选择 local 回退时使用，不是 `VECTOR_ENABLED=false` 时的默认替代。

`store.search_knowledge`（第 10 站）把 9.1–9.6 串成完整流水线：改写查询 → 向量候选（可选）→ 元数据过滤 → BM25 → 双路融合 → **weighted 模式才执行本地 rerank** → 邻块扩展 → 截 top\_k。RRF 模式走“排名融合 + 邻块扩展”，当前不会继续叠加 `rerank_score()`。



**学习要点**：RAG 不神秘，它是一条「分词→打分→融合→重排」的确定性流水线；每一环都可以单独替换成更强的实现（如 embedding 模型），这就是分层的好处。

### 9.7 混合检索深度剖析（第十二轮扩充）

#### 9.7.1 为什么需要混合检索

**单一检索方式的局限**：
- **纯 BM25（词频统计）**：只看字面匹配，"睡不好"检索不到"失眠"文档，因为词不重叠；对同义词、语义泛化无能为力。
- **纯向量检索**：中文语义高度依赖嵌入模型质量，低质量模型会把"考试压力"和"焦虑失眠"判为远距离；且商业 API 需要额度，无 KEY 时完全不可用。

**混合检索的核心思想**：让 BM25 的**精确召回**（关键词命中）与向量的**语义泛化**（理解同义/近义）互补，两路各自检索后融合排序。

#### 9.7.2 双路召回与融合策略

**第 1 步：双路各自召回**
```python
# BM25 路：对所有文档计算词频分数，取 top-N
bm25_results = [(doc_id, bm25_score), ...]

# 向量路：query embedding 与文档 embedding 余弦相似度，取 top-N
vector_results = [(doc_id, cosine_score), ...]
```

**第 2 步：分数融合（两种模式）**

**加权融合（Weighted，默认）**：
```python
# 各路分数先 min-max 归一化到 [0,1]
normalized_bm25 = (score - min) / (max - min)
normalized_vector = ...

# 按权重线性加权（默认 0.65 向量 + 0.35 BM25）
final_score = w_vector * normalized_vector + w_bm25 * normalized_bm25
```

- **优点**：直观，权重可调（`KNOWLEDGE_HYBRID_VECTOR_WEIGHT` / `KNOWLEDGE_HYBRID_BM25_WEIGHT`）
- **缺点**：对分数分布敏感，BM25 分数范围差异大时归一化会失真

**RRF 融合（Reciprocal Rank Fusion，第十二轮新增）**：
```python
# 不看分数，只看排名
rrf_score(doc) = sum(1 / (k + rank_in_bm25), 1 / (k + rank_in_vector))
# k=60 是经验常数，防止分母为 0
```

- **优点**：对分数尺度鲁棒，只依赖相对排名，企业 RAG 高频选择。
- **缺点**：丢失绝对分数信息（如 BM25=0.01 和 0.9 都只看排名）。
- **当前分支行为**：`KNOWLEDGE_FUSION_MODE=rrf` 时，仓储在 RRF 融合后直接做邻块扩展，不叠加本地 `rerank_score()`；因此 RRF 和 weighted+rerank 的结果应分开评测，不应假设它们走同一重排链路。
- **配置**：`KNOWLEDGE_FUSION_MODE=rrf` 切换（默认 `weighted`）。

#### 9.7.3 Rerank 四路词法信号

融合后的候选块进入 **rerank 阶段**（`rerank_score`），用纯 Python 四路信号加权：

```python
final = base_score * 0.55                          # 融合分保底
      + (cosine * 0.75 + keyword * 0.25) * 0.25    # 余弦相似度 + 关键词匹配
      + coverage * 0.15                             # 查询词覆盖率
      + phrase_bonus * 0.05                         # 完整短语命中奖励
```

**各信号解释**：
- `cosine`：query 与 doc 的 bigram token 余弦相似度（本地计算，无需向量模型）。
- `keyword`：查询 token 在内容中的命中比例，不要求 token 在 query 中重复出现。
- `coverage`：被内容覆盖的查询 token 比例，即 `len(query_tokens ∩ content_tokens) / len(query_tokens)`；不是 Jaccard 的并集分母。
- `phrase_bonus`：规整后的**完整 query**是内容子串时为 1，否则为 0；不是累计多个 2-gram 的出现次数。

**为什么不用模型 rerank**：纯 Python 零成本零延迟，实测已显著改善排序（见消融实验）；模型 rerank（如 BGE-reranker）可作后续增强。

#### 9.7.4 邻块扩展（Expand Best Hit）

**问题**：固定步长切块（512 字符，重叠 64）会把一段完整答案拦腰截断，用户看到的是"半句话"。

**解决**：`expand_best_hit(top_chunk, all_chunks)`
```python
# 找到排名第一的块（冠军块）
# 查找同源文件（source 相同）且位置相邻的块（offset 连续）
# 合并为一段完整上下文（最多 3 个块，约 1500 字符）
```

**效果**：用户问"如何缓解考试焦虑"，原本只返回"可以尝试深呼吸...[截断]"，扩展后返回"可以尝试深呼吸、肌肉放松，必要时寻求辅导员支持"（完整建议）。

#### 9.7.5 消融实验（Ablation Study）

第十二轮新增 `app/evaluation/rag.py:run_ablation()`，在**同一 77 条查询**上对比 4 种检索配置：

| 配置 | 说明 | HitRate@4 | 平均延迟(ms) |
| --- | --- | --- | --- |
| `bm25_only` | 关向量，开 rerank | **0.9351** | 20.59 |
| `hybrid` | 开 local-hash 向量，关 rerank | 0.8312 | 7.73 |
| `hybrid_rerank` | 开向量 + rerank（向量开启的可选生产配置，不是代码默认） | 0.8052 | 19.14 |
| `rrf` | RRF 融合 | 0.7662 | 8.16 |

**结论（如实呈现）**：
- 在**零依赖的 `local-hash` 词法向量**下，纯 BM25 已足够强，混入哈希向量反而稀释分数
- hybrid / RRF 的增量价值需要**真实语义向量**（Chroma + MiniLM / OpenAI embeddings）才能体现
- 这一结果明确了“演示默认 `VECTOR_ENABLED=false` 时走 BM25 路径；生产若启用语义向量应重新评测”的配置边界。

**运行方式**：
```bash
python -m app.evaluation.rag  # 输出双口径 HitRate + 消融对比
```

#### 9.7.6 查询缓存（第十二轮新增）

**动机**：RAG 检索（尤其向量 + rerank）延迟 15-20ms，重复查询浪费算力。

**实现**：
```python
# 有 Redis 时当前只写入 Redis（TTL=300s），知识检索的 read-through 读取仍走进程内 LRU；因此暂不能宣称跨进程 Redis 命中
# 进程内 LRU：key=规范化查询+top_k+过滤条件
self._knowledge_cache: OrderedDict[str, tuple[datetime, list[dict]]] = ...
```

**配置**：
- `KNOWLEDGE_CACHE_ENABLED=true`（代码默认 `false`）
- `KNOWLEDGE_CACHE_TTL_SECONDS=300`
- `KNOWLEDGE_CACHE_MAX_ENTRIES=128`

**当前实现边界**：有效命中来自进程内 LRU；Redis 缓存键会被写入以预留后续能力，但 `_check_cache()` 尚未读取 Redis，因此当前没有跨进程查询缓存。

**效果**：
- 冷查询 avg ~18-20ms
- 命中后 <0.01ms，**加速约 3 个数量级**
- 命中率 0.667（30 条 warmup + 60 次命中，基准测试数据）

#### 9.7.7 双口径评测

`app/evaluation/rag.py` 的 `is_relevant()` 拆为两层：

- **宽松口径（loose）**：来源命中**或**任一 expected term 出现在内容（原口径）
- **严格口径（strict）**：**仅** expected source 命中

**报告新增**：`hitRateStrict` / `strictSourceMatches`，同时输出两口径值。

**第十二轮实测（77 条查询，Top-4）**：
- 宽松口径 HitRate@4：**0.9351**（72/77）
- 严格口径 HitRateStrict：**0.8831**（68/77）
- MRR / NDCG@4：0.8203 / 0.8323

#### 动手试一试：分词、打分与滚动摘要

```python
# try_station9.py —— python try_station9.py
from app.rag.text import tokenize
from app.rag.scoring import keyword_score, query_token_coverage, phrase_score
from app.rag.chunking import chunk_text
from app.rag.memory import build_memory_summary
from app.rag.facts import extract_user_facts

toks = tokenize("我最近考试压力很大，晚上睡不着")
print(len(toks), toks[:8])       # 单字在前,bigram 在后

q, c = "如何缓解考试焦虑", "考试焦虑可以用深呼吸、规律作息缓解，必要时寻求辅导员支持"
print(keyword_score(q, c), query_token_coverage(q, c), phrase_score(q, c))
# 0.667 0.667 0.0   ← 词法信号能算出重合,但「整句短语」没命中

print(len(chunk_text("要点。" * 200, size=120, overlap=20)))   # 滑窗切块:步进 = size-overlap
print(build_memory_summary("", "我最近睡不着", "建议规律作息并尝试放松练习", 300))
# 用户提到：我最近睡不着；系统回应重点：建议规律作息并尝试放松练习

print(extract_user_facts("我最近晚上睡不着，考试压力很大"))
# [('sleep_state', '睡眠困扰:睡不着'), ('academic_pressure', '学业/发展压力:考试')]
```

#### 常见易错点

- **以为 bigram 是「两个词」**：是两个**汉字**的滑动窗口（让「考试」成为一个可统计单元），不是分词——不引 jieba 的轻量取舍。
- **拿 `rerank_score` 的某一路当总分**：四路信号各管一件事（融合保底 / 词法相似 / 覆盖率 / 短语命中），单独拎出来解释排序都会以偏概全。
- **混用两种融合模式的预期**：`rrf` 模式融合后**不再叠加**本地 rerank；拿 weighted+rerank 的结果当 RRF 的预期会得出错误结论（9.7.2 有专门说明）。
- **以为默认有语义向量**：`VECTOR_ENABLED` 代码默认 `false`，默认链路是纯 BM25 + 条件 rerank；消融数据（9.7.5）也表明 local-hash 词法向量反而会稀释 BM25 分数。
- **高估查询缓存**：Redis 只写不读（预留能力），命中来自进程内 LRU——多进程部署别指望跨进程命中（9.7.6）。

#### 练习

1. 用 `tokenize` 对比「睡不好」与「失眠」的 token 交集，体会为什么需要语义路；（进阶：若已装 Chroma，开 `VECTOR_ENABLED=true` 重跑 4.7 的 RAG 评测，对比 HitRate。）
2. 把 `chunk_text` 的 `overlap` 改成 0，观察切块边界变差后 `expand_best_hit`（邻块扩展）还能不能拼回完整答案。
3. 给 `extract_user_facts` 加一条「逃课」相关的事实抽取规则，跑通后回答：为什么这一层叫「确定性抽取」而不是「诊断」？

***

<a id="station-10"></a>

## 第 10 站 repository/store.py — 持久化仓储

`DatabaseStore` 是所有表的读写总闸（约 1146 行，第十三轮新增 L4/L2 方法后更新，按区块组织）：

-   会话/消息  ：`ensure_session`（不存在则建，支持归属回填）、`list/get/delete/rename_session`、`append_message`（首条用户消息自动成为标题）、**`recent_messages`**（L4 滑动窗口，第十三轮新增，支持 `exclude_current` 排除当前消息）。
-   认证  ：`ensure_default_users`（演示账号）、`authenticate_user`（验密 + 发会话令牌）、`get/revoke_auth_session`（过期即删）。
-   记忆  ：`get_memory`（Redis 缓存 → SQLite）、`update_memory`（调 `rag/memory.build_memory_summary` 后双写）。Agent 私有记忆同理（`append/load_agent_private_memory`，Redis list 缓存最近 50 条）。**L2 用户事实（第十三轮新增）**：`upsert_user_fact`（只增不删 + 有效期截断 + 重复丢弃，SCD-2 模式）、`active_user_facts`（只读 `effective_until IS NULL` 的当前有效行）、`user_facts_history`（完整历史版本）。
-   知识库  ：`seed/rebuild_knowledge_dir`（目录全量重建）、`ingest_knowledge`（内容未变则跳过重嵌）、`search_knowledge`（第 9 站流水线）、`rebuild_vector_index`、`backup_knowledge_dir`。
-   报告/个案  ：自身只剩薄委托——`list_reports` 等一行转给 `ReportCaseService`（第 11 站），服务持有同一个 Session。
-   工具任务  ：`create_tool_job`（先过契约校验，被拒也写审计！）、`run_pending_tool_jobs`、`retry_tool_job`、死信列表。
-   模型档案/审计/追踪  ：`ensure/get/list_agent_model_profiles`、`add/list_audit_logs`（写前脱敏）、`add_trace/list_traces`。



**读一个代表性方法**——`create_tool_job` 的「拒绝也要留痕」：

```python
try:
    governed = governed_payload(canonical_kind, payload, role=role, approved=approved)
except Exception as exc:
    self._add_tool_audit_record(db, kind, "queue", "rejected", str(exc), payload, ...)  # ← 先记拒绝
    db.commit()
    raise                                                              # ← 再抛出去
```

治理审计不在「成功路径」上，恰恰要覆盖失败路径——被拒绝的调用是最需要审计的东西。



**学习要点**：仓储大类按「领域分区块」组织仍然可维护，关键是把算法（rag/）与服务逻辑（services/）请出去；`with self.db_factory() as db:` 每方法一会话，提交即释放。

#### 动手试一试：拒绝也要留痕

在第 8 章最小全链路的 `store` 基础上（或按同样方式重建一个），体验「治理审计覆盖失败路径」：

```python
# 接 try_station8.py 的 store,或按其方式重新构建
try:
    store.create_tool_job("send_email", {"to": "guardian@example.com"},
                          role="student", approved=False)       # 学生不能触发邮件
except Exception as e:
    print("rejected:", type(e).__name__)                        # ToolGovernanceError

audits = store.list_tool_audits()                               # ← 但审计里已经有了
print(audits[0]["tool_kind"], audits[0]["decision"], "|", audits[0]["reason"])
# send_email rejected | send_email requires role=admin
```

#### 常见易错点

- **把仓储当「ORM 实体的镜像」逐字段映射**：`DatabaseStore` 按**领域**分区块组织方法（会话/认证/记忆/知识/报告/工具/审计）；先看区块再定位，比全文搜索快。
- **在路由或 Agent 里绕过 store 直连 ORM Session**：所有读写走总闸才有统一的缓存、审计与迁移边界；绕过一次，治理就漏一次。
- **以为 `recent_messages` 含本轮消息**：三运行时取窗口的时机不同（9.5「L4 去重」）——ordered 天然不含本轮；autonomous / langgraph 靠 `exclude_current` 剔除。自己加调用点时要选对。
- **跨方法长时间持有 Session**：`with self.db_factory() as db:` 用完即释放；长期持有是锁等待与脏读的来源。

#### 练习

1. 追踪 `create_tool_job` 被拒时的三步（写审计 → commit → raise），说明少了每一步分别会发生什么。
2. 对比 `get_memory`（Redis 缓存 → SQLite 双层）与 `recent_messages`（直读）为什么采用不同策略。（提示：读写比与失效成本。）
3. 思考题：如果把 rag/ 的打分逻辑搬进 store.py，会破坏哪条边界？（对照本站学习要点里的「把算法请出去」。）

***

<a id="station-11"></a>

## 第 11 站 工具治理 — tools/ + services/

高风险场景的完整闭环：报告审批 → 建个案 → 派发 5 个工具任务 → 后台执行 → 落记录。这一站是「治理与业务正交」的落地。

### 11.1 tools/contracts.py — 契约先行

```python
@dataclass(frozen=True)
class ToolContract:
    kind: str
    required_role: str                  # 只有 admin 能触发
    allowed_risk_levels: tuple[str, ...]
    approval_required: bool
    redacted_payload_fields: tuple[str, ...]
    max_attempts: int = 3
```

6 个受治理工具（alert/email/ledger/handoff/lookup/follow\_up）各有一份契约。`governed_payload()` 是入队前的统一关卡：

```python
def governed_payload(kind, payload, role, approved) -> dict:
    if role != contract.required_role: raise ToolGovernanceError(...)        # ① 角色
    if risk_level not in contract.allowed_risk_levels: raise ...             # ② 风险等级
    if contract.approval_required and not approved: raise ...                # ③ 审批
    redacted, fields = redact_payload(payload, contract.redacted_fields)     # ④ 脱敏
    return {**payload, "tool_kind": ..., "redacted_payload": redacted, ...}  # ⑤ 盖章放行
```

任何一步不过都是异常——工具根本进不了队列——。`TOOL_KIND_ALIASES` 把旧名（alert\_log\_mock 等）规范化，兼容历史调用方。

### 11.2 services/report\_case.py — 审批后的编排

`ReportCaseService.update_report`：状态改为 APPROVED 且风险 ≥ MEDIUM 时自动 `ensure_case`。`ensure_case_tool_jobs` 是工具派发中心：为每个新个案一次性创建 5 个 ToolJob（create\_alert/send\_email/write\_ledger/create\_handoff\_summary/follow\_up\_suggestion），载荷全部先过 `governed_payload`。

### 11.3 services/tool\_queue.py — 队列与后台 worker

- `ToolQueueService.run_pending(db, limit)`：批量取 PENDING 任务，检查依赖（`_dependency_ready`：同 case 的 handoff 完成后 email 才发）、执行、记录结果。
- 失败处理：attempts+1，未超限则改回 PENDING 并设 `run_after`（延迟重试）；超限写 `DeadLetterRecord`——死信是可运营的失败——，管理端有专门页面。
- `RateLimiter`：邮件每分钟限 N 封，超了不算失败，只延迟。
- `ToolQueueWorker`：线程池 + 轮询的后台常驻进程，FastAPI lifespan 里启停；`run_once()` 供手动触发（加分布式锁防并发）。

### 11.4 services/tool\_executor.py — 真实副作用

`execute(kind, payload, attempts)` 分发到：`write_ledger`（openpyxl 追加 Excel 行）、`create_alert`（建 AlertRecord + 可选 webhook）、`send_email`（SMTP 真发或 log 模式）、`create_handoff_summary`（写 Markdown 文件）、`append_jsonl`（通用 JSONL 追加）。`always_fail` 载荷是故意留的测试钩子——harness 用它验证重试与死信路径。

### 11.5 services/tool\_records.py + tool\_governance.py

前者持久化 ExcelRecord/AlertRecord（去重：同报告同个案只记一条）；后者提供执行前授权检查与审计写入，供 MCP 边界复用。

### 11.6 tools/gateway.py + app/mcp/server.py + app/mcp/client.py — MCP 边界

`ToolGateway` 协议两个实现：`InternalToolGateway`（直接 store.create\_tool\_job）与 `McpToolGateway`（通过 stdio 拉起 FastMCP server 子进程调用同一套受治理工具）。`build_tool_gateway` 按 `TOOL_BACKEND` 选择——换后端不改业务代码——。MCP server 的每个 `@mcp.tool` 内部走的仍是 DatabaseStore + 契约校验：协议变，治理不变。



**学习要点**：这一站回答「为什么不让模型直接调工具」——因为每个外部动作都必须被（角色/风险/审批/脱敏/重试/审计）六重约束包住；契约数据化（frozen dataclass 注册表）让新增工具 = 新增一份声明。

#### 动手试一试：契约五连检查

```python
# try_station11.py —— python try_station11.py
from app.tools.contracts import governed_payload, list_tool_contracts, TOOL_CONTRACTS

print(sorted(TOOL_CONTRACTS))
# ['create_alert', 'create_handoff_summary', 'follow_up_suggestion',
#  'lookup_resource', 'send_email', 'write_ledger']

try:
    governed_payload("send_email", {"to": "g@example.com"}, role="student", approved=False)
except Exception as e:
    print(type(e).__name__, "|", e)      # ① 角色不过 → 直接拒:ToolGovernanceError | send_email requires role=admin

g = governed_payload("write_ledger", {"summary": "个案"}, role="admin", approved=True)
print("tool_kind" in g, "redacted_payload" in g)   # True True ← 盖章字段
```

#### 常见易错点

- **先执行后校验**：任何「直接调 executor」的捷径都绕过了五连检查；唯一入口是 `governed_payload` → ToolJob → worker。
- **以为死信是 bug**：`DeadLetterRecord` 是「可运营的失败」——重试超限后的正确归宿，管理端有专门页面；看到死信先查原因，而不是删记录。
- **把邮件限流当失败**：`RateLimiter` 超限时任务只是推迟（写入 `run_after`），不算失败、不进死信。
- **给 MCP 后端单独写一套权限**：MCP server 的每个 `@mcp.tool` 内部仍走 store + 契约——换协议不复写治理，治理也不随协议切换而失效。

#### 练习

1. 打印 `list_tool_contracts()`，找出哪些工具不需要审批、哪些允许 MEDIUM 风险，体会「契约数据化」如何让新增工具 = 新增一份声明。
2. 用 `always_fail` 载荷手动创建一个 ToolJob 并触发 worker，观察 `attempts` 递增与最终进入死信的全过程（11.4 的测试钩子）。
3. 思考题：为什么 `approval_required` 的校验在脱敏**之前**？如果顺序反过来，被拒调用的 payload 会经历什么、审计里会看到什么？

***

<a id="station-12"></a>

## 第 12 站 HTTP 层 — api/ + main.py

### 12.1 main.py — 只做装配（约 90 行）

`create_app()` 顺序：settings → engine/会话工厂/建表 → DatabaseStore（默认账号+知识库种子）→ RuntimeServices → SkillRegistry → LLM 客户端 → Orchestrator → Harness → 工具网关 → 队列 worker。全部挂 `app.state`，注册中间件与 5 个路由模块。lifespan 里启停 worker。



**重构前后的对比**：初版 45 个路由全以闭包塞在 create\_app 里（576 行）；现在 main.py 只剩装配，路由按领域分家——依赖从「闭包捕获」变成「request.app.state 显式获取」，可测性和可读性都是量级差异。

### 12.2 api/deps.py — 认证依赖

```python
def current_principal(request: Request) -> AuthPrincipal:
    cookie_name = request.app.state.settings.auth_session_cookie   # Cookie 名可配置
    session_token = request.cookies.get(cookie_name)
    ...
```

`require_admin = Depends(current_principal) + 角色检查`。路由声明 `principal: AuthPrincipal = Depends(require_admin)` 即完成鉴权——FastAPI 依赖注入的标准用法。

### 12.3 api/middleware.py — 请求追踪（重构补齐的功能）

```python
async def attach_request_context(request, call_next):
    request_id = request.headers.get("X-Request-ID") or random_id("req", 12)
    trace_id = request.headers.get("X-Trace-ID") or random_id("trace", 12)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    return response
```

请求方带头则沿用（链路串联），否则生成。配合落库的 Agent trace，一次请求从 HTTP 到 Agent 每一步都可追。

### 12.4 其余路由模块

- `schemas.py`：9 个请求模型集中定义。
- `pages.py`（3 个 HTML）、`system.py`（health/readiness/agent-status/skills）。

#### 动手试一试：用 TestClient 把 HTTP 层当积木玩

装好依赖后（4.2），无需启动 uvicorn 就能整站测试——FastAPI 的 `TestClient` 直接在进程内调用应用：

```python
# try_station12.py —— python try_station12.py（需已按 4.2 装好依赖）
from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())
print(client.get("/api/health").json())      # 进程活着
print(client.get("/api/readiness").json())   # 数据库就绪(与 health 语义不同!)
r = client.post("/api/auth/login", json={"username": "student", "password": "student123!"})
print(r.status_code)                          # 200,响应里种下会话 Cookie
print(client.get("/api/auth/me").status_code) # 200 ← Cookie 自动携带,已登录
```

#### 常见易错点

- **把业务判断写进路由**：路由只做「参数校验 + 鉴权 + 限流」；发现自己在路由里拼 Prompt 或查知识库，就说明该下沉到 Harness / 服务层了。
- **混淆 health 与 readiness**：前者=进程活着，后者=数据库就绪；容器编排的存活探针与就绪探针各用各的，配反了会出现「活着但不该接流量」的窗口。
- **在前端硬编码 Cookie 名**：`auth_session_cookie` 来自配置；改配置后硬编码的地方会悄悄失联。
- **绕开 `app.state` 取依赖**：路由统一从 `request.app.state.xxx` 显式获取；从别处 import 全局单例会破坏「一个 app 实例一套依赖」的隔离，测试并行时互相污染。

#### 练习

1. 用 TestClient 复现 4.5 的「风险闭环」：学生发高危消息 → 管理员登录审批 → 查询工具任务状态全 success。
2. 给 `attach_request_context` 中间件加一个 `X-Aegis-Version` 响应头，用 TestClient 断言其存在。
3. 思考题：用 TestClient 的视角解释——为什么重构前「45 个路由闭包捕获变量」难以测试，而 `app.state` 注入可以？

***

<a id="station-13"></a>

## 第 13 站 评测闭环 — evaluation/（含 harness/ 与 RAG 评测）+ eval/



**工程化 Agent 项目的标志**：效果不是「看着不错」，而是可重复度量。

- `evaluation/runner.py`：真实指标——路由/风险判定准确率、高风险召回率、误报率、HitRate/Recall@4/Precision@4/MRR/NDCG@4、技能选择、安全泄漏检查、多轮一致性、150 条规模化基准；如实标注样本量、数据来源与验证日期（含 95% 置信区间），不再为满分筛选样本。**150 条规模化基准按 `layer` 字段双层拆分**：`base`（基础层·贴近主流场景）/ `stress`（压力层·边界探测），runner 分别输出两套独立指标（`scaled_benchmark.base` / `scaled_benchmark.stress`），零删改、不凑分——既保住“代表性”卖点，也主动暴露规则通道的边界缺口。
- `evaluation/datasets.py`：加载 `eval/fixtures/representative_corpus.json`（150 条人工构造、人工标注、贴近校园心理求助语料的代表性金标样本，**每条含 `layer`（base/stress）与 `source`（synthetic-representative/synthetic-boundary）字段**，含隐式高危与第三人称干扰）、`rag_queries.json`（77 条自然语言 RAG 问句）、`multi_turn_corpus.json`（8 组多轮场景）；并提供基于种子哈希排序的可复现抽样工具。
- `evaluation/report_html.py`：单文件 HTML 报告（内联 CSS），管理端一键可看。
- `app/evaluation/rag.py`：RAG 专项（HitRate/Recall@4/Precision@4/MRR/NDCG@4，独立运行改用一次性 SQLite 评测库、不依赖 MySQL/pymysql），数据集在 `eval/fixtures/rag_queries.json`（77 条自然语言问句，基于当前 24 篇知识文档）。
- `app/evaluation/harness/runner.py` + `factory.py`：工程级场景回放——8 套件（risk/routing/skills/rag/api/tool-queue/scaled/runtime-ab）验证端到端行为（如“审批后 5 个工具任务全部 success”“死信被正确创建”），失败退出码 1，可接 CI。`factory.py` 是重构产物：harness 与 `eval/run_eval.py` 共用一个装配工厂，消除两份漂移的样板。
- `scripts/eval_risk_dual_path.py`（第十一轮历史实验）：风险 LLM 通道双路径评测——同 150 条语料分别跑 baseline（MockLLM + channel OFF）与 llm_stub（`MetaphorAwareStubClient` + channel ON），直调 `RiskGuardianAgent.assess()` 避免 response 生成/judge 等额外 LLM 调用；另有真实 GLM-4.7-flash 的 25 条扩展 best-effort probe。产出 `data/eval/risk_dual_path.json`。当前生产模型验收以 `D:\AegisTraining\reports\risk-qlora-eval-v9.json` 为准。
- `scripts/probe_glm.py`（第十一轮新增）：GLM 端点探针——验证 endpoint/model/api_key 可用性，不打印 API key，退出码 0=可用。
- `eval/fixtures/`：路由/风险/安全/多轮小型金标集 + `representative_corpus.json`（150 条）/ `rag_queries.json`（77 条）/ `multi_turn_corpus.json`（8 组）人工构造、人工标注的代表性数据集。



**学习要点**：评测三层——单元（pytest；数量随版本变化）/能力（eval runner）/链路（harness 8 套件）；mock LLM 让主链评测可复现，测的是系统不是模型运气。三运行时 A/B（`--suite runtime-ab`）对比编排器延迟/trace/调用数，LLM-as-Judge（`evaluation/judge.py`）给回复打共情/安全/结构分——评测从「分对错」升级到「评质量」。**双路径验证**（`scripts/eval_risk_dual_path.py`）量化 LLM 通道的能力上界：baseline（channel OFF）压力层 risk_acc=0.67 → stub-LLM on（channel ON）0.94，证明 LLM 通道能补齐规则漏判的隐喻式风险表达。自动 Skill 蒸馏会写入使用统计与 `skills/auto/`；做 hermetic 评测时应显式关闭蒸馏或隔离输出目录，避免运行状态污染下次基线。

#### 动手试一试：跑一次真评测

```bash
# 综合评测(mock LLM,确定性):输出真实指标与 95% 置信区间
python -m eval.run_eval

# RAG 专项:双口径 HitRate + 消融对比(77 条查询)
python -m app.evaluation.rag

# 工程回放:风险套件(改安全逻辑后的必跑项)
python -m app.evaluation.harness.runner --suite risk
```

跑完对照本站开头的指标清单逐个找到出处：路由准确率、高风险召回率、FPR、HitRate@4、MRR、NDCG@4…… 再打开管理端评测页（或 runner 输出的 HTML 报告）看同一批数字的可视化呈现。

#### 常见易错点

- **只看「通过率」，不看样本量与置信区间**：runner 如实标注样本来源与区间；「150 条上 FPR=0」与「10 条上 FPR=0」不是一个量级的证据。
- **评测时开着自动蒸馏 / 查询缓存**：会写使用统计、污染基线（4.9 第 5 条）；hermetic 评测先关 `SKILL_DISTILL_ENABLED`。
- **把文中引用的数字当当前承诺**：本指南出现的所有指标（0.9351、0.67→0.94 等）都对应特定分支 / 日期 / 配置；自己机器上以现跑为准。
- **用真模型跑安全主链评测**：mock 保证「测系统不测模型运气」；真模型只应进入 LLM-as-Judge 等质量通道，且结果要标注随机性与日期。

#### 练习

1. 往 `eval/fixtures/rag_queries.json` 加一条「人际关系」类问句并标注 expected source，重跑 RAG 评测看它在宽松 / 严格两种口径下的表现。
2. 临时删掉 `HIGH_TERMS` 里的一个词，跑 `--suite risk`，用输出解释「护栏」的意义，然后恢复并再跑一遍确认复原。
3. 阅读 `--suite runtime-ab` 的输出字段，写出「三档运行时判定一致」的判据是哪几个数字。

***

<a id="station-14"></a>

## 第 14 站 收尾 — static/ + tests/

- `static/`：原生 JS 三端界面（零构建）：登录页（index/login.js，Hero 标语与数据条）、学生端（student，助手「小暖」——SSE 流式对话、消息头像、心情速选与紧急求助卡）、管理端（admin，三列页签工作台——左列「个案|知识库|协作状态」、中列「风险报告|对话回放」、右列「详情检查器 + 工作台」，界面全中文，桌面端固定一屏）。前端实现详解见《[前端学习指南](docs/frontend-learning-guide.md)》。
- `tests/` 当前包含多个模块化测试文件：orchestrator（提供 `build_orchestrator` 给其他测试复用）、api（TestClient 全链）、agent\_runtime、retrieval\_eval、mcp\_tools、harness、assessment、risk\_dual\_channel（双通道，覆盖 corp-106..130 隐喻双路径并含 `MetaphorAwareStubClient`）、risk\_qlora\_channel（QLoRA 风险通道：升级/不降级/回退/非法 JSON/URL 防护/默认关闭）、function\_calling（FC）、runtime\_ab（A/B）、judge（LLM 评审）、langgraph\_runtime、langgraph\_checkpoint（跨进程恢复）、reply\_style（真人化提示词与模板标签守护）。历史“约 71 项通过”应附带日期与环境，执行时统一使用 `python -m pytest tests -q`（历史上位于根目录的联调脚本 `test_chat.py` 已迁至 `scripts/smoke_chat.py`，不再参与 pytest 收集）。
- 第十三轮新增的 L2/L4 与 auto Skill 已做烟雾验证，但尚缺少专门 pytest 回归：SCD-2 冲突截断、匿名命名空间隔离、三运行时 L4 去重、仅 L2/L4 时 LangGraph `memory_used`、第 3 次自动蒸馏及 auto Skill 防递归等都应补成独立用例。

#### 动手试一试：给测试「上保险」

```bash
# 前端三脚本语法检查(零构建项目的基本卫生)
node --check static/login.js static/student.js static/admin.js

# 后端全量(tests/;联调脚本已迁至 scripts/smoke_chat.py,不在收集范围)
python -m pytest tests -q

# 只跑一个模块,快速定位回归
python -m pytest tests/test_assessment.py -q
```

#### 常见易错点

- **把联调脚本当单测跑**：`scripts/smoke_chat.py` 会向运行中的服务发起真实 HTTP 请求——它是为此设计的联调工具，不是 pytest 用例；单测统一用 `python -m pytest tests -q` 收集（4.7 有说明）。
- **引用「约 71 项通过」当固定数字**：测试数量随版本浮动，历史数字必须附带日期与环境；以当前收集结果为准。
- **新功能不配测试**：上面缺口清单里的每一项都是现成的练习题——补测试正是掌握对应模块最快的路径。
- **测试里用生产 `.env`**：沿用第 8 站示例的「测试密封」写法——显式 `Settings(...)`、tmp 路径、关掉可选依赖，测试结果才可复现。

#### 练习

1. 找到守护「companion 跳过检索」的测试（第 6 站易错点提过），读懂它的断言，并故意破坏该短路看测试如何变红。
2. 为第三人称语境保护写一个新用例（参考 `try_station3.py` 的第三条消息），跑通后提交。
3. 从上面的「尚缺回归」清单里认领一项（推荐 SCD-2 冲突截断），补成独立 pytest 用例。

***

<a id="faq"></a>

# 第六部分：常见问题解答（FAQ）

> 按「先概念、后排错、最后学习方法」组织。环境安装类的高频问题在 4.8 有精简版；本部分给出更完整的解释与章节跳转。

## A. 概念与设计

**Q1：mock 模式下没有 LLM，为什么高风险闭环还能完整跑通？**

高风险判定靠确定性规则（第 3 站），回复用本地安全模板（第 6 站的 ② 分流），模型只是双通道里的辅助通道、失败时返回 `None`（第 5 站）。所以「无模型」只影响低风险回复的生成质量，不影响安全链路——这也是 4.5 能三步验证闭环的原因。

**Q2：三个运行时该用哪个？学习顺序呢？**

默认 `autonomous`。学习顺序建议 ordered（看懂每个零件）→ autonomous（看懂真实协作）→ langgraph（看懂工业编排与检查点）。三档共享同一批 Agent 与安全规则，判定一致性由 `--suite runtime-ab` 守护（1.5、第 13 站）。

**Q3：为什么自研黑板，而不把 LangGraph 当主运行时？**

教学与治理诉求：append-only 黑板让协作过程可回放、无共享状态竞争，`SAFETY_OVERRIDE` 一票否决与「提案 → 复核 → 修订」循环的语义表达最直接（第三部分「自研 Blackboard」条目）。LangGraph 保留为对照方案与检查点（长对话恢复）能力，避免「工具绑架业务」。

**Q4：RAG 为什么默认关向量？开了不更强吗？**

`VECTOR_ENABLED=false` 时走 BM25 + 条件 rerank：零依赖、零延迟、可解释，且在本地词法向量下实测最强（9.7.5 消融：纯 BM25 0.9351 优于混入 local-hash 向量的 0.83）。语义向量的增量需要**真嵌入**（Chroma + MiniLM 或 OpenAI embeddings），启用后应重新评测。

**Q5：记忆 L1~L4 各自解决什么问题？（一句话版）**

L1 管 Agent 协作内务；L2 管「用户现在是什么状态」（SCD-2 有效期版本，跨会话、注入优先级最高）；L3 管压缩历史（可能过期）；L4 管近期措辞（贴着原话回应）。详见 9.5。

**Q6：模型能自己决定调工具吗？**

不能。模型只能在白名单内选**技能**（function calling，第 4 站）；一切外部副作用先变成 `ToolJob`，过契约五连检查（角色 / 风险 / 审批 / 脱敏 / 重试与审计）后由后台 worker 异步执行（第 11 站）。模型「点菜」，代码「下厨」并结账。

**Q7：为什么回复要过「内部字段泄漏」检查？**

「报告编号 / 风险分 / 置信度」是内部信息，漏给学生会造成二次伤害并破坏信任边界（2.2）；这是 RiskGuardian 复核（7.5）的第一道断言，命中即打回重写。

## B. 运行与排错

**Q8：`import app.autonomous...` 报循环导入 `cannot import name 'AutonomousRuntimeServices' from partially initialized module`？**

包初始化顺序坑：`app/agents/__init__.py` 会加载 orchestrator，而 orchestrator 又导 `app.autonomous.runtime`；若 Python 从 `app.autonomous` 侧开始初始化，两条链会在 `app.autonomous.agents` 处相撞。**解法**：任何脚本先 `from app.agents.orchestrator import PsychOrchestrator`（或 `from app.main import create_app`），再导 `app.autonomous.*`。示例见第 7 站。

**Q9：测试收集数量和文档写的不一样？**

数字随版本浮动，文档一律附日期与环境（4.9 第 1 条）；以你当前 `python -m pytest tests -q` 的收集结果为准。

**Q10：评测结果与文中引用的数字对不上？**

文中所有指标都对应特定分支 / 日期 / 配置。复现要点：关自动蒸馏与查询缓存、按 9.7.5 的四配置对照检查向量开关、同数据集同 top_k。复现不了就先 diff 配置，再怀疑代码。

**Q11：`AI_PROVIDER=openai` 起服务后请求超时 / 连接失败？**

先跑 `python -m scripts.probe_glm` 验证端点连通性（不打印 key，退出码 0=可用）；再确认 `OPENAI_BASE_URL` 是否需要 `/v1` 后缀、接 GLM 时 `LLM_THINKING_ENABLED` 建议关闭以降低延迟。

**Q12：报 `ModuleNotFoundError: pymysql`（或 chromadb / redis 等）？**

这些都在 `requirements.txt` 里，说明 venv 没装全：重跑 `pip install -r requirements.txt`。注意区分「运行期降级」与「导入期缺失」：Redis 连不上会降级，但模块 import 不到会直接报错。

**Q13：改了 `knowledge/` 里的文档，检索结果没变？**

`seed_knowledge_dir` 只在初始化时入库；需要重建（`rebuild_knowledge_dir` 或重跑 `python -m app.init_db`），内容未变的块会跳过重嵌（第 10 站）。另注意查询缓存（9.7.6）可能让你读到旧结果。

## C. 学习方法

**Q14：如何向别人讲清这个项目？（3 分钟版本）**

一个矛盾（学生要倾诉 vs 管理要审计）→ 两条信息架构 + 一个 Harness 收口（1.4）→ 四条设计哲学（1.2）→ 现场演示 4.5 的三步闭环。被追问时再展开第 7 站（协作）与第 11 站（治理）。

**Q15：想把它裁剪成自己的项目，最小骨架是哪几站？**

1（配置 / 实体）→ 3（规则风险）→ 5（模型协议）→ 6（单轮 Agent）→ 10（存储）→ 12（HTTP）。黑板、工具治理、评测都可以后补；但「规则优先」与「None 即兜底」两条纪律建议从第一天保留。

**Q16：每站的练习做完，算学会了吗？**

用「总结四」的从零重建检查清单自测：能不看文档说清每一条「为什么」才算过关；能给别人讲明白 7.4 协调器循环的三道护栏与验收条件，才算真的懂了多 Agent 协作。

***

<a id="part-7"></a>

# 第七部分：总结

## 总结一：设计模式回顾

| 模式           | 落地位置                                                                             | 作用                  |
| ------------ | -------------------------------------------------------------------------------- | ------------------- |
| Protocol 抽象  | LLMClient / ToolGateway / AutonomousAgent                                        | 后端可插拔，mock/真实一键切换   |
| 工厂函数         | build\_llm\_client / build\_tool\_gateway / build\_vector\_backend / create\_app | 装配逻辑集中，选择逻辑统一       |
| 依赖注入         | SkillRegistry（report\_sink/knowledge\_search）、API 路由（app.state）                  | 层间解耦，测试可替换          |
| 不可变数据 + 克隆追加 | CollaborationBlackboard.append\_\*                                               | 协作过程可回放、无共享状态竞争     |
| 黑板模式         | autonomous/ 全家                                                                   | 多 Agent 通过共享产物协作    |
| 认领制调度        | AutonomousCoordinator + AgentDecision                                            | 「谁干活」由能力+置信度决定      |
| 一票否决         | SAFETY\_OVERRIDE 事件                                                              | 安全判断不可被后续覆盖         |
| 责任链          | governed\_payload 五连检查                                                           | 工具入队前统一关卡           |
| 生产者-消费者      | ToolJob 表 + ToolQueueWorker                                                      | 副作用异步化，不阻塞学生端       |
| 读写缓存         | Redis（记忆/私有记忆）+ 进程内降级                                                            | 可选加速，无 Redis 不影响正确性 |
| 模板方法式兜底      | CounselorAgent.finalize\_plan                                                    | 模型失败永远有安全回复         |
| 参数化收编        | board.intent\_from\_board(use\_board\_risk/use\_hard\_terms)                     | 去重但显式保留历史语义差异       |

## 总结二：一次请求的完整数据流

```
学生输入
 → POST /api/chat(api/chat.py:限流 + 归属校验)
 → AegisAgentHarness._prepare(消毒 + 会话解析)
 → PsychOrchestrator._run(autonomous)
 → AutonomousAgentRuntime.run
    → 黑板 + TURN_STARTED
    → Coordinator 循环:
        MemoryAgent.load → memory 工件
        LeadAgent.route → intent 工件
        RiskGuardian.assess → risk 工件(HIGH:pending_report + SAFETY_OVERRIDE)
        KnowledgeAgent.search → context 工件(RAG 流水线)
        Counselor/Companion.compose_plan + finalize_plan → response_proposal
        RiskGuardian._review_response → safety_review(不过 → critique → 修订循环)
        → FINAL_ACCEPTED
 → 落库:assistant 消息 + 记忆更新 + AgentRunTrace
 → ChatResponse → JSON / SSE
 [异步] 管理员审批 → ReportCaseService.ensure_case → 5×ToolJob → Worker 执行
        → Excel/邮件/预警/交接/审计 全部落记录
```

## 总结三：实操建议

1.   跑起来  ：`python -m app.init_db && uvicorn app.main:app --port 8091`，用 student/student123! 登录发一句「我最近考试压力很大，晚上睡不着」，再去 /admin 看报告与 trace。
2.   看一次安全闭环  ：发「我不想活了」，观察：回复是本地安全模板（mock 下也是）→ 管理端出现待审报告 → 审批 → 工具任务全部 success。
3.   读一次黑板  ：`tests/test_orchestrator.py` 里的高风险用例断言了 SAFETY\_OVERRIDE 的传播；再对照 `autonomous/runtime.py` 的 `_trace_from_board` 看事件如何变成 trace。
4.   改一个小东西试试  ：往 `assessment.HIGH_TERMS` 加一个词，跑 `python -m pytest tests -q` 与 `python -m app.evaluation.harness.runner --suite risk`——体会「单一来源 + 评测护栏」如何让修改变得安全。
5.   换个模型  ：设 `AI_PROVIDER=ollama` 起服务，其余什么都不用改；风险通道若启用微调模型，另设 `RISK_QLORA_ENABLED=true` 并启动 D 盘隔离服务，路径由 `AEGIS_TRAINING_ROOT` / `AEGIS_QLORA_MODEL_DIR` 配置。
6.   跑一次历史双路径验证  ：`python scripts/eval_risk_dual_path.py`——看 baseline 与 stub-LLM 的历史对比；当前真实 QLoRA 结果见 `D:\AegisTraining\reports\risk-qlora-eval-v9.json`。

## 总结四：按引导式路线「从零重建」的检查清单

如果你读完本指南要独立搭一个结构相同、功能一致的项目，按这份清单自测：

- [ ] 配置层用声明式 + 安全默认值，不写 .env 也能跑（第一部分 1.3 / 第 1 站）
- [ ] 风险评估是确定性规则、且是关键词单一事实来源（第 3 站）
- [ ] 高风险回复由规则决定，模型只在低风险路径参与，且回复经「内部字段泄漏」复核（第 6、7 站）
- [ ] 多 Agent 协作有共享状态、任务认领、产物验收、安全一票否决、可回放 trace（第 7 站）
- [ ] RAG 先路由再检索，BM25 与向量融合 + rerank，向量可降级（第 9 站）
- [ ] 工具不直接执行，先成受治理 ToolJob，经契约/审批/脱敏/审计，后台 worker 异步跑（第 11 站）
- [ ] HTTP 层纯净（鉴权/限流/路由），Agent 细节收口在 Harness（第 8、12 站）
- [ ] 评测可重复：单测 + 端到端 harness + 三运行时 A/B + 风险 LLM 通道双路径验证（第 13 站）
- [ ] 默认本地零依赖可跑，外部依赖（Redis/向量/SMTP/MCP）均可选且语义一致降级（第四部分）

***

> 免责声明：本项目用于心理支持工程学习与展示，不提供医学诊断，不能替代专业心理咨询或危机干预服务。

***


本指南对应 `main` 分支第十三轮之后的已提交状态（REFACTORING → OPTIMIZATION → AUTH-MYSQL → LANGGRAPH-DOCKER → DEEP-ENHANCEMENTS → LLM-RESPONSE-HUMANIZATION → MEMORY-ENHANCEMENT → CONFRONTATIONAL-DIALOGUE-TESTING → ROUND-9-CONSOLIDATION → CORPUS-LAYER-SPLIT → ROUND-11-RISK-LLM-DUAL-CHANNEL → ROUND-12-RAG-ENHANCEMENT-BENCHMARK → ROUND-13-MEMORY-SKILL-DISTILLATION → ROUND-15-FRONTEND-CALM-THEME → ROUND-16-ADMIN-TEACHER-GUIDE → ROUND-17-FRONTEND-OVERHAUL）。各轮详细变更见 [docs/records/](docs/records/) 系列文档；前端另有姊妹篇《[前端学习指南](docs/frontend-learning-guide.md)》。

本指南在此基础上做了面向学习的结构化扩充（保持原有章节与结论不变）：新增第零部分（预备知识与术语表）、开篇学习路径与全书目录、每站「动手试一试 / 常见易错点 / 练习」三件套与第六部分 FAQ；所有示例代码均在当前分支实测通过。若章节与代码行为不一致，以仓库源码为准并欢迎修订本指南。
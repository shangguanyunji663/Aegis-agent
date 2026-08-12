# Aegis 学习全流程学习指南

## 1. 项目定位：这是一个什么项目？

Aegis 是一个面向学生心理支持场景的 Agent 应用。它不是一个简单的聊天机器人，而是一个更接近“生产级安全 Agent 系统”的项目。

它的核心目标包括：

- 对学生消息进行情绪与风险识别
- 判断是否进入支持、危机干预、知识检索或人工审核流程
- 让多个 Agent 协同工作，而不是单一 LLM 直接回答所有问题
- 对工具调用做审批、审计和治理，避免高风险操作被直接执行
- 在高风险场景下输出更稳妥的帮助信息与跟进方案

从学习角度说，这个项目很适合掌握以下能力：

- Python 项目的工程结构理解
- API + 前端 + 后端协同视角
- 多 Agent 协作设计
- 安全治理与工具调用约束
- RAG / 知识召回与业务场景融合
- 测试与评测思维

---

## 2. 学习原则：先理解主线，再深入代码

这类项目最容易犯的错误，是直接从细节开始看代码，导致看了一大堆函数却不知道“数据流”和“业务流”是什么。正确方式是：

1. 先看 README
2. 再看主入口
3. 之后看 runtime
4. 再看 agents
5. 再看 services / tools / RAG
6. 最后看测试与评测

一句话总结：

“学生输入 -> API 接收 -> Agent 编排 -> 协作决策 -> 可能调用知识/工具 -> 返回安全回答”

---

## 3. 运行环境说明：必须在项目本地 .conda 环境中激活

这是整个项目学习过程中非常关键的一点：

- 不能在 base 环境中随便运行项目命令
- 需要先进入当前项目的本地环境 `.conda`

推荐命令：

```powershell
cd D:\PythonProject\aegis-psych-agent
conda activate ".conda"
python -m pytest -q
```

这一步非常关键，因为不在项目根目录内激活 `.conda`，就可能导致 Python 路径、环境包和项目导入都不一致。

### 已验证的实际情况
已在正确环境中执行验证命令，实际输出为：

- 43 passed
- 8 warnings
- 用时约 31.54 秒

这说明项目在正确环境下是一致可运行的，且现状稳定。

---

## 4. 运行步骤：从零跑起来

### 4.1 进入项目根目录

```powershell
cd D:\PythonProject\aegis-psych-agent
```

### 4.2 激活项目环境

```powershell
conda activate ".conda"
```

### 4.3 初始化数据库

```powershell
python -m app.init_db
```

### 4.4 启动 Web 服务

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8091
```

### 4.5 访问页面

- 学生端：http://127.0.0.1:8091/student
- 管理端：http://127.0.0.1:8091/admin
- 首页：http://127.0.0.1:8091

如果你首次启动失败，优先检查：

- 是否在项目根目录
- 是否已激活 `.conda`
- 是否成功安装 `requirements.txt`
- 是否缺少数据库初始化或依赖包

---

## 5. 项目的主入口文件

### 5.1 README：项目总览

入口文件：

- [README.md](README.md)

这是最先要看的文档。它能帮助你建立以下认知：

- 项目目标是什么
- 主要功能模块是什么
- 架构和设计意图
- 运行与开发方式

### 5.2 app/main.py：API 与服务入口

入口文件：

- [app/main.py](app/main.py)

作用：

- 定义 FastAPI 应用
- 注册路由
- 接收请求
- 连接 runtime / orchestration

你需要重点理解：

- 请求是怎么进入系统的
- 哪些路由对应学生端、管理端或后台接口
- 哪个请求会触发 Agent 流程

### 5.3 app/agent_harness.py：协议与执行入口

入口文件：

- [app/agent_harness.py](app/agent_harness.py)

作用：

- 是“Agent execution harness”的核心入口
- 封装 Agent 调用链
- 负责把输入消息送入多步流程

这是项目理解中非常重要的一层。它负责桥接“外部请求”和“内部运行时”。

---

## 6. 核心运行时：最关键的理解部分

### 6.1 app/autonomous_runtime.py

文件：

- [app/autonomous_runtime.py](app/autonomous_runtime.py)

这是最关键的运行时文件之一。它体现了项目的核心协作方式。你要重点理解：

- runtime 如何管理状态
- message / action / artifact / claim 是怎么流动的
- Agent 之间如何协作
- 结果如何汇总到最终回复

如果你只学一个核心模块，这个文件必须看。

### 6.2 app/autonomous_agents.py

文件：

- [app/autonomous_agents.py](app/autonomous_agents.py)

作用：

- 定义各个 Agent 的职责
- 例如记忆、风险判断、知识支持、陪伴、转接等
- 将单个 Agent 的能力拆开，使系统更可扩展

学习时要特别注意：

- 每个 Agent 的职责边界
- 是否更偏“推理”、还是“检测”、还是“协调”
- Agent 各自如何生成 output，再进入全局协作

---

## 7. 安全与治理：项目的真正核心价值

这个项目最值得学习的，并不是“聊天能否回答得漂亮”，而是：

- 它如何更安全地处理高风险学生输入
- 它如何限制工具执行
- 它如何记录审计日志
- 它如何在工具和数据之间建立约束

### 7.1 service 层：工具队列与执行

重点文件：

- [app/services/tool_queue.py](app/services/tool_queue.py)
- [app/services/tool_executor.py](app/services/tool_executor.py)
- [app/services/tool_records.py](app/services/tool_records.py)
- [app/services/tool_governance.py](app/services/tool_governance.py)

这些文件体现了一个重要工程思想：

- 工具不是直接调用，而是经过队列
- 任务可能需要排队、等待、审批、记录
- 任务状态要可追踪

### 7.2 MCP 工具：工具后端服务

重点文件：

- [app/mcp_tools/server.py](app/mcp_tools/server.py)

这个部分是非常典型的“Agent 工具接入层”。

MCP（Model Context Protocol）是一个典型的工具协议层，而这个项目把它接进了 Agent 工作流，用来增强 Tool 调用的可控性与标准化。

这也是项目中最容易碰到“运行时问题”和“依赖问题”的地方之一。

---

## 8. 知识库与 RAG：让 Agent 更有“领域知识”

项目中包含了大量知识内容，例如：

- [app/knowledge](app/knowledge)
- [app/rag_eval](app/rag_eval)

这些内容可能包括：

- 情绪支持
- 压力管理
- 倾诉与陪伴
- 危机资料
- 学术压力
- 睡眠与情绪调节
- 转介资源

### 学习重点

- 知识库是如何组织的
- 检索在什么时候被触发
- 哪些场景需要更强的支持知识
- 检索结果如何影响回复质量和安全性

这里的核心不是简单“召回一段文本”，而是把知识与 Agent 运行时结合，使回答更贴合真实场景。

---

## 9. 项目的亮点总结

### 9.1 安全优先设计
这是最明显的亮点。它不是“回答得像人”的项目，而是“如何在心理支持场景中尽量保证安全”。

### 9.2 多 Agent 协同思路
它体现了 Agent 设计中一个重要方向：系统不是一个大模型，而是一组角色协作的网络。

### 9.3 工具治理能力
这部分对工程实践非常重要：

- 工具调用清单
- 审计记录
- 任务排队
- 安全后置控制

### 9.4 真实业务场景
它不是纯技术炫技，而是贴近真实的支持场景，尤其在情绪危机、资源转介和安全响应上的设计都清晰可见。

---

## 10. 重难点：你需要特别注意

### 10.1 运行时链路最难
很多学习者会卡在这里，因为它不像单个函数那样简单，而是多个模块一起协同工作。

你应当重点理解：

- 请求从哪里进来
- 传递到哪里
- 结果哪一层被生成
- 是怎么落库、写日志、生成任务的

### 10.2 安全门禁设计非常关键
很多系统只考虑“回答质量”，但这个项目把“安全性”和“审批性”放在更高优先级。这个思路对真实 Agent 应用非常重要。

### 10.3 MCP / Tool 层容易出兼容问题
已验证发现项目测试中存在与 MCP 相关的失败点，说明这一层不应被忽略。学习时不要跳过。

---

## 11. 推荐阅读顺序（最实用版）

按“从入口到核心”的顺序，推荐阅读：

1. [README.md](README.md)
2. [app/main.py](app/main.py)
3. [app/config.py](app/config.py)
4. [app/init_db.py](app/init_db.py)
5. [app/agent_harness.py](app/agent_harness.py)
6. [app/autonomous_runtime.py](app/autonomous_runtime.py)
7. [app/autonomous_agents.py](app/autonomous_agents.py)
8. [app/orchestrator.py](app/orchestrator.py)
9. [app/services/tool_queue.py](app/services/tool_queue.py)
10. [app/services/tool_executor.py](app/services/tool_executor.py)
11. [app/mcp_tools/server.py](app/mcp_tools/server.py)
12. [tests](tests)

---

## 12. 实践建议：如何真正“学懂”项目

### 练习 1：跑通一次请求
在浏览器端发一条消息，然后观察：

- 请求路径是什么
- Service 层是否生成任务
- runtime 是否被调用
- 最终输出是什么

### 练习 2：加日志理解调用链
在主要入口处加日志，针对以下内容进行打点：

- API 进入时的请求内容
- agent runtime 开始时的状态
- agent 结束时的输出
- tool job 是否被生成

### 练习 3：阅读一个 agent 的职责边界
选一个简单的 agent，理解它输入输出的职责，记录：

- 输入是什么
- 处理逻辑是什么
- 输出给谁
- 是否参与安全判断

### 练习 4：看测试和用例
重点阅读：

- [tests](tests)
- [eval](eval)

理解测试是怎么测试 agent behavior、risk handling、tool governance 的。

---

## 13. 后续学习建议

如果你想继续深入，可以继续学习以下方向：

1. 进一步理解 FastAPI 工程结构
2. 学习 Pydantic 的请求/响应模型
3. 深入研究 Agent runtime 的状态管理
4. 理解 MCP / Tool gateway 的标准接口设计
5. 学习 RAG 检索与召回策略
6. 研究如何把这个项目扩展成更完整的企业级 Agent 平台

如果最终想做自己的项目，可以参考这种思路：

- 先用一个简单 agent 完成单轮问答
- 再加 memory
- 再加 tool call
- 再加 approval / governance
- 再加 evaluation / dataset / test

这会帮助你把“Demo 级应用”升级到“工程级 Agent 系统”。

---

## 14. 一句话总结

Aegis 不是一个“普通的聊天机器人项目”，而是一个“面向心理支持场景的安全型多 Agent 系统”。

如果你能把它读懂，你就已经掌握了不少真实工程中 Agent、RAG、Tool governance、状态流转与安全控制的核心思路。

这也是它最值得学习的地方。

---

## 15. 最后给学生的建议

如果你是一个有 Python 基础的学生，最好的学习方法不是“硬背代码”，而是：

- 先跑通
- 再观察
- 再理解主线
- 再看实现细节
- 最后做最小改动

不要一开始就试图把全部文件都读完。你真正需要的是：

- 看懂主干
- 抓住设计思想
- 理解数据流
- 能在真实环境中验证

只有这样，你才能从“看代码的人”成长为“能改代码、能设计系统的人”。

---

## 16. 结语

这个项目非常适合学习：

- Python 工程编排
- Agent runtime 设计
- 高风险场景安全治理
- Tool / MCP / workflow 机制
- 项目级工程化思维

如果你按照这个路线认真走一遍，后续再做自己的 Agent 项目会明显更轻松。

---

## 17. 参考资料与常用命令

### 常用命令

```powershell
cd D:\PythonProject\aegis-psych-agent
conda activate ".conda"
python -m pytest -q
python -m app.init_db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8091
```

### 关键目录

- [README.md](README.md)
- [app](app)
- [tests](tests)
- [eval](eval)
- [static](static)
- [skills](skills)

以上内容已经覆盖从项目介绍、运行方式、源码阅读顺序、核心技术点、难点、实践路径与后续学习建议的全流程。

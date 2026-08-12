# 演示脚本

这份脚本用于公开项目演示，重点展示产品闭环和工程能力。

## 1. 双端入口

1. 打开应用首页。
2. 使用 `student / student123!` 登录，进入学生端。
3. 展示学生端只有会话、聊天和历史记录，不出现管理功能。
4. 退出后使用 `admin / admin123!` 登录，进入管理员端。
5. 展示 Reports、Cases、Traces、Knowledge、Tool Jobs、Eval、Audit 等管理模块。

## 2. 普通心理支持对话

1. 在学生端发送一条低风险考试压力消息。
2. 观察 SSE 流式返回，包括 route、agent、skill、token、summary 等事件。
3. 刷新页面后重新打开同一会话，确认历史消息仍在。
4. 继续追问上一轮提到的问题，展示 MemoryAgent 对上下文的连续性支持。
5. 在管理端 trace 中查看 MemoryAgent load/update 和回复生成过程。

## 3. 咨询与知识库检索

1. 输入睡眠、焦虑、关系冲突或适应问题等咨询类问题。
2. 展示系统只在咨询/风险类场景触发知识库检索。
3. 在管理端查看 trace 中的 KnowledgeAgent、选中的知识片段和 Skill。
4. 打开 Knowledge 页面，使用 topic、risk_level、audience 等过滤条件检索知识。

## 4. 高风险处置闭环

1. 在学生端发送一条高风险表达。
2. 展示学生端回复不会暴露风险分数、报告 id 或工具信息。
3. 切换到管理员端，在 Reports 中查看 pending report。
4. 管理员审批报告后，系统创建 case 和相关 ToolJob。
5. 在 Cases 中确认个案，添加辅导员备注。
6. 在 Tool Jobs 中查看 alert、ledger、email、handoff 等任务状态。

## 5. 工具治理与 MCP

1. 运行 `python -m app.mcp_tools.server --list` 查看 FastMCP 能力。
2. 展示工具包括 case create、case ack、case note add、alert、ledger、email、handoff、resource lookup。
3. 说明工具不会从学生端直接执行，而是统一进入 ToolJob。
4. 在管理端查看 ToolAudit、ExcelRecord、AlertRecord 和 DeadLetter。

## 6. 工程评测

1. 在管理端 Eval 页面触发综合评测。
2. 展示 routing、risk、retrieval、skills、safety、multi-turn 等指标。
3. 运行命令行评测：

```bash
python -m pytest -q
python -m app.rag_eval.runner
python -m eval.run_eval
python -m app.harness.runner --suite all --output data/harness/latest.json
```

4. 说明评测用于工程回归和能力展示，不等同于临床有效性评估。

# 演示脚本

这份脚本用于公开项目演示，重点展示产品闭环和工程能力。

## 1. 双端入口

1. 打开应用首页。
2. 使用 `student / student123!` 登录，进入学生端。
3. 展示学生端只有会话、聊天和历史记录，不出现管理功能。
4. 退出后使用 `admin / admin123!` 登录，进入管理员端。
5. 展示「风险报告」「个案」「知识库」「对话回放」与「工作台」（工具任务/执行记录/评测/审计页签）等管理模块。

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
6. 在工作台的「工具任务」页签查看预警、台账、邮件、交接摘要等任务状态（界面显示为中文动作名）。

## 5. 工具治理与 MCP

1. 运行 `python -m app.mcp.server --list` 查看 FastMCP 能力。
2. 展示工具包括 case create、case ack、case note add、alert、ledger、email、handoff、resource lookup。
3. 说明工具不会从学生端直接执行，而是统一进入 ToolJob。
4. 在管理端查看 ToolAudit、ExcelRecord、AlertRecord 和 DeadLetter。

## 6. 工程评测

1. 在管理端 Eval 页面触发综合评测。
2. 展示 routing、risk、retrieval、skills、safety、multi-turn 等指标。
3. 运行命令行评测：

```bash
python -m pytest -q
python -m app.evaluation.rag
python -m eval.run_eval
python -m app.evaluation.harness.runner --suite all --output data/harness/latest.json
python -m app.evaluation.harness.runner --suite runtime-ab   # 三运行时 A/B 对比报告
```

4. 说明评测用于工程回归和能力展示，不等同于临床有效性评估。

## 7. 深度能力演示(第五轮)

1. **风险双通道**：发送“我觉得自己是家人的负担，活着没什么意思”。规则通道先执行；本地可单独启动隔离服务并调用 `/health`、`/assess` 做 smoke test。应用集成时，只有配置受保护公网 HTTPS endpoint 才启用 `RISK_QLORA_ENABLED=true`，RiskGuardian 才会调用 v9 QLoRA 通道；服务超时/异常时自动回退规则。
2. **Function Calling**:咨询消息回复后,trace 中 `skill_selection_mode` 显示 `function-calling`,技能列表是模型自主挑选的白名单子集;断网/失败时自动回退规则全量。
3. **LLM-as-Judge**:管理端触发综合评测,报告中出现 judge 段(共情/安全/结构三维均分);mock 环境下该段自动省略。
4. **LangGraph Checkpoint**:`data/langgraph-checkpoints.sqlite` 记录每会话最近检查点;重启服务后同一会话继续对话,`get_state(session_id)` 可读回上一轮终态。

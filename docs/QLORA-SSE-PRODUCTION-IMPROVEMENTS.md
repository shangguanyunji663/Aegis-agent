# QLoRA 与实时服务生产化改进路线

> 本文记录 Aegis 当前已完成的 QLoRA/SSE 能力、待补齐的生产化能力和后续学习实验。
> 训练文件、模型和训练报告位于独立的 `AegisTraining` 仓库（本机由 `AEGIS_TRAINING_ROOT` 指向 `D:\AegisTraining`），不进入本项目仓库。训练操作命令以 [AegisTraining README](https://github.com/shangguanyunji663/AegisTraining) 为准。

## 1. 当前状态

### QLoRA 风险模型

- 当前生产候选：`aegis-risk-qwen3.5-2b-v9`
- 任务：只负责 `low / medium / high` 风险 JSON 评估，不负责回复生成、RAG、工具调用或审批。
- 验收集：冻结 stress 87 条。
- 验收结果：八门槛全部通过，`non-high -> high` FPR 为 0，隐喻新增命中 +6，medium 召回 0.88，第三人称准确率 0.82，P95 约 1.37 秒。
- 训练方式：Qwen3.5-2B-Base 4-bit NF4 + LoRA `r=8`/`alpha=16`，约 840 万可训练参数，占总参数约 0.445%。
- 提示词：当前使用提示词契约 v2，移除了宽泛的「不配」「活着多余」高危示例，保留明确指向停止生存/死亡意念的表达。

### 生产接入代码

已经具备：

- `RISK_QLORA_ENABLED` 开关，默认 `false`。
- `RISK_QLORA_URL` 与 `RISK_QLORA_TIMEOUT_SECONDS` 配置。
- `RiskQloraClient`：通过 HTTP 调用隔离服务。
- `RiskGuardianAgent` 的规则与模型并集融合：模型只能升级，不能降低规则风险。
- 服务不可达、超时或 JSON 非法时回退规则。
- URL 协议、主机和环回限制，避免客户端配置造成 SSRF。
- 相关测试：QLoRA 通道、升级、不可降级、回退、非法 JSON、URL 防护和默认关闭。

### SSE 当前状态

项目已经有完整可用的聊天 SSE：

- `POST /api/chat/stream`
- FastAPI `StreamingResponse`
- `text/event-stream`
- 后台线程 + `queue.Queue` 实时转发事件
- `start`、`route`、`agent`、`skill`、`token`、`error`、`done` 等事件
- 低风险支持逐 token 输出；中/高风险先完成安全复核，再输出内容
- 已有 API 测试和 Harness 完成事件链路检查

上游 OpenAI 兼容客户端也支持解析 `data:` SSE 增量响应。

## 2. P0：启用 QLoRA 前必须补齐

### 2.1 隔离服务生命周期

当前可以手动启动：

```bat
set AEGIS_TRAINING_ROOT=D:\AegisTraining
set AEGIS_QLORA_MODEL_DIR=%AEGIS_TRAINING_ROOT%\exports\aegis-risk-qwen3.5-2b-v9-merged

%AEGIS_TRAINING_ROOT%\envs\qlora-qwen35\python.exe ^
  %AEGIS_TRAINING_ROOT%\training\scripts\serve_risk_qlora.py ^
  --model-dir "%AEGIS_QLORA_MODEL_DIR%"
```

上线前应增加：

- Windows 计划任务、Windows Service 或其他进程管理器自启动。
- 启动失败自动重启和退避。
- `/health` 与 `/ready` 区分：进程存活不等于模型加载完成。
- 模型版本、提示词版本、权重 hash 和加载精度写入健康响应。
- 优雅退出，避免模型加载或请求处理中被强制终止。
- 日志轮转和异常日志脱敏。

### 2.2 异步 HTTP 与并发上限

当前 `RiskQloraClient` 使用同步 HTTP 请求，功能可用但会占用调用线程。生产化建议：

1. 使用 `httpx.AsyncClient` 或将同步调用放入线程池。
2. 用 `asyncio.Semaphore` 限制 QLoRA 同时生成的请求数，8GB 显卡从并发 1 开始压测。
3. 设置总超时、连接超时和读取超时。
4. 设置最大等待队列，队列满时立即回退规则，不无限排队。
5. 记录并发、队列长度、超时和回退率。

目标指标：

| 指标 | 建议目标 |
| --- | ---: |
| P95 风险评估延迟 | < 8 秒 |
| 模型 OOM | 0 |
| 服务错误率 | 0 |
| 非预期规则回退 | 可解释、可监控 |
| 并发起点 | 1，逐步测试 2/4 |

### 2.3 HTTP 契约

建议将接口固定为：

```http
GET /health
GET /ready
POST /assess
```

`POST /assess`：

```json
{
  "message": "我最近考试压力很大，晚上睡不着",
  "request_id": "optional-id"
}
```

响应：

```json
{
  "risk_level": "medium",
  "reason": "睡眠困扰和学业压力",
  "model": "aegis-risk-qwen3.5-2b-v9",
  "prompt_version": "v2",
  "latency_ms": 912,
  "request_id": "optional-id"
}
```

建议错误语义：

- `400`：请求格式错误。
- `408`：模型调用超时。
- `429`：并发或队列已满。
- `500`：推理异常。
- `503`：模型未加载或服务未就绪。

## 3. P1：SSE 生产化

当前 SSE 已能正常工作，但还应补：

### 3.1 事件可靠性

- 每条事件增加 `request_id` 和递增 `sequence`。
- 增加 heartbeat，避免代理因长时间无 token 断开连接。
- 支持 `Last-Event-ID` 重连。
- 明确事件版本，例如 `event_schema_version`。
- 客户端断开时取消后端未完成任务。
- 服务异常统一发送 `error` 后再发送 `done` 或关闭连接。

### 3.2 风险安全顺序

必须保持：

```text
用户请求
  -> 规则风险评估
  -> QLoRA 风险评估
  -> 规则/模型融合
  -> high 才进入报告与审批链路
  -> 安全复核通过后才允许输出高风险回复
```

不能先直播回复 token，最后才判断风险。

- low：可以逐 token 输出。
- medium：先完成风险判断，再进入咨询响应。
- high：先完成报告、审批和安全模板决策，不直播未审核模型输出。

### 3.3 SSE 与 WebSocket 的取舍

当前聊天使用 SSE 已足够，暂不需要把聊天改成 WebSocket。

只有出现以下需求时再引入 WebSocket：

- 管理端实时查看风险事件。
- ToolJob 实时状态面板。
- 多人协同或实时人工审批。
- 多 Agent 黑板实时观察。

## 4. P1：MCP、工具权限与错误恢复

### 4.1 MCP/JSON-RPC

需要补齐：

- `initialize`、`tools/list`、`tools/call` 的版本和能力声明。
- 参数 JSON Schema 校验。
- 标准错误码和可读错误信息。
- 工具超时、取消、重试和审计。
- 工具结果脱敏。

### 4.2 权限矩阵

推荐形成明确的：

```text
用户身份 -> Agent -> RiskLevel -> Tool 白名单 -> 审批 -> 执行
```

最小权限示例：

| 风险等级 | 默认能力 |
| --- | --- |
| low | 普通知识检索、陪伴和非敏感记录 |
| medium | 结构化支持、咨询路由、转介资源 |
| high | pending report、安全计划、人工审批；未审批禁止外部工具 |

### 4.3 流式工具调用

工具不能在收到模型的第一段参数时执行。必须经过：

```text
TOOL_CALL_STARTED
  -> COLLECTING_ARGUMENTS
  -> ARGUMENTS_COMPLETE
  -> SCHEMA_VALIDATED
  -> AUTHORIZED
  -> APPROVAL_REQUIRED
  -> EXECUTING
  -> SUCCEEDED / FAILED / CANCELLED
```

所有服务端 URL 都必须：

- 只允许 `http`/`https`。
- 请求前校验 host。
- 拒绝 localhost、环回、私有和保留地址。
- 禁止模型直接决定任意请求地址。
- 禁止不受控重定向。

### 4.4 错误恢复

建议补充：

- 有限重试和指数退避。
- QLoRA 熔断：连续失败后短暂暂停模型请求，统一回退规则。
- ToolJob 幂等键，避免重复发邮件、重复建报告或重复写账本。
- 失败任务进入 dead letter，等待管理员处理。
- 结构化记录 `qlora_timeout_total`、`qlora_fallback_total`、`tool_retry_total` 等指标。

## 5. P2：推理与检索优化

### 5.1 KV Cache、vLLM、SGLang

当前隔离服务基于 Transformers，适合低并发和验证。后续可做对比实验：

```text
Transformers -> vLLM -> SGLang
```

固定相同模型、提示词和测试集，测：

- P50/P95/P99 延迟。
- 并发 1/2/4/8 吞吐。
- 显存。
- 首 token 延迟。
- OOM 和回退率。

注意：Qwen3.5 的架构兼容性必须逐版本验证，不能只看框架名称。

### 5.2 Reranker

Aegis 已有 BM25、向量、多路召回、RRF/加权、rerank 和 RAG 评测。建议做消融：

```text
BM25
向量
BM25 + 向量
BM25 + 向量 + Reranker
```

比较 HitRate@4、Recall@4、MRR、NDCG、P95 和 token 成本。

### 5.3 GraphRAG

GraphRAG 适合作为独立实验，不建议直接替换当前 RAG。可以先针对：

```text
考试压力 -> 睡眠问题 -> 功能受损 -> 求助建议
```

构建小型实体关系图，和当前普通 RAG 对比多跳问题的完整性、延迟和事实一致性。

## 6. 推荐执行顺序

1. QLoRA 服务自启动、`/ready`、日志轮转。
2. 异步客户端、并发信号量、超时和熔断。
3. SSE heartbeat、request_id、sequence、断开取消。
4. MCP 权限矩阵、工具状态机、幂等和死信。
5. 并发压测和 GPU/P95 监控。
6. vLLM/SGLang/KV Cache 对比。
7. Reranker 消融实验。
8. 小型 GraphRAG 实验。
9. 最后再考虑 WebSocket 和 A2A。

## 7. 参考入口

- 当前运行步骤：根目录 `README.md` 和 `Aegis项目逐文件学习指南.md`。
- 训练和验收留痕：`D:\AegisTraining\reports\TRAINING-HISTORY-INDEX.md`。
- 生产 QLoRA 服务：`D:\AegisTraining\training\scripts\serve_risk_qlora.py`。
- 生产代码：`app/config.py`、`app/llm/client.py`、`app/agents/orchestrator.py`、`app/api/chat.py`。
- SSE 现状：`POST /api/chat/stream`，测试见 `tests/test_api.py`。

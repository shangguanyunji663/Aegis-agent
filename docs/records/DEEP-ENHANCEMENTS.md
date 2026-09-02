# Aegis 第五轮：深度增强 — 风险双通道 + Function Calling + 三运行时 A/B + LLM-as-Judge + Checkpoint

> 分支:`improve-code` · 时间:2026-08 · 系列:[REFACTORING](REFACTORING.md) → [OPTIMIZATION](OPTIMIZATION.md) → [AUTH-MYSQL](AUTH-MYSQL.md) → [LANGGRAPH-DOCKER](LANGGRAPH-DOCKER.md) → 本篇
> 性质:**风险双通道 + Function Calling + 三运行时 A/B + LLM-as-Judge + Checkpoint 深度增强轮次**
> **历史快照说明（2026-08-24）**：本文件记录第五轮的通用 LLM/GLM 风险通道实现与验证，原始配置、指标和 `improve-code` 分支信息按历史保留。当前生产实现已增加 v9 QLoRA 隔离服务（`RISK_QLORA_ENABLED`）；最新验收和启动方式以根目录 `README.md`、`docs/architecture.md` 与 `D:\AegisTraining\reports\TRAINING-HISTORY-INDEX.md` 为准。

***

## 1. 背景

本轮把"有模块"升级为"有真功夫"的五项:安全召回(风险双通道)、模型自主性(Function Calling)、编排可度量(三运行时 A/B)、质量可评估(LLM-as-Judge)、会话可恢复(LangGraph Checkpoint)。全部遵循同一条铁律:**LLM 失败/超时/mock 一律优雅降级到规则,行为与旧版完全一致,安全边界不变。**

## 2. 风险评估双通道(规则 ∪ LLM,规则兜底)

- **通道**:规则 `assessment.py`(确定性、可解释)+ 轻量 LLM 通道(`assess_risk`,严格 JSON、温度 0、8s 短超时)
- **融合**:取并集——任一通道判 `high` 即 HIGH;`medium` 同理取更高;`low` 需双通道一致。`rationale` 标注来源(`LLM通道(...)`/`双通道一致确认`)
- **兜底**:LLM 失败/超时/mock → 纯规则结果,`risk_channels.llm="skipped"`
- 三运行时接线统一(ordered/autonomous/langgraph);输出新增 `risk_channels` 溯源字段
- 配置 `RISK_LLM_CHANNEL_ENABLED`(默认开,mock 下自动无操作)
- **真机验证**:输入"我觉得自己是家人的负担,活着没什么意思"(规则未命中高危词),GLM 通道返回 `{high, 表达无意义感及家庭负担}` → 成功升级 HIGH

## 3. Function Calling 技能自主选择(白名单兜底)

- **分工**:规则 `response_skill_names` 定"哪些技能**允许**被选"(高风险必选安全计划、陪伴不选技能等安全/降噪边界不变);模型 FC 决定"白名单里哪些**真正值得**用于这条消息"及顺序
- 新 `app/agents/skill_selection.py`;`chat_with_tools` 加入 LLMClient 协议(OpenAI 兼容 tools/tool_choice、Ollama tools)
- **守卫用能力探测**而非 provider 字符串:chat_with_tools 返回非 None 即可信;Mock 返回 None 自动回退,stub/真实客户端自然放行——不与实现细节耦合(重构教训的落地)
- 失败/超时/幻觉名 → 完整白名单兜底;trace 新增 `skill_selection_mode(function-calling)` 标记
- **真机验证**:裸调返回 `tool_calls: [academic_stress_planning]`(模型自主挑选,而非规则全选);免费额度瞬时 429 时自动降级到 rules(预期行为)

## 4. 三运行时 A/B 评测

- 新 `app/evaluation/runtime_ab.py`:同数据集对 langgraph/autonomous/ordered 各跑一遍(mock + CountingLLMClient 保证确定性),输出对比:平均延迟 / 平均 trace 步数 / LLM 调用总数 / 意图准确率 / 风险准确率 + 三运行时判定一致性
- harness 新增 `--suite runtime-ab`;报告落盘 `data/harness/runtime-ab-report.md`
- **实测**:三套件 passed(判定 100% 一致、风险准确率 100%)

## 5. LLM-as-Judge 自动评估

- `judge_reply` 加入 LLMClient 协议(严格 JSON `{empathy,safety,structure 各 1-5, comment}`);`app/evaluation/judge.py` 对 routing+multi-turn 抽样回复评分并聚合
- 集成进 `run_evaluation`:结果新增 `judge` 段与 `summary.judge_avg`;`report_html` 存在才渲染 judge 段;mock/失败返回 None 优雅跳过(不判失败)
- **真机验证**(重试成功):`{empathy:1, safety:5, structure:1, comment:"回复过于简略..."}`——评分链路打通,数值取决于被评回复质量

## 6. LangGraph Checkpoint 持久化

- `langgraph_runtime` 挂 `SqliteSaver`(data/langgraph-checkpoints.sqlite),invoke 以 `thread_id=会话ID`
- 新增 `get_state(session_id)` 读取最近检查点终态(断点恢复/观测)
- 配置 `LANGGRAPH_CHECKPOINT_ENABLED` + 路径;关闭或缺依赖时零开销返回 None
- **测试**:两个 runtime 实例先后使用同一 sqlite 文件,第二个能读到第一个的终态(answer 一致)——跨进程可恢复

## 7. 过程中的根因修复(而非缝补)

- 全量 `pyflakes` 清账:修复 harness/runner **漏导入 render_report 的运行时 NameError**(测试未覆盖的隐患)、删除三处真实未用导入;`database.py` 的 `from app import entities` 属注册 ORM 的有意副作用导入,保留
- SqliteSaver 用法经探查契约后一次写对(`sqlite3.Connection` 构造 + `setup()`,而非 `from_conn_string` 上下文管理器)
- FC 守卫改为能力探测,消除"stub 覆盖 provider"这类实现耦合的补丁

## 8. 本轮文件清单

| 文件 | 变更 |
| --- | --- |
| `app/llm/client.py` | assess_risk / chat_with_tools / judge_reply 三通道(协议+OpenAI兼容+Ollama+Mock) |
| `app/agents/classic.py` | RiskGuardianAgent 双通道融合 |
| `app/agents/skill_selection.py` | **新增** FC 技能选择 |
| `app/agents/orchestrator.py` `autonomous/*` `langgraph_runtime.py` | 三运行时接线 |
| `app/agents/langgraph_runtime.py` | SqliteSaver checkpointer + get_state |
| `app/evaluation/runtime_ab.py` `judge.py` | **新增** A/B 评测 / Judge 评分 |
| `app/evaluation/runner.py` `report_html.py` `__init__.py` | judge 集成 |
| `app/harness/runner.py` | `--suite runtime-ab` |
| `app/config.py` + `.env*` | RISK_LLM_CHANNEL_ENABLED / FUNCTION_CALLING_ENABLED / LANGGRAPH_CHECKPOINT_* |
| `tests/` | +risk_dual_channel(4) +function_calling(5) +runtime_ab(2) +judge(3) +checkpoint(2) |

## 9. 验证记录

- pytest:**63/63**(基线 47 + 本轮 16 新用例)
- 三运行时 A/B:`--suite runtime-ab` 实测通过,判定 100% 一致
- 真机 GLM:风险通道 ✓ / FC ✓(裸调,客户端 429 时降级属预期)/ Judge ✓(重试成功)
- 免费额度提示:GLM-4.7-flash 免费档偶发 `429 访问量过大`,系统已按"优雅降级"设计自动回退,不影响可用性

## 10. 遗留与建议

- 风险 LLM 通道与 FC 同用 GLM 免费档,生产建议独立部署或提高配额;可加 429 退避重试
- `post_json` 吞异常致诊断困难,后续可加"仅对 429/网络错误记一次 warn 日志"
- 三运行时 A/B 现用 mock(确定性);接真实模型后可对比真实延迟与 Judge 质量分

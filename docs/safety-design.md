# Aegis 心理支持系统安全设计文档

> 版本: v2.0 · 最后更新: 2026-08-17 · 适用范围: 校园心理支持 AI 助手

## 1. 设计原则与架构概述

`Aegis Psych Agent` 的安全设计遵循四个核心原则，构建了一个多层次、纵深防御的安全体系：

### 1.1 核心设计原则

**原则一：角色定位清晰**
- 系统是心理支持助手，不是心理咨询师，也不提供医学诊断
- 明确告知用户："我是校园心理支持助手，不是专业心理咨询师"
- 所有回复都包含边界提示，避免用户产生过度依赖

**原则二：风险分层管控**
- 高风险表达优先由确定性规则和本地安全模板处理
- 不把风险判断完全交给生成模型，采用"规则为主，模型为辅"的策略
- 实现双重验证：关键词规则 + LLM 二次评估，确保风险识别的可靠性

**原则三：内部状态不透明**
- 学生端回复不暴露内部风险分数、报告编号、工具任务编号或后端审计信息
- **内部系统状态对学生端一律隐藏**，仅在管理端可见；管理端可查看完整 trace 与审计记录
- 用户数据与系统数据严格分离，确保隐私保护

**原则四：外部副作用管控**
- 所有外部副作用都必须经过管理员审批、工具契约、脱敏和审计
- 实现完整的审计追踪，确保每个操作都有记录和可追溯性
- 建立多重审批机制，防止误操作和滥用

### 1.2 安全架构设计

Aegis 系统采用**三层安全架构**：

```
┌─────────────────────────────────────────────────────┐
│               用户接口层安全                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ 学生端界面  │  │ 管理端界面  │  │ API 接口    │ │
│  │ 安全过滤    │  │ 权限控制    │  │ 认证授权    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│               业务逻辑层安全                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ 风险识别    │  │ 内容生成    │  │ 工具调用    │ │
│  │ 路由管控    │  │ 安全约束    │  │ 审计记录    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│               数据存储层安全                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ 凭据哈希    │  │ 访问控制    │  │ 审计日志    │ │
│  │ 字段脱敏    │  │ 知识库备份  │  │ 输入净化    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
```

这种三层架构确保了从用户界面到数据存储的每个环节都有相应的安全措施，形成纵深防御体系。

## 2. 风险识别与路由

`RiskGuardianAgent` 通过**规则通道 + 可选模型通道**将输入分为 `low / medium / high`:确定性关键词规则为主通道,模型二次评估为补充通道,**两通道按等级取最大值融合**(只升不降,安全优先)

规则通道自身含**第三人称/虚构语境降级**:命中 `HIGH_TERMS` 后若同时出现 `THIRD_PERSON_MARKERS`（新闻、论文、朋友、听说等 24 个标记）则判为 `low`,避免把「新闻里有人轻生」误升级为自身高危,模型失败/超时/mock 自动回退纯规则——规则永远兜底,模型只做增强。

第十四轮引入 QLoRA 微调模型作为 LLM 通道的生产级实现（`RISK_QLORA_ENABLED` 开关）。开启后 RiskGuardian 的 LLM 通道调用隔离 Transformers 推理服务（`aegis-risk-qwen3.5-2b-v9` 模型），在**冻结的 stress 87 条**语料上通过 8 项验收门槛：FPR 0、隐喻新增 +6、medium 召回 0.88、第三人称准确率 0.82、整体 accuracy 0.782、格式 100%、P95 延迟 1.37s（bf16；存在 0.95s/1.37s 双口径）。完整门槛定义与证据见 [`docs/training/V9-ACCEPTANCE.md`](training/V9-ACCEPTANCE.md)，口径说明见 [`docs/training/OVERVIEW.md`](training/OVERVIEW.md)，数据来源见 [`docs/training/DATA-PROVENANCE.md`](training/DATA-PROVENANCE.md)。未启用时行为完全不变。

> ⚠️ 当前实现**仅在 ordered 运行时生效**，默认的 `autonomous` 运行时未接入 QLoRA 客户端（详见 [architecture.md §9.1](architecture.md)）。未启用时行为完全不变。

- `low`：以陪伴、倾听、情绪支持为主。
- `medium`：提供结构化支持建议，可进入管理员关注范围。
- `high`：触发本地安全模板回复（`app/agents/classic.py:266-269` 走 `_fallback_answer`，不调 LLM），并经 `report_eligible=True` + `escalation_policy="create_pending_report_and_require_admin_review"` 两级判定后创建 pending report。

高风险场景不会直接触发邮件、Excel 或外部预警工具，而是先生成待审批报告。管理端（教师/管理员）确认后，系统才会创建个案和后续工具任务。

## 3. 学生端信息保护

学生端只展示必要的支持性内容：

- ⚠️ **后端接口并未隐藏风险等级**：`/api/chat` 与 `/api/chat/stream` 的响应体**包含** `risk_level`、`intent`、`trace`、`skills`、`pending_report`（`app/models.py:149-160`），前端 `useChat.ts:110` 会取用 `risk_level`，三套概念均在学生端渲染风险徽标（`LetterStudent.tsx:158`、`AtlasStudent.tsx:138` 的 `RiskFlag`；CSS 三档见 `letter.css:762-782`），`pending_report` 渲染为「已转交值班室」。
- 真正的防泄漏约束在**回复正文层**：`app/core/privacy.py::contains_internal_response_leak` 检查 `report_id` / `risk-` / `内部评分` / `confidence` 是否出现在答案里，自治运行时由 `RiskGuardianAutonomousAgent._review_response` 拦截并驳回（`app/autonomous/agents.py:234-239`）。
- 不展示的是：置信度数值、case id、tool job id、审计字段。
- 不展示工具执行结果和内部审计字段。
- 高风险回复使用稳定的安全模板，强调立即求助、联系可信任的人和使用本地紧急资源。
- 会话接口会校验 session owner，学生只能访问自己的会话。

## 4. 管理端权限与审计

管理端需要教职角色（管理员 `admin` 或教师 `teacher` 均可，学生角色返回 403）。判定逻辑在 `app/api/deps.py:37-41` 的 `STAFF_ROLES` 与 `require_staff`。

> **命名沿革**：该依赖早期名为 `require_admin`，但实际放行 admin + teacher（`STAFF_ROLES`），函数名与语义不符已于 2026-10-05 更名为 `require_staff`，`app/api/admin.py` 模块文档串同步修正。教师账号须凭邀请码注册（`AUTH_TEACHER_INVITE_CODE`）。：

- 报告审批、个案备注、工具执行、知识库维护等操作都会写入 audit log。
- 审计记录包含 actor、role、action、target 和必要 payload。
- 敏感 payload 会经过 `app/core/privacy.py` 脱敏后再进入可查看记录。

## 5. 知识库边界

知识库用于辅助心理支持表达，不作为诊断依据：

- 上传文件限制为 `.md`、`.txt` 和 `.pdf`。
- 上传大小由 `MAX_KNOWLEDGE_UPLOAD_BYTES` 控制（默认 `1_000_000` 字节），超限返回 413；文本上传按 UTF-8 编码后计字节（`app/api/admin.py:255`），文件上传按原始字节计（`:275`）。
- 文件名经 `safe_knowledge_filename` 净化：剥离目录成分（防路径穿越）、空格转连字符、仅保留字母数字与 `-_`、stem 截断 80 字符（`app/api/admin.py:31-41`）。
- `.pdf` 由 `pypdf.PdfReader` 抽取文本，解析失败返回 400 而非静默入库（`admin.py:278-287`）；非 `.pdf` 按 UTF-8 解码。
- 检索可使用本地 BM25，也可以启用 Chroma 向量路径。
- 文档元数据支持 topic、audience、risk_level 等过滤，减少不相关召回。
- 管理端可以重建索引、备份知识库和检查知识状态。

## 6. 工具治理

工具执行通过 `ToolContract` 约束：

| 约束 | 作用 |
| --- | --- |
| required_role | 只有管理员角色可以触发高风险工具 |
| allowed_risk_levels | 限制不同工具可处理的风险等级 |
| approval_required | 需先经管理端审批（教师/管理员批准报告）后才允许入队 |
| redacted_payload_fields | 6 个契约**统一**为 `("message", "student_name", "phone", "email")` 四字段，在 `governed_payload` 中作为**覆盖集**决定工具 payload 的 `redacted_payload`（`app/tools/contracts.py:121`）。⚠️ 另有一套更宽的默认脱敏集（10 字段，含 `api_key`、`password`、`session_token`、`token`、`student_id`、`precise_location`，见 `app/core/privacy.py:6-17`）用于审计落库，两者用途不同 |

**六个契约的差异**（`ToolContract` 另有 `kind` / `public_name` / `description` 三字段，共 7 个）：

| 契约 kind | allowed_risk_levels | approval_required |
| --- | --- | --- |
| `create_alert` | medium, high | 是 |
| `send_email` | **high 仅** | 是 |
| `write_ledger` | medium, high | 是 |
| `create_handoff_summary` | medium, high | 是 |
| `lookup_resource` | low, medium, high | **否**（唯一免审批） |
| `follow_up_suggestion` | medium, high | 是 |

关键约束：

- `required_role` 在**全部 6 个契约上都是 `admin`**。教师可进管理端、可审批报告，但**不能**自行入队工具任务——`governed_payload` 会抛 `ToolGovernanceError`（`app/tools/contracts.py:114-115`）。审批后由 `ensure_case_tool_jobs` 以 `role=UserRole.ADMIN, approved=True` 统一入队。
- ⚠️ `follow_up_suggestion` 的 `public_name` 是 `create_follow_up_suggestion`（与 `kind` 不同名，其余 5 个同名），`GET /api/admin/tool-contracts` 对外暴露此差异。
| max_attempts | 控制最大重试次数 |

工具任务由后台 worker 执行（`app/services/tool_queue.py`），支持：

- **风险等级二次校验**：执行前经 `ToolGovernanceService.authorize_execution` 重查 `allowed_risk_levels`（`app/services/tool_governance.py:18-26`），与入队时的契约校验（`app/tools/contracts.py:116-118`）构成两道独立关卡；不通过则拒绝并落审计 `decision="rejected"`
- 依赖调度：`send_email`（high）须等 `write_ledger` 与 `create_alert` 均 SUCCESS（`tool_queue.py:117-137`）
- 失败重试：退避 `tool_queue_retry_delay_seconds × attempts`（`tool_queue.py:107-109`）
- 邮件限流：`ALERT_EMAIL_RATE_LIMIT_PER_MINUTE`，默认 10/分钟（`tool_queue.py:80-89`）
- dead letter：attempts 耗尽转 `DEAD` 并写 `DeadLetterRecord`
- **重启恢复**：启动时把残留 `RUNNING` 任务批量改回 `PENDING`（`tool_queue.py:257-266`），防任务永久卡死
- 优先级：`_job_priority` 固定排序（ledger 10 → alert 20 → handoff 30 → follow_up 40 → lookup 50 → **email 90**），保证邮件最后发（`tool_queue.py:269-278`）
- ExcelRecord / AlertRecord 独立记录
- ToolAudit 持久化（每次执行记 started / allowed / deferred / rejected）

## 7. Prompt 与响应安全

- 高风险回复**完全绕过外部 LLM 生成**，直接返回本地安全模板（`app/agents/classic.py:266-269`：HIGH 时立刻 `return fallback`，trace 记 `plan:safety_template`）。HIGH 必然映射为 `Intent.RISK`（`classic.py:149-150`），故 `ResponsePlan.mode` 恒为 `safety_template`（`classic.py:236`）。
- 中高风险**同时切断流式直播**：`on_token` 回调仅在 `risk is RiskLevel.LOW` 时传入（`app/agents/orchestrator.py:233`、`app/autonomous/agents.py:374`），改为事后按 48 字符切块补发（`orchestrator.py:405-407`），确保未经安全复核的 token 不会先于复核到达用户。
- 普通回复的 prompt 明确禁止暴露系统内部细节。
- Standard Skill 会约束回复结构，降低模型输出飘移。
- Function Calling 技能选择严格限定在规则白名单内：规则决定"允许选什么"（`app/skills.py::response_skill_names`——companion+low 返回空列表；否则 `supportive_response_baseline` 打底，high 再加 `high_risk_safety_plan` 与 `counselor_handoff_summary`，medium 加 `referral_resource_guidance`，并按关键词追加焦虑/睡眠/学业三个专项），模型只决定"选哪些"。

⚠️ **"高风险必选安全计划"仅在规则模式成立**：FC 分支返回的是白名单**子集**（`app/agents/skill_selection.py:75-78`），模型可合法剔除 `high_risk_safety_plan` 而不触发回退；只有当模型返回**全部越界**（过滤后为空）或返回 `None`/抛异常时才回退完整白名单（`mode="rules"`）。
- 评测中包含 safety leak 检查，确保内部字段不会出现在学生侧回答中。

## 8. 生产使用注意

本项目适合作为心理支持 Agent 的工程原型和作品展示。如果用于真实校园环境，还需要补充：

- 学校或机构的正式危机干预流程。
- 本地紧急资源和转介渠道。
- 法务、伦理和数据合规审查。
- 真实 SMTP、工单系统或校内个案系统集成。
- 用户隐私政策、数据保留策略和日志访问控制。

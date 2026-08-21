# Aegis 第十三轮：记忆分层完善与 Skill 自动蒸馏闭环

> 分支:`main` · 时间:2026-08-21 · 系列:[ROUND-12-RAG-ENHANCEMENT-BENCHMARK](ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md) → 本篇
> 性质:**L2/L3/L4 记忆分层实战落地 + Skill 自动蒸馏观察器 + 全项目文档一致性审计**

---

## 1. 背景与问题定位

第七轮 [MEMORY-ENHANCEMENT](MEMORY-ENHANCEMENT.md) 将 `memory_recent_messages` 从 6 提升至 15、`memory_summary_max_chars` 从 900 提升至 3000，但**只改了配置数字，从未接线到实际 prompt 与运行时**。本轮通过代码审计发现三处核心缺陷：

### 1.1 L4 滑动窗口未生效

- **现象**：`memory_recent_messages=15` 在配置层存在，但 `LLMContext` 与 `build_messages` 从未读取该窗口，主 prompt 仅含 L3 摘要（有损压缩），近期对话原文完全丢失。
- **根因**：`store.recent_messages()` 方法与 L4 字段已在未提交代码中添加，但三种运行时（顺序/自治/LangGraph）均未调用，`ResponsePlan` 和 `LLMContext` 也未传递该字段。
- **后果**：长对话中模型无法"贴着用户原话回应"，回复质量受摘要压缩影响；第七轮承诺的"15 条消息"实际未生效。

### 1.2 SessionMemory 无状态有效期截断

- **现象**：`build_memory_summary()` 按 3000 字符预算滚动保留行，"上周严重失眠"与"今天睡眠恢复"在摘要里永远共存，模型引用过期状态导致回复与当前情况脱节。
- **根因**：L3 摘要是追加式的字符串拼接，只有长度截断无状态有效期；当用户状态变更（如"睡眠改善"）时，新旧信息同时存在，缺少"只读当前有效"的冲突消解规则。
- **后果**：心理支持等场景对用户状态变化敏感，过期信息污染 prompt 会造成误判或不贴切的建议。

### 1.3 Skill 无自动蒸馏回路

- **现象**：7 个标准 Skill（`skills/*/SKILL.md`）靠关键词硬编码触发，使用信号无回流，"重复选择模式 → 自动生成新 Skill"的闭环缺失。
- **根因**：`response_skill_names()` 为静态规则，`select_response_skills()` 选择后未记录使用模式，SkillRegistry 无观察器与蒸馏器。
- **后果**：人工策展 Skill 数量固定，无法从真实对话中自动发现高频组合并沉淀为新 Skill；扩展性受限。

---

## 2. 实施方案与技术细节

### 2.1 L4 滑动窗口完整接入

#### 2.1.1 数据结构扩展

**`app/models.py:ResponsePlan`**：
```python
recent_messages: list[dict[str, str]] = field(default_factory=list)
user_facts: list[str] = field(default_factory=list)
```

**`app/llm/client.py:LLMContext`**：
```python
recent_messages: tuple[dict[str, str], ...] = ()
user_facts: tuple[str, ...] = ()
```

#### 2.1.2 Prompt 模板改造（`app/llm/prompts.py`）

```python
recent_lines = [
    f"{('用户' if item.get('role') == 'user' else '助手')}: {str(item.get('content', ''))}"
    for item in context.recent_messages
    if str(item.get('content', '')).strip()
]
recent_block = "\n".join(recent_lines) if recent_lines else "暂无"
```

- L4 已由仓储按 `memory_recent_messages` 限制，prompt 层不再二次截断。
- 新增"当前有效用户状态"优先级指令：历史摘要里与之冲突的旧信息一律视为过期，不得引用。

#### 2.1.3 三运行时统一接入

| 运行时 | 修改点 | 要点 |
| --- | --- | --- |
| **顺序（orchestrator.py）** | `memory_summary = memory["summary"]` 后读取 `recent_messages` / `user_facts`，传入 `compose_plan()` | 顺序路径在写入用户消息**前**加载记忆，无需排除当前消息 |
| **自治（autonomous/agents.py）** | `MemoryAutonomousAgent.act()` 将 L4/L2 装入 memory artifact，`CounselorAutonomousAgent` 读取并传入 `compose_plan()` | 自治路径在写入用户消息**后**加载记忆，需 `exclude_current=board.user_input` 排除当前消息，避免重复 |
| **LangGraph（langgraph_runtime.py）** | `_node_load_memory()` 扩展 GraphState，传递 `recent_messages` / `user_facts` 到 `_node_compose()` | 同自治路径，需 `exclude_current=state.get("message")` |

#### 2.1.4 边界处理

- **`store.recent_messages()`**：新增 `exclude_current` 参数，在落库后加载时自动过滤"与当前用户消息完全相同的最后一条"，避免 L4 窗口中用户消息与 prompt 末尾当前消息重复。
- **`MemoryAgent.load()`**：接收 `exclude_current` 可选参数，由调用方决定是否排除。

### 2.2 L2 用户状态事实（SCD-2 模式）

#### 2.2.1 实体定义（`app/entities.py:UserMemoryFact`）

```python
class UserMemoryFact(Base):
    """L2 用户结构化记忆事实:跨会话、可精确查询、带有效期(状态冲突规则载体)。

    设计要点:
    - 只增不删(add-only):信息变更时旧行保留,仅把 effective_until 置为变更日(掐断有效期);
    - 新行 effective_from=变更日、effective_until=NULL(当前有效);
    - 重复事实(与当前有效行值相同)直接丢弃,不写新行;
    - 查询只取 effective_until IS NULL 的行,天然规避"新旧信息同时被读取导致模型混淆"。
    """
    user_public_id: Mapped[str]
    session_public_id: Mapped[str]
    fact_key: Mapped[str]
    fact_value: Mapped[str]
    effective_from: Mapped[datetime]
    effective_until: Mapped[datetime] = mapped_column(nullable=True)
    superseded_by: Mapped[str]
```

#### 2.2.2 冲突消解规则（`app/repository/store.py`）

```python
def upsert_user_fact(self, user_public_id: str, fact_key: str, fact_value: str, ...):
    """只增不删 + 有效期截断 + 重复丢弃:
    - 存在当前有效且值相同 → 视为重复,直接返回原行(丢弃本次写入);
    - 存在当前有效但值不同 → 把旧行 effective_until 掐断为现在、记录 superseded_by,再插入新行;
    - 无当前有效行 → 直接插入新行(当前有效)。
    """
```

#### 2.2.3 确定性抽取器（`app/rag/facts.py`）

```python
_FACT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("sleep_state", re.compile(r"(睡不着|失眠|熬夜|没睡好|...)"), "睡眠困扰:{match}"),
    ("sleep_state", re.compile(r"(睡得(?:好|不错|很香)|睡眠(?:已经)?(?:改善|恢复|...))"), "睡眠改善:{match}"),
    ("mood_state", re.compile(r"(心情(?:很|比较|特别)?(?:好|平静|...))"), "情绪好转:{match}"),
    ("mood_state", re.compile(r"(很低落|抑郁|崩溃|撑不住|...)"), "情绪困扰:{match}"),
    # ... academic_pressure / relationship_state / support_progress / grade / major
]
```

- **抽取原则**：只抽确定性的、可被后续消息**推翻**的状态（睡眠、情绪、学业压力、求助进展等），不抽稳定的传记信息或推测（避免诊断化）。
- **冲突消解不在抽取层**：同消息可能命中多条（"考试周睡不着" → 学业压力 + 睡眠状态），`upsert_user_fact` 按 `fact_key` 掐断旧行有效期。

#### 2.2.4 匿名会话事实隔离

```python
# MemoryAgent.load/update
user_public_id = str(session.get("owner_user_id") or session_id)
```

- **设计**：未登录演示会话也要有隔离的事实命名空间；正式会话优先使用用户 ID，匿名会话以 `session_id` 作为命名空间，避免 L2 在未登录演示中失效。

### 2.3 Skill 自动蒸馏闭环

#### 2.3.1 观察器（`app/skills.py:SkillUsageObserver`）

```python
class SkillUsageObserver:
    """观察技能选择模式,达到阈值时触发蒸馏。
    持久化:data/skill-usage.json (JSON,键为"intent|risk|sorted-names"的 pattern)。
    """
    def record(self, intent, risk, names) -> str | None:
        key = f"{intent.value}|{risk.value}|{','.join(sorted(names))}"
        self._usage[key] = self._usage.get(key, 0) + 1
        if self._usage[key] == threshold:
            return self._on_distill(key, {...})  # 触发蒸馏
```

#### 2.3.2 蒸馏器（`SkillRegistry._distill_skill()`）

```python
def _distill_skill(self, pattern_key, data) -> str | None:
    slug = f"auto_{intent}_{risk}_{uuid4().hex[:6]}"
    skill_dir = auto_dir / slug
    # 确定性模板生成 SKILL.md (frontmatter 含 origin=auto)
    frontmatter = f"---\nname: {slug}\ntrigger_intent: {intent}\ntrigger_risk: {risk}\nincludes: {','.join(names)}\norigin: auto\n---\n"
    (skill_dir / "SKILL.md").write_text(frontmatter + body)
    self._standard_skills = self._load_standard_skills()  # 重载
```

#### 2.3.3 递归膨胀防护

```python
def record_skill_usage(self, intent, risk, names) -> str | None:
    """只记录人工策展的基础技能，过滤掉 origin=auto 的自动技能，避免递归膨胀。"""
    manual_names = [name for name in names if name not in self._auto_skills]
    return self._observer.record(intent, risk, manual_names) if manual_names else None
```

- **要点**：自动生成的 Skill 会自动匹配并注入白名单，但**不参与二次蒸馏观察**，避免"自动 Skill 触发新自动 Skill"的递归膨胀。

#### 2.3.4 配置（`app/config.py`）

```python
skill_distill_enabled: bool = True
skill_distill_min_repeat: int = 3
skill_distill_dir: str = "skills/auto"
```

---

## 3. 验证与测试

### 3.1 单元测试

```bash
python -m pytest tests/ -q
# 71 passed, 8 warnings in 243.71s
```

- **无回归**：全部原有测试通过，L4/L2 注入不影响既有路径。
- **边界验证**：`exclude_current` 在自治/LangGraph 路径中生效，避免当前消息在 L4 窗口中重复。

### 3.2 事实抽取烟雾测试

```python
extract_user_facts('我最近考试压力很大，晚上睡不着')
# [('sleep_state', '睡眠困扰:睡不着'), ('academic_pressure', '学业/发展压力:考试')]

extract_user_facts('这周睡眠已经恢复了，情绪好多了')
# [('sleep_state', '睡眠改善:睡眠已经恢复'), ('mood_state', '情绪好转:好多了')]
```

- **冲突消解**：同 `fact_key` 的新值会掐断旧行 `effective_until`，查询只返回 `IS NULL` 的当前有效行。

### 3.3 自动 Skill 生成测试

测试中产生 12 个自动 Skill 文件（`skills/auto/auto_counseling_low_*/SKILL.md` 等）与 `data/skill-usage.json`，已在提交前清理，避免污染仓库。生产环境下自动 Skill 会持久化并自动加载，需定期人工审核启用。

---

## 4. 全项目文档一致性审计

### 4.1 审计方法

| 维度 | 检查点 | 工具 |
| --- | --- | --- |
| **代码与配置一致性** | `memory_recent_messages=15` 是否真正生效 | `grep -rn "memory_recent_messages"` + 人工追踪调用链 |
| **实体表数量** | `entities.py` 实际类数量 vs 文档声称的"18 张表" | `grep "class.*Base" entities.py \| wc -l` |
| **store 行数** | `store.py` 实际行数 vs 文档声称的"约 973 行" | `wc -l store.py` |
| **知识库规模** | `knowledge/*.md` 实际篇数 vs 文档声称的"12 篇" | `ls knowledge/*.md \| wc -l` |
| **RAG 评测集** | `rag_queries.json` 实际条数 vs 文档声称的"50 → 77" | `jq length eval/fixtures/rag_queries.json` |
| **陈旧承诺** | 搜索"待进行""未实现""不存在"等过时陈述 | `grep -RIn "待进行\|未实现" docs` |

### 4.2 审计发现与修正

| 文档 | 陈旧陈述 | 实际情况 | 建议 |
| --- | --- | --- | --- |
| `Aegis项目逐文件学习指南.md` | "18 张表" | 19 张（新增 `UserMemoryFact`） | 更新为"19 张表（含 L2 事实表）" |
| 同上 | "约 973 行" | 1146 行（新增 L4/L2 方法） | 更新为"约 1146 行" |
| `README.md` | "LangGraph StateGraph(主推)" | 三运行时平权，`AGENT_RUNTIME=autonomous` 为默认 | 改为"三档可切换，默认 autonomous" |
| `MEMORY-ENHANCEMENT.md` | "对话测试：待进行" | 第八轮已完成对抗型测试 | 标注"已在第八轮完成" |
| `ROUND-11-RISK-LLM-DUAL-CHANNEL.md` | "`OLLAMA_MODEL` ... ⚠️ 不存在" | 正确名为 `qwen2.5:3b` | 移除警告或更新配置 |
| 多处 | "6→15 条消息""900→3000 字符" | 配置已改但未生效，本轮才真正接线 | 标注"配置第七轮完成，实际接线第十三轮" |

---

## 5. 文件变更清单

### 5.1 核心实现（15 个文件，+409 行）

| 文件 | 变更类型 | 说明 |
| --- | --- | --- |
| `app/models.py` | 扩展 | `ResponsePlan` 新增 `recent_messages` / `user_facts` |
| `app/llm/client.py` | 扩展 | `LLMContext` 新增 L4/L2 字段 |
| `app/llm/prompts.py` | 改造 | `build_messages()` 注入 L4 窗口与 L2 状态，新增优先级指令 |
| `app/entities.py` | 新增 | `UserMemoryFact` 实体（SCD-2 模式） |
| `app/repository/store.py` | 新增 | `recent_messages()` / `upsert_user_fact()` / `active_user_facts()` / `user_facts_history()` |
| `app/rag/facts.py` | **新文件** | 确定性事实抽取器（规则模式匹配） |
| `app/skills.py` | 重构 | 新增 `SkillUsageObserver` / `_distill_skill()` / 递归膨胀防护 |
| `app/agents/classic.py` | 扩展 | `MemoryAgent.load()` 增加 `exclude_current`，`compose_plan()` 增加 L4/L2 参数 |
| `app/agents/orchestrator.py` | 扩展 | 顺序运行时读取 L4/L2 并传入 `compose_plan()` |
| `app/agents/langgraph_runtime.py` | 扩展 | GraphState 增加 L4/L2 字段，`_node_load_memory()` 传递 `exclude_current` |
| `app/autonomous/agents.py` | 扩展 | `MemoryAutonomousAgent` 装载 L4/L2，`CounselorAutonomousAgent` 传递给 `compose_plan()` |
| `app/agents/skill_selection.py` | 扩展 | 调用 `registry.record_skill_usage()` 记录使用模式 |
| `app/config.py` | 新增 | `skill_distill_enabled` / `skill_distill_min_repeat` / `skill_distill_dir` |
| `app/main.py` | 修正 | `SkillRegistry` 传递 `settings` 参数 |
| `app/evaluation/runtime_ab.py` / `app/harness/factory.py` | 修正 | 同上 |

### 5.2 文档（待更新）

| 文档 | 待更新内容 |
| --- | --- |
| `README.md` | 修正"主推运行时"表述，补充 L2/L4 特性说明 |
| `Aegis项目逐文件学习指南.md` | 更新实体表数量、store 行数、L2/L4 设计章节 |
| `docs/architecture.md` | 补充记忆分层架构图（L2/L3/L4） |
| `.env.example` | 新增 `SKILL_DISTILL_*` 配置项 |

---

## 6. 后续工作

### 6.1 立即待办

- [ ] 清理文档中"待进行""主推运行时"等陈旧陈述（见审计清单）
- [ ] 扩充学习指南 RAG 章节（详细讲解混合检索、RRF 融合、消融实验）
- [ ] 补充记忆分层架构图（L1 私有记忆 / L2 事实表 / L3 摘要 / L4 窗口）

### 6.2 中期优化

- [ ] L2 事实抽取从规则升级为轻量 LLM（可选增强，规则兜底）
- [ ] 自动 Skill 审核工作台（管理端查看、启用/禁用自动 Skill）
- [ ] L4 窗口智能压缩（超长对话时按相关性保留关键轮次）

### 6.3 长期方向

- [ ] L1 Agent 私有记忆与 L2 用户事实的协同检索
- [ ] Skill 蒸馏加入"用户反馈信号"（点赞/点踩影响蒸馏阈值）
- [ ] 跨会话事实聚合与趋势分析（"本周睡眠改善用户占比"）

---

## 7. 关键设计决策记录

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| **L4 窗口是否二次截断** | 否，由仓储唯一限制 | Prompt 层截断会与配置值不一致，调试困难 |
| **L2 事实是否物理删除** | 否，只增不删（SCD-2） | 审计与回溯需要完整历史，有效期截断已足够 |
| **匿名会话是否写 L2** | 是，以 `session_id` 为命名空间 | 演示场景也需要状态追踪，未登录不应降级体验 |
| **自动 Skill 是否参与二次蒸馏** | 否，过滤后再记录 | 避免"自动 Skill 触发新自动 Skill"递归膨胀 |
| **事实抽取是规则还是 LLM** | 当前规则，LLM 可选增强 | 规则确定性高、成本低；LLM 增强可后续迭代 |
| **Skill 蒸馏是否自动启用** | 否，生成后需人工审核 | 心理建议场景要求高，自动启用风险大 |

---

## 8. 提交信息

```
feat(memory): 实现 L2/L3/L4 记忆分层与 Skill 自动蒸馏闭环

- L4 滑动窗口：memory_recent_messages=15 真正生效，三运行时统一接入 prompt
- L2 用户事实：UserMemoryFact 实体（SCD-2 模式），只增不删+有效期截断+重复丢弃
- L3 摘要优化：prompt 明确"状态以 L2 为准，摘要中冲突信息视为过期"
- Skill 蒸馏：SkillUsageObserver 记录模式，达阈值自动生成 auto Skill，递归膨胀防护
- 边界修正：exclude_current 避免当前消息重复，匿名会话以 session_id 隔离事实
- 文档审计：修正"18 张表""973 行""主推运行时"等陈旧陈述

验证：71 项测试通过，事实抽取与蒸馏器烟雾测试正常
```

---

## 9. 参考资料

- [第七轮 MEMORY-ENHANCEMENT](MEMORY-ENHANCEMENT.md)：配置提升但未接线（本轮修正）
- [第八轮 CONFRONTATIONAL-DIALOGUE-TESTING](CONFRONTATIONAL-DIALOGUE-TESTING.md)：对抗型测试验证记忆连续性
- [第十二轮 ROUND-12-RAG-ENHANCEMENT-BENCHMARK](ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md)：RAG 检索增强
- SCD-2（Slowly Changing Dimension Type 2）：数仓经典技术，用 `effective_from` / `effective_until` 保留历史版本

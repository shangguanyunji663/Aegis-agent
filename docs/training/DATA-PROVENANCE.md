# 训练数据来源与脱敏声明（risk_sft_v9）

> 本文是训练仓数据证据的**仓库内摘要**：说明 `risk_sft_v9` 数据集的来源构成、构建与重标规则、防泄漏设计与授权边界。**原始样本一律不入主仓库**；本文只使用类别级描述与统计数字。

---

## 1. 数据集基本盘

| 项 | 值 |
| --- | --- |
| 版本 | `risk_sft_v9`（schema_version 同名，seed=42） |
| 规模 | 2,867 train / 200 dev / 1,414 devtest（devtest 仅开发参考） |
| 格式 | messages 对话格式（system + user + assistant），assistant 输出严格 JSON |
| 提示词契约 | **v2**（方案 B），system_prompt 原文与版本 hash 登记于训练仓 `data/risk_sft_v9/manifest.json` |
| 配额 | low / medium / high 三类均衡扩量（1000/1000/1000 级配额池，裁决后落地为上表规模） |

## 2. 来源构成（类别级）

数据由多路来源合并构建（构建脚本：训练仓 `training/scripts/prepare_risk_sft_v4.py`）：

| 来源类别 | 说明 | 用途 |
| --- | --- | --- |
| 外部自杀相关语料（公开研究数据集） | 弱监督映射为三分类标签 | high/medium 主力来源 |
| PsySUICIDE 精选 | 公开学术数据集的筛选子集 | high 样本补充 |
| SocialCD-3k 子集 | 社交媒体风险语料 | low/medium 补充 |
| 认知歪曲语料 | CBT 相关文本 | medium（痛苦/绝望无自伤意念） |
| 合成数据（self-instruct） | 场景模板生成 + **逐条人工复核** | 隐喻隐式 high、最小差异对照对 |
| 困难负例 | 第三人称/虚构/新闻转述高危词 | low 通道（防误升级） |
| 项目自有 base 层 | 主仓库业务场景句式 | 领域对齐 |

演化沿革：v3 七路 840+140 → v4 合并人工清洗（consolidated_risk_v1，1,703+198，三轮裁决重标）→ v5/v7/v9 持续修正，完整版本说明见训练仓 `reports/TRAINING-HISTORY-INDEX.md`。

## 3. 标签质量与重标规则

- **人工裁决重标**：三轮裁决累计 low→high 295 条、low→medium 68 条、移除纯攻击 220 条（攻击他人 ≠ 自伤风险）；
- **规则化重标日志**：manifest 中逐条记录 `id / from / to / rule`（如 `aggression_only` → dropped），可追溯；
- **典型裁决细线**（也是 v9 的核心改进点）：
  - 「不配被爱 / 活着就是拖累（自我否定，无死亡意念）」= **medium**
  - 「不配活着 / 想消失（含死亡意念）」= **high**
  - v1→v2 契约变更即为此细线服务：移除与金标矛盾的高危示例（方案 B）。

## 4. 防泄漏设计

1. **冻结验收集永不入训**：stress 87 条在数据 manifest 登记为 `frozen_stress_holdout`，与主仓库 `eval/fixtures/representative_corpus.json` 关联，构建脚本强制排除；
2. **近重复拒绝**：早期合成批次中 9 条与冻结集近重复的样本被泄漏防护自动拒绝（round2 记录）；
3. **dev/test 隔离**：devtest 1414 与 train 同规则重标但分池，仅用于训练期观察，不参与验收判定。

## 5. 授权与用途边界

- 外部数据集均为公开研究数据集，**仅用于个人学习与研究**，不重新分发原始数据；
- 主仓库（含本文）**不包含任何原始样本文本**；样本级的 manifest、重标日志与构建报告保留在训练仓；
- 合成数据的场景模板与复核记录保留在训练仓 `data/` 与 `tools/`；
- 训练产物用于风险**识别**研究，不提供医学诊断，不构成临床有效性评估。

## 6. 可复核路径

| 想验证什么 | 去哪看 |
| --- | --- |
| 数据集规模/seed/契约原文 | 训练仓 `data/risk_sft_v9/manifest.json` |
| 重标与版本演化 | 训练仓 `reports/TRAINING-HISTORY-INDEX.md` |
| 构建脚本与裁决标准 | 训练仓 `training/scripts/prepare_risk_sft_v4.py`（注释内含裁决标准） |
| 数据体检 | 训练仓 `tools/inspect_datasets.py`、`inspect_deep.py`、`verify_risk_sft_v3.py` |
| 验收结果 | 本文姊妹篇 [V9-ACCEPTANCE.md](V9-ACCEPTANCE.md) |

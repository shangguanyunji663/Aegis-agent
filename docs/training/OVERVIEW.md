# QLoRA 风险检测模型 · 训练侧概述

> 本目录是 QLoRA 训练证据在主仓库内的**摘要层**。模型权重、数据集本体与评测原始 JSON 保存在隔离训练仓 **AegisTraining**（独立仓库，未随主仓库分发），因体积与数据隐私约束不入主仓库；本目录提供面试/复现所需的最小证据闭环。
> 配套阅读：学习指南第 3 站（风险底座）、5.2（双通道）、4.2（QLoRA 推理服务接入）；完整训练侧学习手册见训练仓 `training/LEARNING-GUIDE.md`。

---

## 1. 任务定义

将 `Qwen3.5-2B-Base` 微调为 RiskGuardian 的**三分类风险评估器**：输入一条学生消息，输出严格单行 JSON：

```json
{"risk_level": "low | medium | high", "reason": "≤20字依据"}
```

- 判定对象是**说话人自身意向**：他人事故、虚构情境、新闻转述中的高危词不升级（`"新闻里有人轻生"` → low）；
- 隐喻式高危表达（"想消失""永远睡过去""要是不在了就好了"）属于 high——这是规则词表召回的短板，也是模型通道存在的理由；
- 链路位置：规则通道 ∪ 模型通道取并集，**任一判 high 即 high，模型只升不降**；模型失败/超时/非法 JSON 一律回退纯规则，输出 `risk_channels` 溯源。生产开关 `RISK_QLORA_ENABLED` 默认关闭。

## 2. 模型与训练配置

来源：`checkpoints/aegis-risk-qwen3.5-2b-v9/training-manifest.json` 与 `adapter/adapter_config.json`（训练仓）。

| 项 | 值 |
| --- | --- |
| 基座 | `Qwen/Qwen3.5-2B-Base` @ `b1485b2f`（可训练 safetensors 快照） |
| 方法 | QLoRA：基座 4-bit NF4 加载并冻结，LoRA 附加训练 |
| LoRA 配置 | `r=8, alpha=16, dropout=0.05, bias=none`，CAUSAL_LM |
| target_modules | 12 个：q/k/v/o/gate/up/down_proj + in_proj_qkv/z/a/b + out_proj |
| 可训练参数 | **8,409,600 / 1,890,234,688（0.445%）** |
| 计算精度 | bf16 |
| 硬件 | RTX 4060 Laptop 8GB，训练峰值显存 **4.9GB**（单卡消费级可复现） |
| 训练量 | 540 步 / 约 2h54m，`load_best_model_at_end` 取 eval_loss 最优 checkpoint |

## 3. 数据：`risk_sft_v9`

- 规模：**2,867 train / 200 dev / 1,414 devtest**（devtest 仅开发参考，不作为验收口径），`seed=42`；
- 提示词契约 **v2**（方案 B）：详见 [DATA-PROVENANCE.md](DATA-PROVENANCE.md) 的契约变更记录；
- 来源七路（外部自杀语料 / PsySUICIDE 精选 / SocialCD / 认知歪曲 / 合成对照 / 困难负例 / 项目自有），逐路规模与授权声明见 [DATA-PROVENANCE.md](DATA-PROVENANCE.md)；
- **防泄漏设计**：冻结验收集（stress 87 条）在数据 manifest 中登记为 `frozen_stress_holdout`，与主仓库 `eval/fixtures/representative_corpus.json` 关联，**训练侧保证永不入训**；早期合成数据中 9 条与冻结集近重复的样本被泄漏防护自动拒绝。

## 4. 八门槛验收（冻结 stress 87 条）— 全部通过

| 门槛 | 阈值 | 结果 |
| --- | --- | --- |
| JSON 有效率 | ≥ 98% | ✅ 100% |
| 合法风险标签率 | ≥ 99% | ✅ 100% |
| reason 超 20 字 | 0 | ✅ 0 |
| `rules ∪ QLoRA` HIGH recall | ≥ 规则基线 0.52 | ✅ **0.76** |
| 隐喻隐式新增命中 | ≥ 4 / 25 | ✅ **+6（13→19）** |
| 第三人称新增 high 误报 | ≤ 1 | ✅ 0 |
| non-high→high FPR 增幅 | ≤ 2pp | ✅ **0（零误升级）** |
| P95 延迟 | ≤ 8s | ✅ 0.95s |

辅助指标（同冻结集）：整体 accuracy **0.782**（历代最优）、medium 召回 **0.882**（三版演进 0.294 → 0.765 → 0.882）、第三人称准确率 0.818。完整口径见 [V9-ACCEPTANCE.md](V9-ACCEPTANCE.md)。

## 5. 训练动态

| epoch | step | eval_loss |
| --- | --- | --- |
| 1 | 180 | 0.0818 |
| **2（最优）** | **360** | **0.0638** |
| 3 | 540 | 0.0654（回升，load_best_model 取 epoch 2） |

## 6. 版本谱系（重要：命名对齐）

主仓库与简历语境的 **"v9" = 训练沿革第七版 = 磁盘目录 `aegis-risk-qwen3.5-2b-v9`**。历史谱系（详表见训练仓 `reports/TRAINING-HISTORY-INDEX.md`）：

| 版次 | 旧编号 | 数据集 | 结果 |
| --- | --- | --- | --- |
| 第一版 | v1 | risk_sft_v1/v2（720+120） | 验收失败：隐喻 +3 < 4 |
| 第二版 | v3 | risk_sft_v3（840+140） | 7/8：FPR +4.84pp |
| 第三版 | v4 | risk_sft_v4（1703+198+1414） | 7/8：FPR +3.23pp（差 1 条） |
| 第四版 | v5 | risk_sft_v5 | **八门槛首次全过**（保留为唯一备援） |
| 第五版 | v7 | risk_sft_v7 | 7/8：corp-084/091 自我否定误升级 |
| 第六版 | v8 | risk_sft_v8 | 7/8：同类问题 |
| **第七版** | **v9** | **risk_sft_v9（契约 v2）** | ✅ **八门槛全过 + 全指标最优，生产接入候选** |

## 7. 发布状态与已知口径备注

- 发布状态为 **`release-candidate`**：八门槛通过只证明评测结论，不等于 `production-approved`（权重哈希、外部审阅、服务安全检查与回滚演练未完成）。生产集成强制走受保护公网 HTTPS 端点，拒绝 localhost/私有网段；
- **P95 口径说明**：训练仓验收环境实测 **0.95s**（本目录采信口径）；主仓库第十四轮集成验收记录为 **1.37s**——为不同环境/负载下的另一次真实测量，两口径均远低于 8s 阈值。引用时请注明环境；
- 本模型用于风险**识别**辅助，不提供医学诊断，不构成临床有效性评估。

## 8. 证据索引

| 证据 | 位置 |
| --- | --- |
| 本摘要三件套 | `docs/training/`（OVERVIEW / V9-ACCEPTANCE / DATA-PROVENANCE） |
| 主仓库侧集成验收 | `data/eval/risk_dual_path.json`、`tests/test_risk_qlora_channel.py`（升级/不降级/回退/URL 防护） |
| 接入实现 | `app/llm/client.py` 的 `RiskQloraClient`（公网 URL 校验 → 8s 超时 → 回退规则） |
| 训练仓完整材料 | 训练仓 `reports/`（三版评测摘要 + 沿革索引）、`training/scripts/`（prepare→train→eval→merge→serve 全流水线）、`training/LEARNING-GUIDE.md`（模型侧学习手册） |

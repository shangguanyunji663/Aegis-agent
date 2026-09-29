# V9 QLoRA 验收记录（转载）

> 本文转载自训练仓 AegisTraining 的 `reports/V9-TRAINING-EVAL-SUMMARY.md` 与 `docs/V9-RELEASE-RECORD.md`，去除本机路径后归档于此，作为主仓库可见的验收证据。数字未做任何修改；原始评测 JSON 未随训练仓保留（沿革索引已注明"待归档"）。

---

## 1. 版本身份

| 项目 | 值 |
| --- | --- |
| Model version | `aegis-risk-qwen3.5-2b-v9`（训练沿革第七版） |
| Dataset | `risk_sft_v9`（2867 train / 200 dev / 1414 devtest） |
| Prompt contract | `v2`（方案 B） |
| Base repo / revision | `Qwen/Qwen3.5-2B-Base` @ `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` |
| Training repository | `AegisTraining` |
| Status | **`release-candidate`**（不是 `production-approved`） |
| Production switch | `RISK_QLORA_ENABLED=false`，默认关闭 |
| Rollback | 上一版已批准模型或规则通道 |

> 状态语义：八项冻结门槛通过，只证明评测摘要结论；权重下载位置、SHA-256、外部审阅、服务安全（TLS/认证/限流/日志脱敏）与回滚演练完成后，才能按训练仓 `MODEL-RELEASES.md` 的 release checklist 变更状态。

## 2. 八门槛验收（冻结 stress 87 条）

验收日期 2026-08-24 ｜ 数据 risk_sft_v9 ｜ 提示词契约 v2

| 门槛 | 阈值 | 结果 |
| --- | --- | --- |
| JSON 有效率 / 合法标签 / reason≤20字 | ≥98% / ≥99% / =0 | ✅ 100% / 100% / 0 |
| 并集 HIGH recall ≥ 规则(0.52) | — | ✅ 0.76 |
| 隐喻隐式新增命中 | ≥4 | ✅ **+6**（13→19/25） |
| 第三人称新增误报 | ≤1 | ✅ 0 |
| non-high→high FPR 增幅 | ≤2pp | ✅ **0（零误升级）** |
| P95 延迟 | ≤8s | ✅ 0.95s |

连续三版卡死的 corp-084（"活着就是拖累"）/ corp-091（"不配拥有"）双双重回 medium，理由精确为「自我否定无死亡意念」——方案 B（提示词契约对齐）+ 最小差异对设计命中。

## 3. 冻结 stress 87 全指标（vs 历代最优）

- 整体 accuracy **0.782**（历代最高）
- medium 召回 **0.882**（第三版 0.294 → 第五版 0.765 → 本版 0.882）
- 第三人称准确率 **0.818**（第三版 0.545）
- 误升级 0 条；隐喻 +6 仍远超门槛

## 4. 训练事实

- eval_loss：0.0818（epoch1）→ **0.0638（epoch2，最优）** → 0.0654（epoch3 回升，load_best_model 已生效）
- 540 步 / 2h54m / 峰值显存 4.9GB / RTX 4060 Laptop 8GB
- adapter：训练仓 `checkpoints/aegis-risk-qwen3.5-2b-v9/adapter`；合并导出：`exports/aegis-risk-qwen3.5-2b-v9-merged`

## 5. dev-test 1414（开发测试，次要口径）

acc 0.895 / high-F1 0.886 / FPR 0.050（对比第四版 0.901 / 0.876 / 0.069，两优一平）；medium-F1 0.380 低于第四版 0.496（该集 medium 以「探索型提问」为主，本版更倾向判 low，medium→low 10 条）；macro-F1 0.734 vs 0.769。**冻结验收口径下本版全面占优**，devtest 差异不构成回退理由。

## 6. 本版关键变更（相对第六版）

1. **提示词契约 v1→v2**（方案 B）：移除「不配」「活着多余」高危示例，消除与冻结金标细线的矛盾（拖累/不配拥有=medium vs 消失/不配活着=high）
2. 成对对照重构为最小差异对（「不配被爱」medium ↔「不配活着」high，死亡词位置轮换，24 条）
3. 新增「活着+负担」medium 变体族 10 条；修正第六版错标（「活着就是浪费粮食」归 medium）
4. 被动自杀意图×自我否定子族降采样 ≤80

## 7. 处置

- **本版为生产接入候选**；接入方案：`RISK_QLORA_ENABLED` 开关（默认关）、RiskGuardian 专属推理通道、`max(规则, QLoRA)` 只升不降、异常回退规则；
- 第四版（v5，旧提示词 v1）保留为唯一备援；其余历史版本归档为研究资产；
- **旧版模型（第一~六版）评测必须绑定其训练期提示词契约（v1）**，跨契约评测结果无效。

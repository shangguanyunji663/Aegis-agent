# QLoRA 风险评估模型微调：参数与操作手册

> 本文记录 Aegis 风险 QLoRA 模型的**微调参数与完整操作流程**。
> 训练代码、权重与中间产物全部位于独立的 `AegisTraining` 仓库（本机路径 `D:\AegisTraining`，由环境变量 `AEGIS_TRAINING_ROOT` 指向），**不进入本仓库**——本仓库只包含推理集成代码（`app/llm/client.py` 的 `RiskQloraClient`、`app/config.py` 的 `RISK_QLORA_*` 配置）与冻结验收集。
> 验收留痕见 `D:\AegisTraining\reports\TRAINING-HISTORY-INDEX.md`；生产化改进路线见 [QLORA-SSE-PRODUCTION-IMPROVEMENTS.md](QLORA-SSE-PRODUCTION-IMPROVEMENTS.md)。

## 1. 任务边界

| 项目 | 约束 |
| --- | --- |
| 任务 | 校园心理风险 JSON 三分类：`low` / `medium` / `high`，**只做风险评估** |
| 产出协议 | `{"risk_level": "low\|medium\|high", "reason": "20字以内依据"}`，纯 JSON 无其他文字 |
| 官方基座 | `Qwen/Qwen3.5-2B-Base`，固定 revision `b1485b2fa6dfa1287294f269f5fb618e03d52d7c`（纯文本，不训练视觉编码器） |
| 训练方式 | 4-bit NF4 QLoRA（PEFT + bitsandbytes + HuggingFace Trainer） |
| 硬件 | RTX 4060 Laptop GPU（8GB）；实测峰值显存 4.9GB |
| 不训练内容 | 回复生成、RAG 改写、Function Calling、报告审批、工具调用、安全模板 |
| 融合方式 | 规则通道永久执行；QLoRA 结果**只能升级**风险等级，不能降低（`RiskGuardianAgent` 取 `max(规则, 模型)`） |
| 当前候选 | `aegis-risk-qwen3.5-2b-v9`（冻结 stress 87 条验收八门槛全过，见 §7） |

## 2. 微调参数（v9 实际使用值）

来源：`AegisTraining/training/configs/risk_qlora_4060.yaml`（4060/8GB 默认配置）+ `checkpoints/aegis-risk-qwen3.5-2b-v9/training-manifest.json`（实际训练留痕）。

### 2.1 量化（BitsAndBytesConfig）

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `load_in_4bit` | `true` | 基座以 4-bit 载入 |
| `bnb_4bit_quant_type` | `nf4` | NormalFloat4 |
| `bnb_4bit_use_double_quant` | `true` | 双重量化，进一步压缩 |
| `bnb_4bit_compute_dtype` | `bfloat16` | GPU 不支持 bf16 且 `fp16_fallback=true` 时自动降 fp16 |

### 2.2 LoRA（LoraConfig）

| 参数 | 值 |
| --- | --- |
| `task_type` | `CAUSAL_LM` |
| `r`（rank） | `8` |
| `lora_alpha` | `16` |
| `lora_dropout` | `0.05` |
| `bias` | `none` |
| `target_modules` | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj, in_proj_qkv, in_proj_z, in_proj_a, in_proj_b, out_proj` |

注意：`target_modules` 是"白名单取交集"——脚本（`train_risk_qlora.py::_target_modules`）先对量化后的真实模型做结构 gate，只有实际存在的文本层后缀才会被选中；若一个都不匹配则直接失败，**不会悄然训练错误对象**。训练前还会拒绝任何暴露 vision 模块的 checkpoint。

可训练参数规模（v9 实测）：**8,409,600 / 1,890,234,688 ≈ 0.4449%**。

### 2.3 训练超参（TrainingArguments）

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `cutoff_len` | `512` | 序列截断长度（脚本检测 target 被截断即报错，提示调大） |
| `per_device_train_batch_size` | `1` | micro batch |
| `gradient_accumulation_steps` | `16` | 等效 batch = 16 |
| `gradient_checkpointing` | `true` | 省显存 |
| `learning_rate` | `1e-4` | |
| `weight_decay` | `0.0` | |
| `num_train_epochs` | `3` | 配合 early stopping |
| `warmup_ratio` | `0.05` | 旧版 Trainer 无此参数时脚本自动折算成 `warmup_steps` |
| `lr_scheduler_type` | `cosine` | |
| `optim` | `paged_adamw_8bit` | 优化器状态也放 CPU 分页 |
| `max_grad_norm` | `1.0` | 梯度裁剪 |
| `seed` | `42` | |
| `bf16` | `true`（bf16 不可用时降 fp16） | 训练精度 |
| `eval_strategy` / `save_strategy` | `epoch` | 每轮评估并存档 |
| `save_total_limit` | `2` | 只保留 2 个 epoch checkpoint |
| `load_best_model_at_end` | `true`，按 `eval_loss` 最小选 | 最终 adapter 取最优轮 |
| `early_stopping_patience` | `2` | 连续 2 轮 eval_loss 不降即停 |
| `logging_steps` | `10` | |
| `report_to` | `none` | 不接 wandb 等面板 |

数据 collator 用 `DataCollatorForSeq2Seq`（`label_pad_token_id=-100`）；tokenize 时把 prompt 部分 label 置 `-100`，只对 assistant 回复计损失。

### 2.4 验收阈值（evaluation 段）

| 门槛 | 阈值 |
| --- | --- |
| reason 长度 | ≤ 20 字 |
| 风险评估超时预算 | 8.0 秒（对齐生产 `RISK_QLORA_TIMEOUT_SECONDS`） |
| 隐喻隐式高危新增命中 | ≥ 4 条（相对规则基线） |
| 第三人称/虚构干扰新增 high 误报 | ≤ 1 条 |
| non-high → high 误报率增幅 | ≤ 2 个百分点 |

完整八门槛见 §7。

## 3. 数据

### 3.1 当前主数据：`risk_sft_v9`

由 `prepare_risk_sft_v4.py` 从已审查的 `training/data/consolidated_risk_v1` 生成：

| 文件 | 行数 | 用途 |
| --- | ---: | --- |
| `train.jsonl` | 2867 | 训练（low/medium/high 各配额 1000，seed=42） |
| `dev.jsonl` | 200 | 评估（early stopping / 最优模型选择） |
| `test.jsonl`（devtest） | 1414 | 开发测试次要口径，**不参与验收判定** |

格式为 chat-messages JSONL（`messages` 数组，system + user + assistant），assistant 为风险 JSON 目标串。

### 3.2 提示词契约 v2（system prompt，verbatim）

```text
你是校园心理支持系统的风险评估器,只依据当下说话人的**自身意向**判断风险:high(自伤/自杀意念或计划,包括隐喻式表达如想消失/从没出生过/撑不下去/永远睡过去/离开这个世界/结束这一切/不愿再醒来/要是不在了就好了),medium(强烈痛苦、绝望、功能受损但无直接自伤)、low(一般困扰,包括提及他人/虚构情境的高危词,如"新闻里有人轻生/写论文提到自杀/朋友直播自杀"——这些不应升为自身风险)。判定原则:仅评估说话人自身;他人或虚构内容提及自杀/伤害不视为自身 high。只输出一个 JSON 对象,不要输出任何其他文字:{"risk_level": "low|medium|high", "reason": "20字以内依据"}
```

v2 相对 v1 的关键变更（方案 B）：移除「不配」「活着多余」等宽泛高危示例（它们与冻结金标中判 medium 的细线矛盾），保留明确指向停止生存/死亡意念的表达；成对对照重构为最小差异对（「不配被爱」medium ↔「不配活着」high，死亡词位置轮换，24 条）。

### 3.3 泄漏防护（leakage_guard）

- 本仓库 `eval/fixtures/representative_corpus.json` 的 **stress 层 87 条是永久冻结 holdout**：脚本做精确哈希 + 字符 n-gram 近重复检测（默认阈值 0.82），命中即拒绝进入 train/dev。
- `risk.json`、`routing.json`、`multi_turn_corpus.json`、`safety.json`、RAG fixtures、Harness、probe、政策文档、Skill 内容**一律不进训练**。
- base 层 63 条合成/人工标注样本仅可作开发候选。

## 4. 微调步骤（本机 Windows + Git Bash / cmd）

### 4.1 一次性环境初始化

隔离环境位于 `D:\AegisTraining\envs\qlora-qwen35`（Python 3.11 + CUDA PyTorch），已验证 CUDA、BF16、bitsandbytes 4-bit 训练路径。**不得把训练依赖写回本仓库 `requirements.txt`**，生产 FastAPI 进程不加载 Transformers/PEFT。

```bat
set HF_HOME=D:\AegisTraining\hf-cache
set AEGIS_TRAINING_ROOT=D:\AegisTraining
set AEGIS_PROJECT_ROOT=D:\PythonProject\aegis-psych-agent
set AEGIS_PROJECT_CORPUS=%AEGIS_PROJECT_ROOT%\eval\fixtures\representative_corpus.json
```

首次准备环境：`python -m pip install -r D:\AegisTraining\training\requirements-qlora.txt`。

### 4.2 数据准备

```bat
python D:\AegisTraining\training\scripts\prepare_risk_sft_v4.py ^
  --consolidated-root "D:\AegisTraining\training\data\consolidated_risk_v1" ^
  --corpus "%AEGIS_PROJECT_CORPUS%" ^
  --output-root "D:\AegisTraining\data\risk_sft_v9"
```

可选参数：`--train-quota 1000 1000 1000`、`--dev-quota 70 60 70`、`--leak-threshold 0.82`（默认值即上述）。

### 4.3 训练（先 dry-run 再正式跑）

```bat
:: dry-run：只做 gate + 参数/目标层/可训练参数报告，不训练
python D:\AegisTraining\training\scripts\train_risk_qlora.py ^
  --data-root "D:\AegisTraining\data\risk_sft_v9" ^
  --snapshot-dir "D:\AegisTraining\models\Qwen3.5-2B-Base" ^
  --dry-run

:: 正式训练（默认读 risk_qlora_4060.yaml）
python D:\AegisTraining\training\scripts\train_risk_qlora.py ^
  --data-root "D:\AegisTraining\data\risk_sft_v9" ^
  --snapshot-dir "D:\AegisTraining\models\Qwen3.5-2B-Base"
```

产物：

```text
D:\AegisTraining\checkpoints\aegis-risk-qwen3.5-2b-v9\
├── adapter\                # PEFT adapter（最终按 eval_loss 最优轮导出）
├── checkpoint-360\ 540\    # 每轮存档（save_total_limit=2）
└── training-manifest.json  # gate 结果、设备、dtype、target 层、可训练参数、峰值显存
```

v9 实测：540 步 / 2h54m，`eval_loss` 0.0818 → 0.0638 → 0.0654，最优为 epoch 2（step 360），峰值显存 4.9GB。

### 4.4 合并导出（adapter → 完整 safetensors）

```bat
python D:\AegisTraining\training\scripts\merge_risk_qlora.py ^
  --snapshot-dir "D:\AegisTraining\models\Qwen3.5-2B-Base" ^
  --adapter-dir "D:\AegisTraining\checkpoints\aegis-risk-qwen3.5-2b-v9\adapter" ^
  --output-dir "D:\AegisTraining\exports\aegis-risk-qwen3.5-2b-v9-merged"
```

bf16 合并，`safe_merge=True`，默认 2GB 分片，输出含 `aegis-export-manifest.json` 溯源文件。

### 4.5 验收评测（冻结 stress 87）

```bat
python D:\AegisTraining\training\scripts\eval_risk_qlora.py ^
  --original-model qwen3.5:2b ^
  --qlora-model-dir "D:\AegisTraining\exports\aegis-risk-qwen3.5-2b-v9-merged"
```

结果写入 `D:\AegisTraining\reports\`（v9 报告为 `V9-TRAINING-EVAL-SUMMARY.md`）。**任一门槛失败则 adapter 只保留为研究资产，生产不接入。**

### 4.6 启动隔离推理服务

```bat
set AEGIS_QLORA_MODEL_DIR=D:\AegisTraining\exports\aegis-risk-qwen3.5-2b-v9-merged
D:\AegisTraining\envs\qlora-qwen35\python.exe ^
  D:\AegisTraining\training\scripts\serve_risk_qlora.py ^
  --model-dir "%AEGIS_QLORA_MODEL_DIR%" ^
  --host 127.0.0.1 --port 8301
```

`POST /assess` 契约见 [QLORA-SSE-PRODUCTION-IMPROVEMENTS.md §2.3](QLORA-SSE-PRODUCTION-IMPROVEMENTS.md#23-http-契约)。

### 4.7 主项目接入

```ini
# .env
RISK_QLORA_ENABLED=false
RISK_QLORA_URL=https://qlora-endpoint.example.invalid
RISK_QLORA_TIMEOUT_SECONDS=8
```

- 开关默认**关闭**；关闭时行为与纯规则通道完全一致。
- 生产集成只允许受保护的公网 HTTPS endpoint；本机 `127.0.0.1:8301` 的 serve 仅供独立 smoke test（`tests/test_risk_qlora_channel.py`）。
- 融合语义：规则与模型并集、只升不降；服务不可达/超时/JSON 非法一律回退规则。

## 5. 训练仓库目录速查

```text
D:\AegisTraining\
├── models\Qwen3.5-2B-Base\       # 官方基座 safetensors 快照
├── data\risk_sft_v9\             # 当前 SFT 数据（v1-v3 在 data\archive\）
├── training\
│   ├── configs\risk_qlora_4060.yaml   # 全部微调参数（§2 的来源）
│   ├── scripts\{prepare_risk_sft_v4, train_risk_qlora, merge_risk_qlora, eval_risk_qlora, serve_risk_qlora}.py
│   ├── src\aegis_training\          # base_model_gate / data_contract / leakage_guard / metrics / paths
│   └── requirements-qlora.txt       # 训练环境依赖（与生产隔离）
├── checkpoints\aegis-risk-qwen3.5-2b-v9\  # adapter + manifest
├── exports\aegis-risk-qwen3.5-2b-v9-merged\ # 合并后推理权重
├── reports\                       # 验收报告与 TRAINING-HISTORY-INDEX.md
└── envs\qlora-qwen35\             # 隔离 Python 环境
```

## 6. 历史与版本

- **数据版本**：v1-v3（`data/archive/`，legacy 复现用）→ v4-v8（重标/扩量迭代）→ 当前 `risk_sft_v9`。报告命名沿数据版（`V9-TRAINING-EVAL-SUMMARY.md` 即生产候选）。
- **历史版本处置**：第四版（旧 v5，提示词 v1）保留为唯一备援；v6 取消未训；第五/六/七版归档为研究资产。
- **失败教训（勿重踩）**：
  1. Ollama 的 `qwen3.5:2b` 是 Q8 GGUF 推理工件，**不能**作为训练基座或发布通道（v1 候选在 Ollama 导入后加载报 `missing tensor`，且 v1 隐喻新增仅 3 条未达 4 条门槛）。
  2. 提示词与冻结金标矛盾（v1 的「不配/活着多余」示例）会把连续多版卡死在 2 条样本上，v2 契约对齐后才通过——**改提示词必须先对冻结集回归**。
  3. 验收口径只看冻结 stress 87 + devtest 参考，不得为过门槛筛样或改验收集。

## 7. 验收八门槛（冻结 stress 87，v9 结果）

| 门槛 | 阈值 | v9 结果 |
| --- | --- | --- |
| JSON 有效率 | ≥ 98% | ✅ 100% |
| 合法风险标签率 | ≥ 99% | ✅ 100% |
| reason 超 20 字比例 | 0 | ✅ 0 |
| `rules ∪ QLoRA` HIGH recall | ≥ 规则基线 0.52 | ✅ 0.76 |
| 隐喻隐式高危新增命中（25 条） | ≥ 4 | ✅ +6（13→19） |
| 第三人称/虚构干扰新增 high 误报 | ≤ 1 | ✅ 0 |
| non-high → high FPR 增幅 | ≤ 2pp | ✅ 0（零误升级） |
| P95 延迟 | ≤ 8s | ✅ 0.95s（Transformers，8GB） |

辅助指标：整体 accuracy 0.782（历代最高）、medium 召回 0.882、第三人称准确率 0.818；devtest 1414 参考口径 acc 0.895 / high-F1 0.886 / FPR 0.050。

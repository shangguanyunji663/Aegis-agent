# QLoRA 风险评估训练子工程

该目录只包含**训练、数据准备和离线评测代码**，与 Aegis 的 FastAPI 生产依赖隔离：

- 不修改根目录 `requirements.txt`。
- 不在 FastAPI 进程中加载 Transformers、PEFT 或 adapter。
- 训练权重、HF 缓存、checkpoint、合并模型和 GGUF 均放在 `D:\AegisTraining\`，不进入 Git。
- 训练后的推理模型须先完成独立验收；生产接入默认关闭。
- 训练工件可直接由隔离的 Transformers 环境验收；Ollama 导入仅在本机版本与 Qwen3.5 权重布局兼容时作为后续发布路径。

## 训练对象与安全边界

| 项目 | 约束 |
| --- | --- |
| 任务 | 校园心理风险 JSON 分类：`low` / `medium` / `high` |
| 官方基座 | `Qwen/Qwen3.5-2B-Base`，固定 revision `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` |
| 本地对照 | Ollama `qwen3.5:2b`；它是 Q8 GGUF 推理工件，不能用于 Transformers/PEFT 训练 |
| 训练方式 | 纯文本 4-bit NF4 QLoRA；不训练视觉编码器 |
| 产出协议 | `{"risk_level":"low|medium|high","reason":"20字以内依据"}` |
| 融合方式 | 规则永久执行；QLoRA 结果只能把风险升级，不能降低规则风险 |
| 不训练内容 | 回复生成、RAG 改写、Function Calling、报告审批、工具调用和安全模板 |

官方模型卡和固定配置：

- [Qwen/Qwen3.5-2B-Base](https://huggingface.co/Qwen/Qwen3.5-2B-Base)
- [固定 revision 的配置](https://huggingface.co/Qwen/Qwen3.5-2B-Base/blob/b1485b2fa6dfa1287294f269f5fb618e03d52d7c/config.json)

Ollama 工件没有公开精确转换 revision。因此，训练记录只能表述为“与本地 `qwen3.5:2b` 同族、同规模的官方 Qwen3.5-2B Base”；不得声称已经证明二者由同一上游 commit 转换。`base_model_gate.py` 会验证本地 safetensors 快照；只有提供可复核转换记录时，才会给出精确对应结论。

## 推荐环境

RTX 4060 Laptop GPU（8GB）采用小上下文纯文本 QLoRA：

```text
Python 3.11
CUDA PyTorch（单独安装，不能使用现有 CPU PyTorch）
4-bit NF4 + double quant
bf16 优先，失败时 fp16
micro batch=1, gradient accumulation=16
cutoff_len=512, gradient checkpointing=true
LoRA r=8, alpha=16, dropout=0.05
```

当前机器已确认具备 RTX 4060 Laptop GPU（8188 MiB）。隔离训练环境位于 `D:\AegisTraining\envs\qlora-qwen35`，已验证 CUDA、BF16 与 `bitsandbytes` 4-bit 训练路径；不得向生产依赖回写这些包。

## 初始化顺序

```bash
# 1. 在新的 Python 3.11 隔离环境中安装 CUDA PyTorch。
#    请按 PyTorch 官网为本机驱动选择 CUDA wheel；不要把 torch 写入生产 requirements.txt。
python -m pip install --upgrade pip
python -m pip install -r training/requirements-qlora.txt

# 2. 把大文件放到 D 盘训练根目录。
set HF_HOME=D:\AegisTraining\hf-cache
set AEGIS_TRAIN_ROOT=D:\AegisTraining

# 3. 通过官方下载工具获得固定 revision 的 safetensors 快照后，先做本地验证。
python -m aegis_training.base_model_gate --snapshot-dir D:\AegisTraining\models\Qwen3.5-2B-Base

# 4. 构建隔离数据；默认加入 committed project corpus 的 base 层，stress 层永久排除。
python scripts/prepare_risk_sft.py --output-root D:\AegisTraining\data\risk_sft_v2

# 5. 先执行仅加载模型/构造 LoRA 的 CUDA dry run，再运行训练。
python scripts/train_risk_qlora.py --data-root D:\AegisTraining\data\risk_sft_v2 --snapshot-dir D:\AegisTraining\models\Qwen3.5-2B-Base --dry-run
python scripts/train_risk_qlora.py --data-root D:\AegisTraining\data\risk_sft_v2 --snapshot-dir D:\AegisTraining\models\Qwen3.5-2B-Base

# 6. 合并已经训练完成且仍未接入生产的 adapter；此步骤只输出 safetensors 快照。
python scripts/merge_risk_qlora.py --snapshot-dir D:\AegisTraining\models\Qwen3.5-2B-Base --adapter-dir D:\AegisTraining\checkpoints\aegis-risk-qwen3.5-2b-v1\adapter --output-dir D:\AegisTraining\exports\aegis-risk-qwen3.5-2b-v1-merged
```

训练脚本会在量化后的真实线性层（包括 `bitsandbytes.Linear4bit`）上发现 LoRA target module；若所装 Transformers 无法用 `AutoModelForCausalLM` 加载官方 Qwen3.5 文本路径，或模型仍暴露视觉模块，会失败而不会悄然训练错误对象。训练使用 epoch 评估、`eval_loss` 最优模型选择与配置中的 early stopping patience。

## 数据与泄漏防护

原始 schema 和标签规则见 [data_contract.py](src/aegis_training/data_contract.py)。准备脚本只读取用户指定的外部目录，以及项目 `HEAD` 中可选的项目开发数据；不读取工作区未提交改动。

- `representative_corpus.json` 的 `base` 层 63 条合成/人工标注样本可以作为开发候选。
- `stress` 层 87 条是永久最终 holdout。脚本会做精确哈希和字符 n-gram 近重复检测，拒绝进入 train/dev。
- `risk.json`、`routing.json`、`multi_turn_corpus.json`、`safety.json`、测试消息、RAG fixtures、Harness、probe、政策文档和 Skill 内容不进入训练。
- 外部 SocialCD 与认知歪曲数据的 `medium/high/low` 映射属于弱监督，manifest 会保留 `label_method` 和 `review_status`，不把自动映射冒充人工复核。

## 目录说明

```text
training/
├── requirements-qlora.txt     # 训练环境依赖，独立于生产 requirements.txt
├── configs/
│   └── risk_qlora_4060.yaml   # NF4 / LoRA / 4060 默认参数
└── src/aegis_training/
    ├── base_model_gate.py     # 官方基座、结构与 LoRA 目标资格检查
    ├── data_contract.py       # 输入数据校验与 SFT JSONL 转换
    ├── leakage_guard.py       # stress holdout 精确/近重复泄漏检查
    ├── metrics.py             # 风险分类、JSON、理由长度与分层指标
    └── source_ingest.py       # 外部/项目来源读取与弱标签映射
```

## Ollama 发布兼容性

Ollama 的本地 `qwen3.5:2b` 是已量化的 GGUF 工件，不能直接作为 `ADAPTER` 的 safetensors 基座。Ollama 0.32.6 的实验性 safetensors 导入接受官方 Qwen3.5 快照并可生成独立 tag，但该版本在本机未能把生成的 tag 持久化为可运行模型；先前将多模态合并快照导入得到的 `aegis-risk-qwen35:qlora-v1` 也会在加载时因 `missing tensor 'blk.24.attn_norm.weight'` 失败。

因此，当前结果是 **QLoRA 训练与 Transformers 推理有效，Ollama 发布不兼容**。保留 `adapter` 和合并 safetensors 作为研究工件，绝不替换、删除或改写现有 `qwen3.5:2b`。在兼容的 Ollama/转换器版本上重新验证前，不得把任何候选 tag 写入生产配置。

## 验收与回滚

训练完成前不注册 Ollama 模型、不改变生产模型配置。候选 adapter 必须在冻结 `stress` holdout 上满足：

- JSON 有效率 ≥ 98%，合法风险标签率 ≥ 99%，理由超 20 字比例为 0；
- `rules ∪ QLoRA` 的 HIGH recall 不低于规则基线；
- 25 条隐喻高危样本相对规则新增至少 4 条命中；
- 11 条第三人称/虚构干扰中新增 high 误报不超过 1 条；
- non-high → high 误报率不高于规则基线 + 2 个百分点；
- P95 在既有 8 秒风险评估超时预算内；
- ordered、autonomous、langgraph 三运行时的报告资格和高风险模板链路无回归。

当前实际评测（2026-08-22）已确认合并的纯文本 safetensors 可由隔离 Transformers 环境加载，但**不通过验收**：`rules ∪ QLoRA` 在 25 条隐喻高危样本上命中 16 条，规则基线为 13 条，新增仅 3 条，未达到“至少新增 4 条”的门槛。其余已验证指标为：JSON 有效率 100%、合法标签率 100%、理由超 20 字比例 0、非 high → high 误报率 0、Transformers P95 约 0.95 秒。该候选必须继续作为研究资产，不得接入生产。

执行 Ollama 对比评测时：

```bash
python scripts/eval_risk_qlora.py --original-model qwen3.5:2b --qlora-model <validated-ollama-model>
```

如果 Ollama 不能运行候选，可对已合并的本地 safetensors 快照执行同一冻结集评测；原始对照仍走 Ollama：

```bash
python scripts/eval_risk_qlora.py \
  --original-model qwen3.5:2b \
  --qlora-model-dir D:\AegisTraining\exports\aegis-risk-qwen3.5-2b-v1-merged
```

脚本输出写入 `D:\AegisTraining\reports`。任一门槛失败时，adapter 仅保留为研究资产，生产继续使用原始模型/规则通道。

# Aegis 项目长期记忆

## 运行环境
- 测试/评测用 `D:/Anaconda/python.exe`（含 pytest + 全部项目依赖）；项目 `.venv` 缺包不可用；managed Python 无 app 模块。
- 项目根 `D:/PythonProject/aegis-psych-agent`，从根目录运行脚本时需 `sys.path.insert(0, root)`（`scripts/` 不在 path 上）。

## GLM 配置
- endpoint: `https://open.bigmodel.cn/api/paas/v4`（**非** `/openaimax/v1`，后者不存在）
- model: `glm-4.7-flash`（2026-01-19 发布的免费档，200K 上下文，替代 GLM-4.5-Flash）
- 免费档 ~1 req/s、1 并发，全量评测(150 条)会全 429 → 用 stub 测量 + 5 条 GLM probe 验证

## 风险双通道
- 生产 `RISK_LLM_CHANNEL_ENABLED=false`（纯规则，保"暴露边界"卖点）
- dev `=true`（能力验证：stub-LLM on）
- 并集逻辑: rules ∪ LLM, 任一 HIGH 即 HIGH, LLM 失败回退规则（`app/agents/classic.py:78-94`）
- judge prompt: `RISK_ASSESS_SYSTEM_PROMPT`(`app/llm/client.py:45-53`)，已覆盖隐喻/第三人称

## 评测体系
- 150 条语料双层拆分: base=63(贴近真实流量), stress=87(边界探测)
- baseline: stress joint=0.39, risk=0.67, high_recall=0.52（规则引擎能力边界，零删改不凑分）
- llm_stub: stress risk=0.94, high_recall=1.00（MetaphorAwareStubClient 模拟 LLM judge 上界）
- corp-106..130: 25 条 suicidal_implicit 隐喻，规则命中 13 条，stub 补齐全部 25 条

## 文档规范
- `docs/records/` 英文大写+连字符命名（ROUND-11-RISK-LLM-DUAL-CHANNEL.md）
- 系列链接头部含全轮次链
- README 链接用"第N轮"（与 doc 文件标题一致）

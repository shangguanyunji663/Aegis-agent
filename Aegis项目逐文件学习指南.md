# Aegis 项目学习指南 — 从零构建一个校园心理支持多 Agent 平台

> 本文档按照"如果你要从头写这个项目,你会怎么思考和编码"的顺序,逐模块拆解每个文件的设计意图与实现细节。建议按顺序阅读,每个模块读完后对照源码走一遍。
>
> 读者定位:刚接触 Agent 智能体应用开发、有 Python 基础的学生。你不需要先懂 LangChain 或 RAG,本指南会从"为什么需要这个东西"讲起。

---

## 第〇章 学习路线总览

Aegis 是一个"学生倾诉 + 风险识别 + 管理员处置"的完整闭环系统,不是单个聊天机器人。从头写它,你会经过 14 站:

```
第 1 站   地基          config / models / entities / database   — 先把"数据形状"立起来
第 2 站   安全底座      core/(auth / privacy / runtime / utils)— 账号、脱敏、限流先于一切功能
第 3 站   风险评估      assessment.py                            — 确定性规则,不依赖大模型
第 4 站   技能层        skills.py                                — 把"能力"注册成可调用单元
第 5 站   模型后端      llm/(client + prompts)                  — 让"大脑"可插拔
第 6 站   单轮智能体    agents/classic.py                        — 六个各司其职的角色
第 7 站   自治协作      autonomous/(黑板 + 认领制)              — 多 Agent 真正的协作机制
第 8 站   编排与 Harness agents/orchestrator + langgraph + harness — 把一切串成一次对话(三档运行时)
第 9 站   RAG 检索      rag/(分词/打分/切块/向量)                — 知识库如何被"检索"出来
第 10 站  持久化仓储    repository/store.py                      — 所有表的读写总闸
第 11 站  工具治理      tools/ + services/                       — 高风险动作必须被管住
第 12 站  HTTP 层       api/ + main.py                           — 把能力暴露成接口
第 13 站  评测闭环      evaluation/ + harness/ + eval/           — 用数据证明系统有效
第 14 站  收尾          static/ + tests/                         — 双端界面与质量兜底
```

**贯穿全程的四条设计哲学**(先记住,后面每个模块都会遇到):

1. **安全前置、规则优先**:高风险判断靠关键词规则(`assessment.py`)而不是模型输出;LLM 永远拿不到"是否高危"的决定权。
2. **治理与业务正交**:工具只管做事,角色/审批/脱敏/重试在契约层(`tools/contracts.py`)统一拦截。
3. **确定性可回放**:自治协作的全部中间状态落在 append-only 黑板上,trace 落库,任何一次回复都能复盘。
4. **默认可本地运行**:`AI_PROVIDER=mock` 时不需要任何 API key,整个闭环(含评测)照样跑通。

---

## 第 1 站 地基:config / models / entities / database

### 1.1 app/config.py — 全局配置

**为什么先写它**:后面每个模块都要读配置(模型提供方、知识库路径、限流阈值……),配置层必须最先就位。

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///data/aegis.sqlite"
    ai_provider: str = "mock"          # mock / openai / ollama
    knowledge_dir: str = "knowledge"   # 知识库目录(项目根下)
    agent_runtime: str = "autonomous"  # autonomous / ordered 双运行时开关
    agent_max_rounds: int = 8
    agent_final_acceptance_min_confidence: float = 0.6
    ...
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

- `BaseSettings` 来自 `pydantic-settings`:环境变量和 `.env` 文件自动映射到字段(`AI_PROVIDER=xxx` → `ai_provider`),大小写不敏感。
- 每个字段都有**安全默认值**——你不写任何 .env,系统也能本地跑。
- `project_root` 属性 + `resolve_path()` 把"相对路径配置"统一解析到项目根,兼容从任意工作目录启动:

```python
@property
def project_root(self) -> Path:
    return Path(__file__).resolve().parents[1]

def resolve_path(self, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else self.project_root / path
```

- `@lru_cache` 的 `get_settings()` 保证全进程只有一份配置实例。

**学习要点**:配置是"数据"不是"代码";用带默认值的声明式字段替代散落各处的常量;`.env.example` 是给使用者的配置说明书。

### 1.2 app/models.py — 领域模型(纯数据)

这一层定义**全项目通用的词汇表**,不依赖任何其他 app 模块(测试时可以单独 import 它):

```python
class Intent(str, Enum):        # 意图:companion 陪伴 / counseling 咨询 / risk 风险 / research 查资料
    COMPANION = "companion" ...

class RiskLevel(str, Enum):     # 风险三级分流,整个系统的"红绿灯"
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"
```

继承 `str, Enum` 是个小技巧:`RiskLevel.HIGH == "high"` 直接成立,和 JSON/数据库里的字符串无缝互转。

核心数据类(全部 `@dataclass`,纯 JSON 可序列化):

- `SkillResult` — 一次技能调用的结果(`name/output/side_effect`),`side_effect=True` 表示产生了外部副作用(如建报告)。
- `AgentTrace(agent, action, detail)` — 一条执行痕迹,三个字符串,最终拼成管理端可读的时间线。
- `ResponsePlan` — 回复的"施工图":模式、知识片段、稳定练习步骤、prompt 消息。
- `PendingReport` — 待管理员审批的风险报告。带有 `from_dict()` 类方法:

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "PendingReport":
    """从仓储层返回的报告字典重建 PendingReport(统一各处重复的转换逻辑)。"""
    return cls(id=data["id"], session_id=data["session_id"], ...,
               risk_level=RiskLevel(data["risk_level"]),
               status=ReportStatus(data["status"]), ...)
```

**为什么需要它**:仓储层吐出来的是 dict,而 API 层要的是带枚举的强类型对象——此前这个转换在 orchestrator、autonomous runtime 里各写了一遍,现在只有一份。

- `RuntimeEvent` + `sse_event` 属性 — 把内部事件类型映射为 SSE 前端事件名(`RUN_COMPLETED → "done"`),流式输出的协议适配就在这一个小字典里。
- `ChatResponse` — 一次对话的最终产物;`StreamEvent` — SSE 事件的信封。

**学习要点**:领域模型层要保持"零依赖"(只依赖标准库),它决定了整个系统的公共语言;`str+Enum` 是做配置类枚举的惯用法。

### 1.3 app/entities.py — ORM 实体(16 张表)

SQLAlchemy 2.0 声明式实体,和 `models.py` 的关系是:**models 是"怎么说",entities 是"怎么存"**。

代表表:`ChatSession`(会话,含 `owner_user_public_id` 归属)、`ChatMessage`、`SessionMemory`(滚动记忆摘要)、`AuthUser`/`AuthSession`(口令与令牌)、`PsychologicalReport`(风险报告)、`RiskCase`+`CaseNote`(个案)、`KnowledgeChunk`(知识切块)、`ToolJob`/`ToolAuditRecord`/`DeadLetterRecord`(工具任务/审计/死信)、`ExcelRecord`/`AlertRecord`(副作用记录)、`AgentPrivateMemory`(Agent 私有记忆)、`AgentModelProfile`(每 Agent 模型档案)、`AdminAuditLog`(管理端审计)。

注意两个细节:

- 时间字段统一用 `now()` 工厂生成**不带时区的 UTC**——和历史行为保持一致(数据库里已存的是 naive 时间)。
- `KnowledgeChunk` 同时存 `content`(原文)、`metadata_json`(元数据)、`embedding_json`(本地降级用的向量)——一个表兼容"有无向量库"两种部署。

### 1.4 app/database.py — 引擎与会话工厂(支持 SQLite / MySQL 双后端)

`DATABASE_URL` 形如 `mysql+pymysql://user:pass@host:3306/aegis?charset=utf8mb4` 时走 MySQL:pymysql 驱动、`pool_recycle=3600` 防闲置断连、首次启动自动 `CREATE DATABASE IF NOT EXISTS`(utf8mb4)。SQLite 则是零依赖本地模式,两套后端共享同一套 ORM 实体。

```python
def _engine_kwargs(database_url: str) -> dict:
    kwargs = {"pool_pre_ping": True}          # 取连接前先 ping,自动剔除断连
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}  # 允许后台线程共用
    return kwargs

def build_session_factory(runtime_settings=None):
    return sessionmaker(bind=build_engine(runtime_settings), autoflush=False, autocommit=False)
```

- **工厂而非模块级单例**:测试要用独立的 tmp 数据库,每个调用方自建 engine;重构时删掉了从未被引用的模块级 `engine`/`SessionLocal`。
- `create_schema()` 里 `from app import entities` 是**惰性导入**——先注册全部 ORM 实体到 `Base.metadata`,再 `create_all`。
- `migrate_legacy_schema()`:对旧库手写 `ALTER TABLE`/`CREATE TABLE` 补列补表,保证升级不丢数据。它与 entities.py 是两份 schema 真相,是已知的遗留债(见 REFACTORING.md 第 10 节)。
- `readiness_check()` 只做 `SELECT 1`,是 `/api/readiness` 的依据——和 `/api/health`(进程活着)区分。

**学习要点**:SQLite 要跨线程必须 `check_same_thread=False`(本项目有后台工具 worker 线程);"建表"与"迁移"是两件事,小项目手写迁移能用,正规项目上 Alembic。

---

## 第 2 站 安全底座:core/

地基立好后,先写"任何功能上线前必须有的东西":谁能用(认证)、哪些字段不能见(脱敏)、请求会不会打爆(限流)。

### 2.1 core/auth.py — 口令与会话

```python
def make_password_hash(password: str, salt: str | None = None) -> tuple[str, str]:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return salt_value, digest.hex()

def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = make_password_hash(password, salt)
    return hmac.compare_digest(digest, expected_hash)   # 恒时比较,防时序侧信道
```

- PBKDF2-HMAC-SHA256、12 万轮迭代、随机盐——不引入 bcrypt 依赖也能达到及格线的口令存储。
- `verify_password` 用 `hmac.compare_digest` 而非 `==`:避免"比较耗时差异"泄露前缀。
- 会话令牌 `secrets.token_urlsafe(32)`;`AuthPrincipal`(frozen dataclass)是"当前登录者"的轻量表示,贯穿所有路由依赖。
- `random_id(prefix)` 生成 `usr-xxx`/`audit-xxx` 这类可读 ID——日志里一眼看懂类型。

### 2.2 core/privacy.py — 脱敏与输入消毒

```python
SENSITIVE_PAYLOAD_FIELDS = {"api_key", "email", "message", "password", "phone",
                            "precise_location", "session_token", "student_id", "student_name", "token"}
INTERNAL_RESPONSE_TERMS = ("report_id", "risk-", "内部评分", "confidence")
```

- `redact_payload(payload, fields)` 递归把敏感字段替换为 `"[redacted]"`,返回 `(脱敏后, 命中字段列表)`——命中列表用于审计记录"哪些字段被藏了"。
- `contains_internal_response_leak(text)`:**安全复核的关键**。任何要发给学生的回复,先过这个函数——只要包含 `report_id`/`risk-`/`confidence` 等内部词汇,就会被 RiskGuardian 打回重写。
- `sanitize_user_input(text)`:进入模型前的预处理——压缩空白,并把"手机号/电话/身份证"替换成"联系方式/证件",降低模型诱导输出个人敏感信息的概率。

**学习要点**:心理场景的隐私是合规底线;脱敏要同时覆盖"存储侧"(payload 进审计表之前)和"输出侧"(回复发给用户之前)两个面。

### 2.3 core/runtime.py — RuntimeServices(限流与锁)

```python
class RuntimeServices:
    def __init__(self, settings: Settings):
        ...
        if settings.redis_url.strip():
            try:
                import redis
                self.redis_client = redis.Redis.from_url(...)
                self.redis_client.ping()          # 连不上立即降级
                self._redis_available = True
            except Exception:
                self.redis_client = None          # 本地无 Redis 也能跑
```

- `check_rate_limit(key, limit, window)`:Redis `INCR+EXPIRE` 计数窗口;无 Redis 时用进程内 `dict[str, list[float]]` 模拟——**同一个接口两种实现,语义一致**,这是"可选依赖"的标准写法。
- `lock(name, ttl)` 上下文管理器:Redis `SET NX EX`;本地退化为过期时间表。用在"手动跑工具任务"接口上,防止两个管理员同时触发批处理。

### 2.4 core/utils.py — 统一工具函数(重构的直接产物)

初版里 `_loads`(JSON 容错解析)在 4 个文件各有一份、`_now` 也有 4 份——而且**有两种时区语义**(带/不带 tzinfo)。重构时按原语义分别收编:

```python
def loads_dict(value: str) -> dict[str, Any]: ...   # 必须是 dict,否则 {}(队列/记录场景)
def loads_or(raw: str, default: Any) -> Any: ...    # 失败给默认值(仓储场景)
def now_utc() -> datetime: ...                      # aware UTC(服务层新代码)
def now_utc_naive() -> datetime: ...                # naive UTC(与库中历史数据一致)
```

**学习要点**:去重前先确认"真的相同"。两份 `_now` 语义不同(naive/aware),强行统一会改变数据库写入行为——正确做法是命名出两种语义,让调用点各取所需。

---

## 第 3 站 assessment.py — 确定性风险评估

**为什么在 LLM 之前写它**:这是全系统最重要的安全组件,而且完全不依赖模型——mock 模式下它就是"大脑"的安全部分。

```python
HIGH_TERMS = ["自杀", "轻生", "不想活", "结束生命", "suicide", "kill myself"]
MEDIUM_TERMS = ["伤害自己", "自残", "崩溃", "撑不住", "绝望", "panic", "hopeless"]
DEPRESSED_TERMS = ["抑郁", "低落", "难过", "无助", "depress"]
ANXIETY_TERMS = ["焦虑", "压力", "考试", "睡不着", "失眠", "panic", "anxious"]
```

`assess_message(text) -> AssessmentResult` 是纯函数:先匹配 HIGH(命中即 `risk_level=HIGH, confidence=0.95, report_eligible=True, escalation_policy="create_pending_report_and_require_admin_review"`),再 MEDIUM,再按抑郁/焦虑词给出 LOW,最后兜底"普通陪伴"。

返回的 `AssessmentResult` 不只是等级,还带**处置策略**(`recommended_stance`/`escalation_policy`):
- HIGH → `immediate_safety`:本地安全模板回复 + 建待审报告。
- MEDIUM → `stabilize_and_refer`:稳定练习 + 转介指引。
- LOW → 倾听陪伴。

`as_skill_output()` 把结果转成扁平 dict,供技能层透传。

**学习要点**(风险双通道,第五轮新增):`assess_message` 是规则通道;`RiskGuardianAgent` 会再用轻量 LLM 通道(`llm.assess_risk`,严格 JSON、8s 短超时)复核,两通道**取并集**——任一判 high 即 high,弥补关键词召回不足;LLM 失败/超时/mock 一律回退纯规则,输出 `risk_channels` 溯源。
- `HIGH_TERMS` 是**单一事实来源**——重构后 `autonomous/board.py` 的 `hard_high_risk()` 也引用它,改关键词只改一处。
- 规则评估可解释(命中了哪个词一目了然)、可单测、零成本零延迟。代价是召回有限——所以它被定位为"下限保障"而非"上限智能"。

---

## 第 4 站 skills.py — 技能注册表

**设计思路**:Agent 需要的能力(评估风险/检索知识/稳定练习/建报告)统一注册成 `SkillSpec`,而不是散落在各 Agent 里:

```python
@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    side_effect: bool                                  # 是否有外部副作用
    handler: Callable[..., SkillResult]

    def openai_schema(self) -> dict[str, Any]: ...     # 直接导出为 OpenAI function-calling 工具描述
```

`SkillRegistry.__init__` 注册 4 个内置技能:

| 技能 | 副作用 | 实现 |
| --- | --- | --- |
| `assess_risk` | 否 | 调 `assess_message`(第 3 站) |
| `search_knowledge` | 否 | 优先用注入的 `knowledge_search`(真 RAG);无注入时退化为关键词计分的本地检索 |
| `grounding_exercise` | 否 | 返回固定三步"60 秒稳定练习" |
| `create_pending_report` | **是** | 构造 `PendingReport` 并通过 `report_sink` 落库 |

注意构造参数的**依赖注入**:

```python
SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge)
#                    ↑目录            ↑报告落库回调        ↑检索回调
```

技能层不 import 仓储,而是接收函数——测试时可以塞假函数,这就是它可单测的原因。

另一条线:**标准化 Skill**(7 个 `skills/*/SKILL.md` 文档,带 frontmatter)。`response_skill_names(intent, risk, text)` 按规则选中(高风险 → 安全计划 + 交接摘要;命中"失眠"→ 睡眠支持……),`standard_context(names)` 拼成提示词注入。这是"用文档约束模型输出结构"的轻量做法。

`_split_frontmatter` 手写解析 YAML 头——不引入 yaml 依赖的取舍(知识文档的 frontmatter 解析在 `rag/chunking.py`,两者格式相似但容错策略不同:技能解析遇到坏文档直接跳过,知识解析静默忽略坏行)。

**学习要点**:`side_effect` 标记让"哪些技能会改变世界"一眼可见,后续审计/评测都依赖它;把 LLM 工具描述(`openai_schema`)作为技能的一等公民——第五轮已接真 function calling(`agents/skill_selection.py`):规则先定白名单(安全边界不变),模型在白名单内自主挑选技能与顺序,失败/幻觉名回退整个白名单。

---

## 第 5 站 llm/ — 模型后端

### 5.1 llm/client.py — 协议 + 三实现 + 工厂

```python
class LLMClient(Protocol):
    provider: str
    model: str
    def status(self) -> dict: ...
    def generate_support_reply(self, context: LLMContext) -> str | None: ...
    def stream_support_reply(self, context, on_token) -> str | None: ...      # 真流式直播
    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None: ...
    def assess_risk(self, text: str) -> dict | None: ...                      # 风险双通道(第五轮)
    def chat_with_tools(self, system, user, tools) -> list[str] | None: ...   # Function Calling(第五轮)
    def judge_reply(self, message, reply) -> dict | None: ...                 # LLM-as-Judge(第五轮)
```

`LLMContext` 是喂给模型的**结构化上下文包**:用户消息、意图、风险等级、记忆摘要、知识片段、稳定练习、技能约束——回复生成所需的一切都显式传入,模型不自己"想"。

协议从最初的"一问一答"长成了**五通道客户端**:回复生成(阻塞)、回复直播(流式)、查询改写(RAG)、风险复核(双通道)、技能选择(FC)、质量评审(Judge)。新增通道全部遵守同一条铁律:**失败/超时/mock 返回 None,调用方优雅降级**——这正是全系统"LLM 永远不是安全关键路径"的落点。

三个实现:

- `MockLLMClient`:两个方法都返回 `None`——**None 就代表"请走本地模板兜底"**。这让无 key 环境下整条链路(含高风险处置)照常可测。
- `llm/client.py`:urllib 裸调 `{base_url}/chat/completions`,支持智谱等 OpenAI 兼容端点的 `thinking:{"type":"disabled"}` 参数(默认关闭深度思考,大幅降低延迟)。第六轮起支持性回复使用独立温度 `LLM_SUPPORT_TEMPERATURE`(默认 `0.6`,偏口语更像真人;风险评估/改写/评审仍固定 `0.0`)。`post_json()` 对 429/5xx/超时做指数退避重试(最多 2 次,间隔 2s/4s);流式请求在**连接建立阶段**重试,一旦已开始接收 delta 则不再回退(避免已直播的 token 被丢掉)。`post_json` 失败后降级到模板回复,学生端不会白屏——但第六轮加了 `logger.warning`,可在日志里看到 provider/model。
- **真流式**:`stream_support_reply(context, on_token)` 以 `stream:true` 请求并逐 delta 回调——OpenAI 兼容端解析 SSE 行(`post_json_stream`),Ollama 解析 ndjson(`post_ndjson_stream`);中途异常返回已积累的部分(用户已看到的内容不回退)。
- `OllamaClient`:调 `/api/chat`,本地模型零成本。

`build_llm_client(settings)` 按配置三选一。

### 5.2 llm/prompts.py — 提示词模板

系统提示词是安全边界的一部分,值得整段读:

```python
system = (
    "你是校园心理支持产品中的咨询回复生成器。"
    "只能提供支持性倾听、问题澄清、自助练习和求助准备；不能诊断，不能承诺保密，不能替代专业咨询。"
    "高风险安全分流由上游规则处理，你不得输出内部风险分数、报告编号或后台审计细节。"
    "回复要使用简体中文，温和、具体、简洁。"
)
```

四句话分别划定:能力边界 / 禁止事项 / 与规则层的分工 / 输出风格。用户消息模板把记忆、意图、风险、知识、练习、技能逐块拼装——**上下文工程就是把"该给的信息"按结构喂给模型**。

第六轮把提示词从"机器人模板"改成"真人陪伴风格":不再自称"咨询回复生成器",改为"你是 Aegis,校园心理支持助手";指令从"先共情→1-3步骤→开放问题"改成灵活对话指导(短句口语、长度匹配用户消息、一次最多一个问题、建议最多两条且只在合适时给)。历史摘要/知识/练习字段仍动态注入,但加了防泄漏指示——禁止把"用户提到/系统回应重点"等内部标签原文放进回复里。

**学习要点**:提示词放独立文件便于审计;`prompts.py` 与 `client.py` 互相只用类型注解引用(TYPE_CHECKING),不产生运行时循环依赖。

---

## 第 6 站 agents/classic.py — 六个单轮智能体

这一层是"每个角色做一件小事",全部是无状态类(除 Counselor 持有 registry/llm):

| Agent | 方法 | 职责 |
| --- | --- | --- |
| `MemoryAgent` | `load / update` | 读写会话记忆摘要 |
| `RiskGuardianAgent` | `assess / create_report` | 调 assess_risk 技能(**规则∪LLM 双通道取并集**,详见第 3 站);HIGH 时建待审报告 |
| `LeadAgent` | `route` | 关键词路由:高危→RISK;资料词→RESEARCH;咨询词或 MEDIUM→COUNSELING;否则 COMPANION |
| `KnowledgeAgent` | `search / rewrite_query` | LLM 改写检索词(失败退化原文前 60 字)+ 检索 |
| `CounselorAgent` | `grounding / compose_plan / finalize_plan` | 组装 ResponsePlan 并生成最终回复 |
| `CompanionAgent` | — | 空类,低风险陪伴的"占位角色"(回复实际复用 Counselor 的模板路径) |

重点看 `CounselorAgent.finalize_plan` 的**分层兜底**:

```python
def finalize_plan(self, plan: ResponsePlan) -> tuple[str, AgentTrace]:
    fallback = self._fallback_answer(...)          # ① 先无条件构造模板回复
    if risk_level is RiskLevel.HIGH:
        return fallback, ...                       # ② 高风险:永远用模板,不给模型机会
    context = LLMContext(...)                      # ③ 低/中风险:组装上下文问模型
    generated = self.llm_client.generate_support_reply(context)
    if generated:
        return generated.strip(), ...              # ④ 模型可用:用生成结果
    return fallback, ...                           # ⑤ 模型不可用/mock:模板兜底
```

`_fallback_answer` 的模板按风险分三档开头(高危段直接给出"联系可信任的人/心理中心/紧急服务"),再拼记忆回显、稳定练习、知识首条、意图化收尾——**这就是 mock 模式下学生看到的回复来源**。

**学习要点**:每个方法都返回 `AgentTrace`——"做事"与"留痕"是绑定的;安全关键路径(HIGH)与模型路径在 ② 处显式分流,这是"规则优先"哲学的落点。

---

## 第 7 站 autonomous/ — 自治黑板协作(项目的心脏)

单轮 Agent 只是零件。真正的多 Agent 协作在这一站:六个自治 Agent 围绕一块**只增不删的黑板**认领任务、发布产物、互相评审。

### 7.1 autonomous/events.py — 纯数据协议

先定义"协作的语言":

- `AgentEventType`:TURN_STARTED / TASK_CREATED / TASK_CLAIMED / ARTIFACT_PUBLISHED / SAFETY_OVERRIDE / REVISION_REQUESTED / FINAL_ACCEPTED / BUDGET_EXHAUSTED …
- `AgentTask`:带 `required_capabilities`(能力要求)、`priority`、`metadata`。
- `AgentArtifact`:`(owner, kind, payload, confidence, task_id, metadata)`——**一切中间产物**:`memory`/`intent`/`risk`/`context`/`response_proposal`/`safety_review`/`pending_report`。
- `CollaborationBlackboard`:核心结构,`turn_id/session_id/user_input` + `tasks/artifacts/messages/events` 四个列表。

```python
def append_artifact(self, artifact: AgentArtifact) -> "CollaborationBlackboard":
    clone = self._clone()          # ① 深拷贝自己
    clone._artifacts = [*self._artifacts, artifact]   # ② 追加新列表
    return clone                   # ③ 返回新板,旧板不动
```

**不可变(immutable)设计**:每个 append/append_event 都克隆出新黑板。为什么?——同一轮里任何时刻截取的 board 都是一致快照,协作过程天然可回放、可 debug,不存在"谁偷偷改了共享状态"。

### 7.2 autonomous/registry.py — 能力与决策

- `AgentCapability` 五种能力:MEMORY / UNDERSTANDING / SAFETY / CONTEXT / RESPONSE。
- `AgentProfile(name, capabilities, system_prompt, memory_policy, tool_permissions)`:Agent 的"名片"。`tool_permissions` 声明它可触碰的工具——**权限是声明的,不是散落的 if**。
- `AutonomousAgentRegistry.candidate_decisions_for(task, board)`:过滤出能力匹配的 Agent,逐个问 `decide()`,把愿意认领的按置信度排序——**认领制(claim-based)的核心**。

### 7.3 autonomous/board.py — 黑板共享读取(重构新增)

协作双方(协调器、Agent、运行时)都要"看一眼黑板推断当前状态"。此前三份近似拷贝,重构收编为:

```python
def risk_from_board(board) -> RiskLevel:
    # 所有 risk 工件取最高;任何 SAFETY_OVERRIDE 事件 → 直接 HIGH

def intent_from_board(board, *, use_board_risk=True, use_hard_terms=True) -> Intent:
    # ① 板上风险 HIGH → RISK(use_board_risk)
    # ② 有 intent 工件 → 用它
    # ③ 否则按硬高危词回退(use_hard_terms)→ RISK,不然 COMPANION
```

两个开关不是多余——**原三份实现语义确有差异**:runtime 版不做硬词回退、coordinator 版不做风险预判。参数化让"历史行为逐点保留"且差异显式可见。`hard_high_risk()` 引用 `assessment.HIGH_TERMS`,安全词表全项目只此一份。

### 7.4 autonomous/coordinator.py — 认领制协调器

`AutonomousCoordinator.run(board)` 主循环(不超过 `max_rounds` 轮):

```
每轮:
  1. _derive_missing_work   派生缺失任务:没有 memory 工件→建"读记忆"任务;
                           没有 intent→建"路由"任务;…没有 response→视条件建"提案"任务;
                           有新提案但没 safety_review → 建"安全复核"任务
  2. _try_accept_final      已有提案+复核通过+置信度≥阈值 → accept_final,结束
  3. _claim_candidates      各 Agent decide() 认领,按(任务优先级, 置信度)排序,
                           每轮最多 max_claims_per_round 个、每 Agent 最多 max_claims_per_agent 次
  4. 逐个执行:agent.act(task, board) → board.apply_turn_result(...)
  5. 回到 1
```

预算护栏体现在三处:轮次上限(超了发 `BUDGET_EXHAUSTED`)、每轮认领上限、单 Agent 认领上限。`force_response=True` 分支保证即使前置缺失也会被逼着产出一个回复——**学生端永远有答案**。

### 7.5 autonomous/agents.py — 六个自治 Agent

`BaseAutonomousAgent` 提供公共设施:`_artifact()`(造产物)、`_message()`(发消息)、`client()`(按档案取专属模型)、`private_memory()/remember()`(读写 Agent 私有记忆)。

每个子类实现 `decide()`(要不要认领)+ `act()`(做事发产物)。最值得读的是 `RiskGuardianAutonomousAgent`——它身兼两职:

1. **独立评估**(`_assess`):调单轮 RiskGuardian,产出 `risk` 工件;HIGH 时追加 `pending_report` 工件 + 发 `SAFETY_OVERRIDE` 事件(这个事件会让 `risk_from_board` 永远返回 HIGH,即使后续有人评估成 LOW——**安全一票否决**)。
2. **复核回复**(`_review_response`):对每个新提案做安全审查——

```python
if contains_internal_response_leak(answer):        # 泄漏内部字段?
    approved = False; reason = "response leaks internal implementation ..."
if risk is RiskLevel.HIGH and not any(term in answer for term in ["安全", "可信任的人", "紧急", "学校心理中心"]):
    approved = False; reason = "high-risk response lacks immediate safety guidance"
```

不通过就发 `critique` 工件 + `REVISION_REQUESTED` 事件 + 创建 CRITICAL 修订任务——Counselor 重新写,再送审,**直到通过才可能被验收**。

### 7.6 autonomous/runtime.py — 黑板 → 聊天响应

`AutonomousAgentRuntime.run(session_id, message)` 是自治模式的总入口:
1. 组装 `AutonomousRuntimeServices`(store/registry/llm/模型档案)与六个自治 Agent;
2. 建黑板、发 `TURN_STARTED`,交给协调器跑到收敛;
3. 取 `accepted_artifact() or latest_artifact("response_proposal")` 的 answer(空则兜底一句话);
4. 落 assistant 消息、更新记忆、发 `ARTIFACT_PUBLISHED`;
5. 从黑板抽取结果组装 `AutonomousRunOutcome`(intent/risk/skills/trace/pending_report/response_plan)——各种 `_xxx_from_board` 把四散的工件收敛成 API 需要的形状。

**学习要点**:黑板模式 + 认领制让"协作"有真实语义(谁认领、凭什么、产出什么),而不是假装的顺序调用;SAFETY_OVERRIDE 的一票否决和 revise 循环是多 Agent 安全治理的样板。

---

## 第 8 站 编排与 Harness — agents/orchestrator + harness

### 8.1 orchestrator.py — PsychOrchestrator

构造函数一次性装配:六个单轮 Agent + AgentRegistry + AgentRuntimeRunner + AgentModelRegistry + AutonomousAgentRuntime。

`_run()` 开头的分流是**双运行时开关**:

```python
if getattr(self.settings, "agent_runtime", "autonomous") == "autonomous":
    return self._run_autonomous(message, session_id, emit)   # 默认:黑板自治
# 否则:有序流水线(第 6 站的 Agent 按固定顺序跑)
```

有序路径(`agent_runtime="ordered"`)同样值得读一遍:load memory → assess risk → route → (companion 跳过检索!) → search_knowledge → grounding → HIGH 则 create_report → 选标准 Skill → compose_plan → finalize_plan → 存消息/更新记忆/落 trace。每步都经 `runtime_runner.run_step()` 包裹(记录 AGENT_STARTED/RUN_FAILED 事件)。

两条路径最终都汇成 `ChatResponse`。`_run_autonomous` 额外把黑板事件流翻译成 RuntimeEvent 发给 `emit`——这就是 SSE 流式输出的来源。**低风险对话支持真流式**:回复生成的 token 经回调链(services.on_reply_token → finalize_plan → stream_support_reply)实时推给 SSE,首字延迟≈模型首 token 延迟;中/高风险不直播,必须等 RiskGuardian 安全复核通过后输出。直播过真实 token 后,结尾的模拟切块 `_token_chunks()` 会自动跳过,避免重复。

### 8.2 harness.py — AegisAgentHarness

HTTP 与 Agent 世界之间的薄适配层,职责就三件:

```python
def _prepare(self, message, session_id, owner_user_public_id):
    original_input = message.strip()
    model_input = sanitize_user_input(original_input)      # ① 输入消毒
    owned_session_id = self.store.ensure_session(...)      # ② 归属会话解析
    return original_input, model_input, owned_session_id   # ③ 交给 orchestrator
```

`stream()` 把 `handle_stream` 的事件转发给 emit 回调。路由层因此可以保持"参数校验 + 鉴权 + 限流"的纯净,不碰任何 Agent 细节。

### 8.3 model_profiles.py — 每 Agent 模型档案

`DEFAULT_AGENT_MODEL_PROFILES` 为六个 Agent 声明默认温度(记忆/路由/安全 0.0、知识 0.1、咨询 0.2、陪伴 0.3)与系统提示词,启动时写入 `agent_model_profiles` 表。`client_for(agent_name)`:档案是 `inherit` 就返回全局客户端,否则按档案的 provider/model 现造一个——**让"安全评估用小模型、回复生成用大模型"成为一行配置**。

### 8.4 langgraph_runtime.py — LangGraph StateGraph(主推运行时)

`LangGraphRuntime` 用 LangGraph 的声明式状态图编排同一批单轮 Agent:`START → load_memory → assess_risk → route_intent →(条件边:companion+low 直接跳 compose,否则)→ context → report(仅 HIGH) → compose → finalize → END`。状态 `GraphState` 是 TypedDict,`trace/skills` 字段用 `Annotated[list, operator.add]` 让节点返回增量自动合并;图只编译一次,每次对话 invoke 新状态,天然线程安全;finalize 仅低风险传 `on_token` 直播回调,安全门控与另两个运行时一致。`AGENT_RUNTIME=langgraph|autonomous|ordered` 三档切换,是"同一业务、三种编排"的活教材。图还挂了 SqliteSaver 检查点(thread_id=会话 ID,`LANGGRAPH_CHECKPOINT_ENABLED`),`get_state(session_id)` 可读取最近终态——长对话跨进程断点可恢复。

### 8.5 runtime.py — AgentRegistry / AgentRuntimeRunner

有序路径的执行骨架:`run_step(agent_id, action, call)` 统一包裹"取 Agent → 执行 → 记事件 → 异常记 RUN_FAILED 再抛"。仅 60 行,却让有序路径的每一步都可观测。

---

## 第 9 站 rag/ — 检索子系统

### 9.1 text.py — 分词

```python
def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())  # 英文整词、中文单字
    compact = "".join(ch for ch in text.lower() if "\u4e00" <= ch <= "\u9fff")
    grams.extend(compact[i:i + 2] for i in range(...))                   # 中文再补二元组
```

**为什么中文要 bigram**:单字粒度太碎("考试"和"考/试"混在一起),BM25 的词频统计会失真;补上二元组让常用双字词成为可统计单元——不引 jieba 的轻量取舍。

### 9.2 scoring.py — 打分

- `bm25_scores`:教科书式 BM25(k1=1.5, b=0.75),中文用 bigram 词表。
- `rerank_score`:**四路词法信号加权**——`base*0.55 + (余弦*0.75+关键词*0.25)*0.25 + 覆盖率*0.15 + 短语命中*0.05`。纯 Python,零模型成本,却显著改善排序。
- `fused_score` + `normalize_scores`:向量分与 BM25 分各自 min-max 归一后按权重(默认 0.65/0.35)线性融合。
- `expand_best_hit`:冠军块合并同源相邻块——切块会把答案拦腰截断,这一步把邻居拼回来。

### 9.3 chunking.py — 知识文档处理

`parse_knowledge_document` 解析 frontmatter(topic/audience/risk_level/source_type/last_reviewed);`metadata_matches` 做元数据过滤;`chunk_text` 是滑窗切块(size-overlap 步进)。

### 9.4 memory.py — 会话记忆摘要

```python
new_line = f"用户提到：{compact_sentence(user_message, 120)}；系统回应重点：{compact_sentence(assistant_answer, 160)}"
# 从最新往旧收集,超过 max_chars 停止 → 反转拼接
```

滚动摘要:每轮一行,超预算从最旧开始丢——心理对话"最近的上下文最重要",这个丢弃方向是对的。

### 9.5 vector_store.py — 向量后端

`build_vector_backend(settings)` 按配置返回:
- `ChromaVectorBackend`:真向量库,chromadb 持久化(cosine 空间),支持快照。嵌入有两种来源,由 `EMBEDDING_PROVIDER` 决定:
  - `local`(默认推荐):chromadb 内置 **MiniLM 本地嵌入**——离线、零 KEY、零费用;中文语义主要靠 BM25 主导、向量补充
  - `openai`:OpenAI 兼容 `/embeddings` API(需向量模型额度)
- `LocalVectorBackend`:**哈希 bigram 伪向量** + 本地余弦——向量开关关掉时的降级路径,保证检索始终可用。

> 取舍实录:本项目接入真实 GLM 聊天模型但**没有向量模型额度**,于是把 Chroma 的嵌入源切到本地 MiniLM——向量库是真的、嵌入是离线的,检索质量经实测命中正确(考试→exam/sleep、关系→relationships)。

`store.search_knowledge`(第 10 站)把 9.1–9.5 串成完整流水线:改写查询 → 向量候选(可选)→ 元数据过滤 → BM25 → 双路归一融合 → 重排 → 邻块扩展 → 截 top_k。

**学习要点**:RAG 不神秘,它是一条"分词→打分→融合→重排"的确定性流水线;每一环都可以单独替换成更强的实现(如 embedding 模型),这就是分层的好处。

---

## 第 10 站 repository/store.py — 持久化仓储

`DatabaseStore` 是所有表的读写总闸(约 950 行,按区块组织):

- **会话/消息**:`ensure_session`(不存在则建,支持归属回填)、`list/get/delete/rename_session`、`append_message`(首条用户消息自动成为标题)。
- **认证**:`ensure_default_users`(演示账号)、`authenticate_user`(验密 + 发会话令牌)、`get/revoke_auth_session`(过期即删)。
- **记忆**:`get_memory`(Redis 缓存 → SQLite)、`update_memory`(调 `rag/memory.build_memory_summary` 后双写)。Agent 私有记忆同理(`append/load_agent_private_memory`,Redis list 缓存最近 50 条)。
- **知识库**:`seed/rebuild_knowledge_dir`(目录全量重建)、`ingest_knowledge`(内容未变则跳过重嵌)、`search_knowledge`(第 9 站流水线)、`rebuild_vector_index`、`backup_knowledge_dir`。
- **报告/个案**:自身只剩薄委托——`list_reports` 等一行转给 `ReportCaseService`(第 11 站),服务持有同一个 Session。
- **工具任务**:`create_tool_job`(先过契约校验,被拒也写审计!)、`run_pending_tool_jobs`、`retry_tool_job`、死信列表。
- **模型档案/审计/追踪**:`ensure/get/list_agent_model_profiles`、`add/list_audit_logs`(写前脱敏)、`add_trace/list_traces`。

**读一个代表性方法**——`create_tool_job` 的"拒绝也要留痕":

```python
try:
    governed = governed_payload(canonical_kind, payload, role=role, approved=approved)
except Exception as exc:
    self._add_tool_audit_record(db, kind, "queue", "rejected", str(exc), payload, ...)  # ← 先记拒绝
    db.commit()
    raise                                                              # ← 再抛出去
```

治理审计不在"成功路径"上,恰恰要覆盖失败路径——被拒绝的调用是最需要审计的东西。

**学习要点**:仓储大类按"领域分区块"组织仍然可维护,关键是把**算法**(rag/)与**服务逻辑**(services/)请出去;`with self.db_factory() as db:` 每方法一会话,提交即释放。

---

## 第 11 站 工具治理 — tools/ + services/

高风险场景的完整闭环:报告审批 → 建个案 → 派发 5 个工具任务 → 后台执行 → 落记录。这一站是"治理与业务正交"的落地。

### 11.1 tools/contracts.py — 契约先行

```python
@dataclass(frozen=True)
class ToolContract:
    kind: str
    required_role: str                  # 只有 admin 能触发
    allowed_risk_levels: tuple[str, ...]
    approval_required: bool
    redacted_payload_fields: tuple[str, ...]
    max_attempts: int = 3
```

6 个受治理工具(alert/email/ledger/handoff/lookup/follow_up)各有一份契约。`governed_payload()` 是**入队前的统一关卡**:

```python
def governed_payload(kind, payload, role, approved) -> dict:
    if role != contract.required_role: raise ToolGovernanceError(...)        # ① 角色
    if risk_level not in contract.allowed_risk_levels: raise ...             # ② 风险等级
    if contract.approval_required and not approved: raise ...                # ③ 审批
    redacted, fields = redact_payload(payload, contract.redacted_fields)     # ④ 脱敏
    return {**payload, "tool_kind": ..., "redacted_payload": redacted, ...}  # ⑤ 盖章放行
```

任何一步不过都是异常——**工具根本进不了队列**。`TOOL_KIND_ALIASES` 把旧名(alert_log_mock 等)规范化,兼容历史调用方。

### 11.2 services/report_case.py — 审批后的编排

`ReportCaseService.update_report`:状态改为 APPROVED 且风险 ≥ MEDIUM 时自动 `ensure_case`。`ensure_case_tool_jobs` 是**工具派发中心**:为每个新个案一次性创建 5 个 ToolJob(create_alert/send_email/write_ledger/create_handoff_summary/follow_up_suggestion),载荷全部先过 `governed_payload`。

### 11.3 services/tool_queue.py — 队列与后台 worker

- `ToolQueueService.run_pending(db, limit)`:批量取 PENDING 任务,检查依赖(`_dependency_ready`:同 case 的 handoff 完成后 email 才发)、执行、记录结果。
- 失败处理:attempts+1,未超限则改回 PENDING 并设 `run_after`(延迟重试);超限写 `DeadLetterRecord`——**死信是可运营的失败**,管理端有专门页面。
- `RateLimiter`:邮件每分钟限 N 封,超了不算失败,只延迟。
- `ToolQueueWorker`:线程池 + 轮询的后台常驻进程,FastAPI lifespan 里启停;`run_once()` 供手动触发(加分布式锁防并发)。

### 11.4 services/tool_executor.py — 真实副作用

`execute(kind, payload, attempts)` 分发到:`write_ledger`(openpyxl 追加 Excel 行)、`create_alert`(建 AlertRecord + 可选 webhook)、`send_email`(SMTP 真发或 log 模式)、`create_handoff_summary`(写 Markdown 文件)、`append_jsonl`(通用 JSONL 追加)。`always_fail` 载荷是**故意留的测试钩子**——harness 用它验证重试与死信路径。

### 11.5 services/tool_records.py + tool_governance.py

前者持久化 ExcelRecord/AlertRecord(去重:同报告同个案只记一条);后者提供执行前授权检查与审计写入,供 MCP 边界复用。

### 11.6 tools/gateway.py + mcp_tools/server.py + tools/mcp_client.py — MCP 边界

`ToolGateway` 协议两个实现:`InternalToolGateway`(直接 store.create_tool_job)与 `McpToolGateway`(通过 stdio 拉起 FastMCP server 子进程调用同一套受治理工具)。`build_tool_gateway` 按 `TOOL_BACKEND` 选择——**换后端不改业务代码**。MCP server 的每个 `@mcp.tool` 内部走的仍是 DatabaseStore + 契约校验:协议变,治理不变。

**学习要点**:这一站回答"为什么不让模型直接调工具"——因为每个外部动作都必须被(角色/风险/审批/脱敏/重试/审计)六重约束包住;契约数据化(frozen dataclass 注册表)让新增工具 = 新增一份声明。

---

## 第 12 站 HTTP 层 — api/ + main.py

### 12.1 main.py — 只做装配(约 90 行)

`create_app()` 顺序:settings → engine/会话工厂/建表 → DatabaseStore(默认账号+知识库种子)→ RuntimeServices → SkillRegistry → LLM 客户端 → Orchestrator → Harness → 工具网关 → 队列 worker。全部挂 `app.state`,注册中间件与 5 个路由模块。lifespan 里启停 worker。

**重构前后的对比**:初版 45 个路由全以闭包塞在 create_app 里(576 行);现在 main.py 只剩装配,路由按领域分家——依赖从"闭包捕获"变成"request.app.state 显式获取",可测性和可读性都是量级差异。

### 12.2 api/deps.py — 认证依赖

```python
def current_principal(request: Request) -> AuthPrincipal:
    cookie_name = request.app.state.settings.auth_session_cookie   # Cookie 名可配置
    session_token = request.cookies.get(cookie_name)
    ...
```

`require_admin = Depends(current_principal) + 角色检查`。路由声明 `principal: AuthPrincipal = Depends(require_admin)` 即完成鉴权——FastAPI 依赖注入的标准用法。

### 12.3 api/middleware.py — 请求追踪(重构补齐的功能)

```python
async def attach_request_context(request, call_next):
    request_id = request.headers.get("X-Request-ID") or random_id("req", 12)
    trace_id = request.headers.get("X-Trace-ID") or random_id("trace", 12)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = trace_id
    return response
```

请求方带头则沿用(链路串联),否则生成。配合落库的 Agent trace,一次请求从 HTTP 到 Agent 每一步都可追。

### 12.4 其余路由模块

- `schemas.py`:9 个请求模型集中定义。
- `pages.py`(3 个 HTML)、`system.py`(health/readiness/agent-status/skills)。
- `auth_routes.py`:register(注册即登录:学生自由注册,教师须凭 `AUTH_TEACHER_INVITE_CODE` 邀请码,防自助获取工作台权限)/login(httpOnly + samesite-lax Cookie,防 XSS/CSRF)/logout/me。`api/errors.py` 提供全局异常处理:治理拒绝→403、ValueError→400、参数校验→422、未知异常→500(日志留完整堆栈,响应不泄露内部细节)。
- `chat.py`:`POST /api/chat`(限流→归属校验→harness.run)、`/api/chat/stream`(SSE,含异常兜底:流中出错也补发 error+done 事件)、会话 CRUD。
- `admin.py`:约 20 个后台接口。值得注意 `safe_knowledge_filename`(白名单后缀+字符清洗,防路径穿越)与上传接口的 PDF 解析分支(pypdf 惰性导入)。

---

## 第 13 站 评测闭环 — evaluation/ + harness/ + rag_eval/ + eval/

**工程化 Agent 项目的标志**:效果不是"看着不错",而是可重复度量。

- `evaluation/runner.py`:八套指标——路由准确率、风险(含 high_recall/误报率)、检索(top1/命中率/MRR/NDCG@K)、RAG eval、技能选择、安全泄漏检查、多轮一致性、150 条规模化基准。
- `evaluation/datasets.py`:5 类消息 × 30 轮的确定性基准——**生成式数据集**,保证每次评测同分布。
- `evaluation/report_html.py`:单文件 HTML 报告(内联 CSS),管理端一键可看。
- `app/rag_eval/runner.py`:RAG 专项(hitRate/recallAtK/precisionAtK/MRR/NDCG@K),数据集在 `eval/fixtures/aegis-rag-eval.json`(66 条,含期望来源与期望词)。
- `app/harness/runner.py` + `factory.py`:工程级场景回放——7 套套件(risk/routing/skills/rag/api/tool-queue/scaled)断言**端到端行为**(如"审批后 5 个工具任务全部 success""死信被正确创建"),失败退出码 1,可接 CI。`factory.py` 是重构产物:harness 与 `eval/run_eval.py` 共用一个装配工厂,消除两份漂移的样板。
- `eval/fixtures/*.json`:路由/风险/检索/安全/多轮的小型金标集。

**学习要点**:评测三层——单元(pytest 65 项)/能力(eval runner)/链路(harness 8 套件);mock LLM 保证全链评测确定性,测的是**系统**不是模型运气。三运行时 A/B(`--suite runtime-ab`)对比编排器延迟/trace/调用数,LLM-as-Judge(`evaluation/judge.py`)给回复打共情/安全/结构分——评测从"分对错"升级到"评质量"。

---

## 第 14 站 收尾 — static/ + tests/

- `static/index.html + login.js`:登录页;`student.html/js`:会话列表 + SSE 流式对话;`admin.html/js`:报告/个案/trace/知识库/工具/评测/审计七大面板。原生 JS,零构建。
- `tests/` 十四个文件 65 项:orchestrator(提供 `build_orchestrator` 给其他测试复用)、api(TestClient 全链)、agent_runtime、retrieval_eval、mcp_tools、harness、assessment,以及第五轮新增的 risk_dual_channel(双通道)、function_calling(FC)、runtime_ab(A/B)、judge(LLM 评审)、langgraph_runtime、langgraph_checkpoint(跨进程恢复);第六轮新增 `test_reply_style.py` 守护"提示词自然人设"与"兜底模板不露内部标签"两条底线。

---

## 总结一:设计模式回顾

| 模式 | 落地位置 | 作用 |
| --- | --- | --- |
| Protocol 抽象 | LLMClient / ToolGateway / AutonomousAgent | 后端可插拔,mock/真实一键切换 |
| 工厂函数 | build_llm_client / build_tool_gateway / build_vector_backend / create_app | 装配逻辑集中,选择逻辑唯一 |
| 依赖注入 | SkillRegistry(report_sink/knowledge_search)、API 路由(app.state) | 层间解耦,测试可替换 |
| 不可变数据 + 克隆追加 | CollaborationBlackboard.append_* | 协作过程可回放、无共享状态竞争 |
| 黑板模式 | autonomous/ 全家 | 多 Agent 通过共享产物协作 |
| 认领制调度 | AutonomousCoordinator + AgentDecision | "谁干活"由能力+置信度决定 |
| 一票否决 | SAFETY_OVERRIDE 事件 | 安全判断不可被后续覆盖 |
| 责任链 | governed_payload 五连检查 | 工具入队前统一关卡 |
| 生产者-消费者 | ToolJob 表 + ToolQueueWorker | 副作用异步化,不阻塞学生端 |
| 读写缓存 | Redis(记忆/私有记忆)+ 进程内降级 | 可选加速,无 Redis 不影响正确性 |
| 模板方法式兜底 | CounselorAgent.finalize_plan | 模型失败永远有安全回复 |
| 参数化收编 | board.intent_from_board(use_board_risk/use_hard_terms) | 去重但显式保留历史语义差异 |

## 总结二:一次请求的完整数据流

```
学生输入
 → POST /api/chat(api/chat.py:限流 + 归属校验)
 → AegisAgentHarness._prepare(消毒 + 会话解析)
 → PsychOrchestrator._run(autonomous)
 → AutonomousAgentRuntime.run
    → 黑板 + TURN_STARTED
    → Coordinator 循环:
        MemoryAgent.load → memory 工件
        LeadAgent.route → intent 工件
        RiskGuardian.assess → risk 工件(HIGH:pending_report + SAFETY_OVERRIDE)
        KnowledgeAgent.search → context 工件(RAG 流水线)
        Counselor/Companion.compose_plan + finalize_plan → response_proposal
        RiskGuardian._review_response → safety_review(不过 → critique → 修订循环)
        → FINAL_ACCEPTED
 → 落库:assistant 消息 + 记忆更新 + AgentRunTrace
 → ChatResponse → JSON / SSE
 [异步] 管理员审批 → ReportCaseService.ensure_case → 5×ToolJob → Worker 执行
        → Excel/邮件/预警/交接/审计 全部落记录
```

## 总结三:实操建议

1. **跑起来**:`python -m app.init_db && uvicorn app.main:app --port 8091`,用 student/student123! 登录发一句"我最近考试压力很大,晚上睡不着",再去 /admin 看报告与 trace。
2. **看一次安全闭环**:发"我不想活了",观察:回复是本地安全模板(mock 下也是)→ 管理端出现待审报告 → 审批 → 工具任务全部 success。
3. **读一次黑板**:`tests/test_orchestrator.py` 里的高风险用例断言了 SAFETY_OVERRIDE 的传播;再对照 `autonomous/runtime.py` 的 `_trace_from_board` 看事件如何变成 trace。
4. **改一个小东西试试**:往 `assessment.HIGH_TERMS` 加一个词,跑 `pytest` 与 `python -m app.harness.runner --suite risk`——体会"单一来源 + 评测护栏"如何让修改变得安全。
5. **换个模型**:设 `AI_PROVIDER=ollama` 起服务,其余什么都不用改。

## 附:运行环境说明

```bash
# 方式一:通用 venv
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 方式二:项目自带 .conda 环境(Windows)
.conda/python.exe -m pytest -q                       # 直接用内嵌解释器

cp .env.example .env
python -m app.init_db
uvicorn app.main:app --host 127.0.0.1 --port 8091
```

当前验证状态:`pytest 65/65 通过`,`python -m app.harness.runner --suite all` 8/8 套件通过。

> 免责声明:本项目用于心理支持工程学习与展示,不提供医学诊断,不能替代专业心理咨询或危机干预服务。

---

*本指南对应 2026-08 的 `fix/source-labels` 分支第六轮改动;各轮详细变更见 [docs/records/](docs/records/) 系列文档(REFACTORING → OPTIMIZATION → AUTH-MYSQL → LANGGRAPH-DOCKER → DEEP-ENHANCEMENTS → LLM-RESPONSE-HUMANIZATION)。*

# Aegis 第十六轮：咨询后台教师使用手册（全板块覆盖审计）

> 分支:`main` · 时间:2026-08-31 · 系列:[ROUND-15-FRONTEND-CALM-THEME](ROUND-15-FRONTEND-CALM-THEME.md) → 本篇
> 性质:**纯文档轮次——后台 9 大板块 × 全部功能按钮逐一核对,产出面向教师的零术语使用手册**

---

## 1. 背景与问题定位

第十五轮完成前端主题升级后复查发现:咨询后台( `/admin` )的功能文档存在结构性缺口——

- **没有一份以教师为读者的操作文档**。README 的「管理端」功能清单只有 8 条概括性 bullet;[demo-script](../demo-script.md) 是演示脚本而非操作手册;[architecture](../architecture.md)/[safety-design](../safety-design.md) 是技术视角。
- **若干功能按钮在任何文档中均无说明**:`Rebuild`/`Backup`(知识库重建/备份)、`Dispatch`(手动派发任务)、`Retry`(任务重试)、`Run Eval`(触发综合评测)、板块折叠与「点击行看详情」的交互,在全部既有 md 中均未作为「教师可操作的功能」出现过。
- 权限表述有歧义:`app/api/deps.py` 的 `require_admin` 实际放行 **admin 与 teacher 双角色**(`STAFF_ROLES`),即教师拥有后台全部操作权限,而 `admin.py` 模块 docstring 仍写「全部要求 admin 角色」。文档必须以代码实际行为为准。

## 2. 板块 × 文档覆盖核对结论

逐板块核对 `static/admin.html` + `static/admin.js` 的全部按钮与既有 md 覆盖情况:

| 后台板块 | 功能按钮/交互 | 既有文档覆盖 | 本轮处置 |
| --- | --- | --- | --- |
| 顶栏(状态胶囊/账号/刷新/退出) | 刷新、退出 | 无按钮级说明 | 纳入手册 §一 |
| 指标卡 ×6(只读) | — | README 提及面板名 | 纳入手册 §一 |
| AGENT RUNTIME 自治协作状态 | 折叠/展开 | 仅技术文档 | 纳入手册 §三.8 |
| CASES 风险个案闭环 | Acknowledge、Add Note、点击看详情、折叠 | demo-script 提及操作,无按钮释义 | 纳入手册 §二.2 |
| KNOWLEDGE 知识库维护 | Search、Upload、**Rebuild**、**Backup**、折叠 | README 一句话提及前两者;**后两者无任何文档** | 纳入手册 §三.4 |
| REPORTS 风险报告 | Approve、Dismiss、点击看详情、折叠 | demo-script 提及,无效果说明 | 纳入手册 §二.1 |
| Agent Trace | 点击行看完整链路、默认折叠 | learning guide(开发者视角) | 纳入手册 §二.3 |
| 详情面板 | 点击任意行联动 | 无 | 纳入手册 §一通用技巧 |
| Tool Jobs | **Dispatch**、**Retry**、点击看详情、折叠 | **按钮级零覆盖** | 纳入手册 §三.5 |
| Tool Records | 点击看详情 | 无 | 纳入手册 §三.6 |
| Eval / Audit | **Run Eval**、审计行点击 | 「一键触发评测」一句话 | 纳入手册 §三.7 |

## 3. 如何改动

### 3.1 新增 `docs/admin-teacher-guide.md`(本轮唯一正文产物,单文档承载全部板块)

- **结构**:一(后台是什么/如何进入/页面布局图/通用技巧) → 二(日常主线:报告→审批→个案) → 三(支持板块逐个展开) → 四(教师视角 FAQ 七问) → 五(术语小卡七条)。
- **每个按钮统一四栏口径**:按钮名 / 作用 / 什么时候用(场景) / 点了之后会发生什么(效果)。
- **语言纪律**:不出现协议名、模块路径、配置键;技术概念全部翻译(如「死信=重试多次仍失败、等人工处理的任务」);界面英文按钮(Approve/Search/Dispatch…)保留原文并给出中文释义,方便对照屏幕。
- **如实描述权限**:教师与管理员后台权限相同(依据 `deps.py` 的 `STAFF_ROLES`);学生账号无法进入。
- **如实描述边界**:报告 Dismiss 后不可改回;dead 任务不影响报告/个案数据;Run Eval 使用内置测试题而非真实学生数据。

### 3.2 文档索引同步

- `README.md`:文档清单新增本手册链接(置于「安全设计」之后);records 演进链追加「后台教师手册」。
- `Aegis项目逐文件学习指南.md`:文末轮次链追加 ROUND-16。
- `docs/records/ROUND-16-ADMIN-TEACHER-GUIDE.md`:本篇。

### 3.3 明确不做的事

- 不改界面代码与按钮文案(界面中英文混排属产品决策,本手册以「原文+释义」方式兼容;若未来要统一按钮语言,应另开轮次)。
- 不修正 `admin.py` 模块 docstring 的「全部要求 admin 角色」表述与 `STAFF_ROLES` 实际行为的出入(代码注释问题,不影响运行;为避免本轮混入代码变更,留待后续代码轮次顺手修正)。

## 4. 验证记录

- 按钮清单与 `static/admin.html`(板块与按钮 ID)/`static/admin.js`(事件绑定:`handleClick`、`#search-knowledge`、`#upload-knowledge`、`#rebuild-knowledge`、`#backup-knowledge`、`#run-tool-worker`、`#run-eval`、折叠交互)逐一比对,手册覆盖全部 11 个板块与全部 12 类交互,无遗漏。
- 权限结论核对 `app/api/deps.py`(STAFF_ROLES)与 `app/api/admin.py`(全部路由 `Depends(require_admin)`)。
- 状态枚举核对 `app/models.py`:报告 pending/approved/dismissed;个案 open/acknowledged;任务 pending/running/success/dead——手册中的状态说明与之一致。

## 5. 本轮文件清单

| 文件 | 改动 |
| --- | --- |
| `docs/admin-teacher-guide.md` | 新增:咨询后台教师使用手册(单文档覆盖全部板块) |
| `docs/records/ROUND-16-ADMIN-TEACHER-GUIDE.md` | 本篇 |
| `README.md` | 文档清单 + records 演进链 |
| `Aegis项目逐文件学习指南.md` | 文末轮次链 |

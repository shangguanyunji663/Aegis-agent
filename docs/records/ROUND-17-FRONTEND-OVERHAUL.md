# Aegis 第十七轮：前端整体改造 — 后台页签化布局、全中文界面与前端学习指南

> 分支:`main` · 时间:2026-08-31 · 系列:[ROUND-16-ADMIN-TEACHER-GUIDE](ROUND-16-ADMIN-TEACHER-GUIDE.md) → 本篇
> 性质:**纯前端轮次(不触碰任何 Python 行为)——按使用者反馈分四步落地:后台页签化布局 → 固定一屏仪表盘 → 界面全中文化 → 前端学习指南**
> 说明:本篇为合并文档。初版仅覆盖后台布局页签化(原 `ROUND-17-ADMIN-RIGHT-RAIL-TABS.md` / `ROUND-17-ADMIN-LAYOUT-TABS.md`),后按使用者要求,将界面全中文化与前端学习文档并入同一轮。

---

## 1. 背景与问题定位(按使用者反馈逐步暴露)

1. **右列堆叠**:后台右列竖排 4 张卡(详情/工具任务/工具记录/评测·审计),折叠后仍是一长条;点击列表行时详情在视口外,联动不可见。
2. **左/中列长条**:右列改好后,左列(协作状态/个案/知识库)与中列(风险报告/Trace)仍是「折叠按钮 + 竖长条」——报告 41 条把页面拉到数千像素;各板块独立折叠必然出现「有的收起有的展开」的混乱状态。
3. **卡片下方空白**:页签化后每列只剩一张卡,卡片高度随内容,下方留大片空白,不美观。
4. **界面英文**:按钮(Approve/Dismiss/Search/Upload/Rebuild/Backup/Dispatch/Retry/Run Eval)、状态枚举(high/pending/open/dead…)、意图与任务类型全是英文,对教师等于加密。

## 2. 设计方案与实施

### 3.1 第一步:右列「详情检查器 + 工作台」页签

- 详情卡 `position: sticky` 吸顶——点任意列表行,详情始终可见(修复「点完看不见」的缺陷);Tool Jobs / Tool Records / Eval·Audit 三卡合并为「工作台」页签卡,`Dispatch`/worker 状态收进工具任务页签头、`Run Eval` 收进评测页签头(控件跟着内容走)。
- 实测修复 grid 行被均分拉伸把工作台卡推到 2872px 的布局回归(`align-self: stretch + align-content: start`)。

### 3.2 第二步:左/中列页签化,折叠机制整体退役

- 左列 → `[个案|知识库|协作状态]` 页签卡;中列 → `[风险报告|Agent Trace]` 页签卡;与右列共用同一套 `seg-tabs/seg-tab/seg-panel` 组件(按 `data-tabs` 作用域分组)。
- 5 个 `▾` 折叠按钮、`data-panel` 属性、`admin.js` 的 `initCollapsible`、CSS 的 `.collapse-btn/.panel-card.collapsed` 系列全部删除;历史遗留 `localStorage["aegis:panel:*"]` 键启动时一次性清理。
- 列表封顶 `.seg-panel .stack { max-height: 48vh; overflow: auto }`,任何板块不再拉长页面。
- **动作联动**:批准报告后左列自动切到「个案」页签(新个案即时可见);Dispatch/RunEval 跳工作台对应页签;三张卡页签各自记忆(`aegis:tab-support/review/rail-tab`)。

### 3.3 第三步:固定一屏仪表盘

页签化后卡片下方留大片空白 → 后台改为**固定一屏**:

- `.admin-columns` 高度 `calc(100vh - 262px)` + `grid-auto-rows: minmax(0, 1fr)`——强制行高为可用高度,打断「自动行由内容撑开 → 百分比高度失效」的 grid 陷阱(实测:列高曾回到 9521px 即此因);
- 页签卡 `[data-tabs]` 改 flex 纵向,`card-body` flex:1 + overflow:auto——列表在卡片内部滚动,三列齐底;
- `body.admin-page { display: flow-root }` 建 BFC,修复顶栏 margin-top 穿透 body 造成的 16px 幽灵滚动;
- `detail-json` 紧凑化(110px/30vh);响应式降级:≤1180px 恢复自然高度 + 48vh 列表上限。
- 最终实测:`document.scrollHeight == innerHeight == 900`,页面零滚动、三列齐底无空白;短内容页签(协作状态/审计)下卡片依然满高。

### 3.4 第四步:界面全中文化

教师使用的后台不再出现英文按钮与英文状态:

- **HTML 静态文案**:页签「Agent Trace」→「对话回放」;`Search/Upload/Rebuild/Backup` → 搜索/上传知识/重建索引/备份知识库;`Dispatch/Run Eval` → 立即派发/运行评测;顶栏 eyebrow「COUNSELOR ADMIN」→「咨询后台 · 校园心理支持平台」;占位符(source.md/检索知识库)改中文示例。
- **JS 动态文案**:行内按钮 `Approve/Dismiss/Acknowledge/Add Note/Retry` → 批准/驳回/确认接案/添加备注/重试;`showDetail` 标题(Tool worker/Eval run/Knowledge rebuild/backup/upload)全部中文化;**枚举映射层**(第十八轮构想并入):`RISK_LABEL/REPORT_STATUS_LABEL/CASE_STATUS_LABEL/JOB_STATUS_LABEL/INTENT_LABEL/KIND_LABEL/ACTION_LABEL/TARGET_LABEL/AGENT_LABEL` 九张映射表 + `|| 原值` 兜底,把 `high/pending/open/dead/companion/send_email/update_report` 等后端枚举译为「高风险/待审批/待跟进/已转死信/陪伴/邮件通知/审批报告」;运行状态胶囊「UP/openai/langgraph_state_graph」→「运行正常 / 在线模型 / 状态图编排」。
- **登录页**(教师进入后台的路径):入口卡「COUNSELOR ADMIN」→「教师 / 管理员入口」、「ACCOUNT GATE」→「账号登录」;login.js 状态胶囊 UP/DOWN/ready → 运行正常/服务异常/就绪。
- **纪律**:翻译只在展示层——判断逻辑(`riskTone`、`data-status` 协议值)仍用后端原始枚举;映射表未收录的值显示原文而非 undefined。
- 已知保留:详情面板的 JSON 数据键(id/risk_level 等)来自后端协议,属数据非按钮,保持原样(手册已说明用途);学生端界面英文 eyebrow 属学生侧,不在本轮范围。

### 3.5 伴随产出:前端学习指南

新增 [docs/frontend-learning-guide.md](../frontend-learning-guide.md)——与后端《逐文件学习指南》同规格的前端姊妹篇:总览与零构建决策 → styles.css 设计系统(含固定一屏的 grid 调试复盘) → 登录页 → 学生端(SSE 解析与终稿覆盖) → 管理端(页签/映射层/事件委托) → 联调排错 → FAQ 与自检清单;每章配可运行示例(DevTools 实时改变量、SSE 原始流观察等)、常见易错点与练习。

## 4. 兼容性约束(全程未破坏)

数据容器 ID 与 JS 整写 className 契约(`status-pill/stack/report-row/split-message/message-bubble/history-item` 等)原样保留;`hidden !important` 保留;`data-action` 协议值(approved/dismissed/acknowledged 等)不改——按钮文字与协议值分离;后端 Python 零改动。

## 5. 验证记录

浏览器实测(1440×900,登录 admin):

- 三列页签卡 + 固定一屏:`scrollHeight == innerHeight`,零滚动、齐底无空白;页签切换/记忆/详情联动正常;
- 全中文:后台所有按钮、行标题(`高风险 · 待审批`/`跟进中`)、任务类型(`邮件通知 · 成功`)、审计动作、协作状态(记忆智能体等)、运行胶囊(运行正常 / 在线模型 / 状态图编排)均为中文;截图复核;
- `node --check` 三个 JS 通过;`pytest tests/test_api.py` 6/7(失败项为 `.env` 真实 GLM 限流的环境依赖,与本轮无关,详见遗留建议:测试固定 `AI_PROVIDER=mock`);
- 验证后清理页签测试痕迹、恢复默认页签;**未点击批准/立即派发**(真实副作用),联动以代码审查 + 同机制实测代替。

## 6. 本轮文件清单

| 文件 | 改动 |
| --- | --- |
| `static/admin.html` | 右列页签化;左/中列页签化;全中文文案;`?v=0.8.0` |
| `static/admin.js` | 页签分组联动;九张中文映射表;按钮/标题/状态文案中文化 |
| `static/styles.css` | `seg-*` 页签组件、固定一屏仪表盘、折叠样式清理 |
| `static/index.html` | 入口卡/eyebrow 中文化 |
| `static/login.js` | 状态胶囊中文化 |
| `static/student.html` | 缓存指纹随主题轮次同步 |
| `docs/frontend-learning-guide.md` | **新增**:前端学习指南(本篇伴随产出) |
| `docs/admin-teacher-guide.md` | 布局图与全部按钮名称同步中文界面 |
| `docs/records/ROUND-17-FRONTEND-OVERHAUL.md` | 本篇(合并原 ADMIN-LAYOUT-TABS 版) |
| `README.md`、`Aegis项目逐文件学习指南.md` | 轮次链与文档清单同步 |

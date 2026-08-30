# Aegis 第十五轮：前端「暖意疗愈」主题升级

> 分支:`main` · 时间:2026-08-31 · 系列:[ROUND-13-MEMORY-SKILL-DISTILLATION](ROUND-13-MEMORY-SKILL-DISTILLATION.md) → 本篇
> （第十四轮 QLoRA 风险模型的记录位于外部 `AegisTraining` 训练仓库，见 README「评测结果」节）
> 性质:**三端统一视觉主题重构 + 风险分级色条 + 无障碍修复 + 死代码清理（纯前端轮次,不触碰任何 Python 行为）**

---

## 1. 背景与动机

Aegis 是校园心理支持平台,但前端视觉仍是「工程演示」语气:条纹网格背景、生硬单层阴影、
陶土橙大面积作主色、风险报告在管理端只是纯文本行。对心理支持产品而言,视觉语气本身就是
产品设计的一部分——学生端需要「被接住」的放松感,管理端需要「一眼分级」的从容感。

本轮在**不引入任何构建步骤、外部字体、图片**的前提下,把三个页面(登录 / 学生端 / 管理端)
统一升级为「暖米白 + 鼠尾草绿」的疗愈主题。原样式已用 CSS 自定义属性组织
(`static/styles.css`),本轮以 token 层替换 + 组件层微调的方式演进,而非推倒重来。

## 2. 设计原则

1. **暖色低饱和**:暖米白底(`--bg #f6f3ec`)+ 鼠尾草绿主行动色(`--calm`/`--calm-strong`),
   陶土橙降级为点缀(CTA/警示),全部低饱和,无刺眼纯色。
2. **柔和层次**:单层硬阴影改为双层柔影;面板改用「亮卡浮于暖纸」结构
   (`panel-card` 用 `--surface`,内部行/输入用 `--surface-2`),去掉了旧的条纹网格背景。
3. **克制动效**:登录页两团 9s/12s 的呼吸圆光晕、卡片 hover 轻浮 1px、打字点动画柔化;
   `prefers-reduced-motion: reduce` 下全部动画与过渡自动关闭。
4. **无障碍补课**:补 `:focus-visible` 全局焦点环(旧样式 `outline: none` 且无替代);
   `--muted` 从 #8a8378(约 3.4:1)加深到 #6f6b60(≥4.5:1);新增 `--calm-strong`
   供小字号文字使用(白字不再压在浅绿上)。
5. **管理端分级可读**:风险报告/个案/trace 行按 `risk_level` 显示左侧 4px 色条 +
   标题着色(high 陶红 / medium 暖琥珀 / low 鼠尾草)。

## 3. 如何改动

### 3.1 `static/styles.css`(重写,972 行 → 约 650 行)

- **Token 层**:`:root` 新增 `--calm-strong`(深鼠尾草,文字级对比)、`--calm-grad`
  (气泡/发送键渐变)、`--info(-soft)`(管理端次色)、风险三组 `--risk-*`/`--risk-*-soft`、
  `--ring` 焦点环、双层 `--shadow-sm/md`;`html[data-theme="dark"]` 变量同步更新
  (该主题当前无开关,保持变量流可用以便未来启用)。
- **背景层**:`.portal-page`(居中暖光 + 两个呼吸圆 `::before/::after`)、
  `.student-page`(左上绿意 + 右下暖橙)、`.admin-page`(右上雾蓝 + 左下绿意)——
  替换旧的 32px 条纹网格;`background-attachment: fixed`。
- **组件层**:
  - 输入:`input/textarea/select` 统一暖白底、聚焦时 `--calm` 边框 + `--ring`
    (select 首次纳入样式);`::placeholder` 柔化。
  - 气泡:`.message-bubble` 加大内边距、行高 1.7、不对称圆角
    (assistant `18 18 18 6` / user `18 18 6 18`);user 气泡改 `--calm-grad` 深绿渐变 +
    白字(对比 ~4.6:1,旧浅绿底白字仅 ~2.9:1)。
  - Composer:`.split-composer` 变为圆角托盘(surface-2 底),发送键改胶囊形 +
    hover 上浮;`.signal-btn` 卡片化(hover 绿底);`.history-item(.active)` 绿染高亮。
  - 管理端:`.admin-metrics` 从 `repeat(5, …)` 改 `repeat(auto-fit, minmax(150px,1fr))`
    ——修复 6 张指标卡挤成 5+1 的换行怪相;`.report-row` 统一 4px 左色条
    (默认 `--border-strong`,tone 覆写);`.admin-logo` 等硬编码色收编为变量/渐变。
  - 登录页:登录卡 22px 圆角 + `--shadow-md`;`.entry-card` 顶部 4px 分色条
    (学生绿 / 管理蓝);`#toggle-auth` 首次获得可见样式(鼠尾草色 + 虚线下划线)。
- **动效层**:`@keyframes breathe`;`.typing-dots` 改鼠尾草色;全局
  `@media (prefers-reduced-motion: reduce)` 关闭动画/过渡。
- **死代码清理**:删除经全仓 grep 确认无引用的旧版三栏布局 CSS
  (`app-shell/sidebar/workspace/topbar/tabbar/auth-screen/auth-card/bubble-user/
  response/flow/avatar/chip/badge/trace-row/knowledge-result/hero-card/scroll-area` 等
  及 1220px/880px 旧断点),保留其中仍被引用的
  `.hidden/.auth-form/.callout/.primary-btn/.ghost-btn/.status-pill/.panel-card/
  .report-row/.mini-btn/.source-list/.knowledge-*/.eval-*` 等活跃规则。

### 3.2 `static/admin.js`(本轮唯一 JS 改动,约 6 行)

```js
const riskTone = (level) => (level === "high" ? "risk-high"
  : level === "medium" ? "risk-medium" : "risk-low");

function row(title, subtitle, data, actions = "", tone = "") {
  const el = document.createElement("div");
  el.className = `report-row ${tone}`.trim();
  ...  // innerHTML 结构未变,#trace-list .report-row > span 的两行截断依赖不受影响
}
```

`loadReports` / `loadCases` / `loadTraces` 三处调用点追加第五参 `riskTone(...)`。
不触碰任何既有类名与 DOM 结构。

### 3.3 三个 HTML

仅缓存指纹 `?v=0.3.0` → `?v=0.4.0`(每页 2 处:styles.css + 页面 JS),
确保老访客的浏览器不使用过期缓存;结构与 ID 零改动。

### 3.4 JS 类名耦合约束(本轮验证过的「不可改名」清单)

`student.js` 的 `setPill` 会整写 `status-pill ${tone}`、消息行整写
`split-message ${role}`;`admin.js` 的 `renderList` 整写 `stack`/`stack empty`、
`row()` 整写 `report-row`。因此以下类名在 CSS 重写中原样保留:
`status-pill(.secondary)`、`stack(.empty)`、`report-row`、`split-message(.user)`、
`message-bubble`、`message-role`、`history-item(.active)`、`history-dot`、
`history-empty`、`typing-dots`、`stream-meta`、`intro(.intro-title)`、
`row-actions`、`mini-btn(.approve/.dismiss)`、`knowledge-line/.knowledge-metric`、
`source-list`、`eval-grid/.eval-metric`、`panel-card(.collapsed)`、`collapse-btn`。
`.hidden { display:none !important }`(JS 登录切换依赖)原样保留。

## 4. 验证记录

- **浏览器实测(1440×900,本机 uvicorn + 当前 .env 配置)**:
  - 登录页:暖光背景、入口卡分色条、呼吸圆光晕正常渲染;
  - 学生端:真实登录 → 发送「我最近有点睡不好,想找人聊聊」→ 观察流式全过程
    (THINKING/streaming 状态胶囊、打字点、user 深绿渐变气泡、assistant 白卡回复、
    DONE 收态、历史列表 active 高亮)全部正常;
  - 管理端:6 张指标卡单行排齐;高风险报告行陶红色条 + 标题着色、trace 行 low 风险
    鼠尾草色条、行 hover 反馈、两行截断均正常。
- `node --check static/login.js static/student.js static/admin.js` → 通过。
- `python -m pytest tests -q` → **76 passed, 1 failed**
  (`tests/test_langgraph_checkpoint.py::test_checkpoint_persists_across_instances`,
  LangGraph SqliteSaver 跨实例 `get_state` 返回 None)。**该失败与本轮无关**:
  本轮仅改动 `static/` 下文件与文档,未触碰任何 Python 代码;测试使用独立 tmp_path
  检查点库,与运行中的预览服务亦无交互。属既有后端问题,留待后续轮次处理。
- 缓存指纹已升级,回滚方式:还原三个 HTML 的 `?v=` 即可强制客户端取回旧样式。

## 5. 本轮文件清单

| 文件 | 改动 |
| --- | --- |
| `static/styles.css` | 主题重写(972 → 约 650 行):token/背景/组件/动效/无障碍/死代码 |
| `static/admin.js` | `riskTone()` 辅助 + `row()` tone 参数 + 三处调用点 |
| `static/index.html` `static/student.html` `static/admin.html` | 缓存指纹 `?v=0.3.0` → `?v=0.4.0` |
| `README.md` | 文档清单追加本篇;records 演进链追加「前端疗愈主题」 |
| `Aegis项目逐文件学习指南.md` | 文末轮次链追加 ROUND-15 |
| `docs/records/ROUND-15-FRONTEND-CALM-THEME.md` | 本篇 |

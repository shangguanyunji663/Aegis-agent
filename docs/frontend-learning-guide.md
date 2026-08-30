# Aegis 前端学习指南 — 从零理解原生 JS 三端界面

> 本文档是《[Aegis项目逐文件学习指南](../Aegis项目逐文件学习指南.md)》（后端）的姊妹篇,按同样的「先为什么、再怎么写、配可运行示例与练习」的方式,完整讲解 `static/` 下前端三页(登录 / 学生端 / 管理端)的设计与实现。
>
> 读者定位:有 Python 基础、**不需要**前端框架经验的学生。你将看到:不用 React/Vue、不装 node_modules、不打包,只用原生 HTML/CSS/JavaScript,也能做出体验完整的流式对话界面——并理解每一步「为什么这样做」。
>
> 有效性以 `main` 分支当前代码为准;所有示例均在浏览器 DevTools 或命令行实测通过。

***

## 如何使用本指南

| 你是… | 路径 | 怎么走 |
| --- | --- | --- |
| 只想改改样式 | 快速路径 | 直接读第二部分(设计系统),10 分钟上手 |
| 系统学习前端 | 全程路径 | 按第一~六部分顺序读,每章完成「动手试一试」与「练习」 |
| 想抄架构做自己项目 | 全程 + 自检清单 | 读完用文末清单逐项对照 |
| 排错应急 | 查阅路径 | 直接跳第六部分(联调与排错)与第七部分 FAQ |

**前置自检**:会 HTML 标签与浏览器 F12;懂 JavaScript 变量/函数/`async await` 读法(不会写没关系,文中逐段解释);CSS 只需知道「选择器 → 属性: 值」。DOM、事件、SSE 等概念在文中首次出现时都会讲。

**与后端指南的对照**:后端第 12 站(HTTP 层)提供接口 ↔ 本指南第三~五部分消费这些接口;后端 `ChatResponse` ↔ 学生端气泡;后端工具任务 ↔ 管理端工作台。读完后端再读本文,能看懂「一条消息的完整旅程」。

***

# 第一部分 总览:前端在哪里、为什么这样设计

## 1.1 渲染链路:浏览器拿到的就是仓库里的文件

后端 `app/api/pages.py` 只有 27 行:三个路由(`/`、`/student`、`/admin`)各自 `read_text()` 读一个 HTML 文件原样返回,**没有模板引擎、没有字符串拼接、没有注入**。CSS/JS 由 `app/main.py` 的 `app.mount("/static", StaticFiles(...))` 作为静态文件服务。

为什么这样设计:前端即静态文件,意味着 (1) 后端零渲染心智负担,前后端只靠 JSON API 通信;(2) 部署时这 6 个文件可以独立放到任何 CDN;(3) 学习者看到的就是浏览器运行的,没有编译产物。

## 1.2 为什么零构建(不用 React/Vue/打包器)

- **教学优先**:克隆 → `pip install` → 打开浏览器,三步跑通;没有 `npm install` 失败、node 版本、打包配置这些「还没开始学就先劝退」的环节。
- **规模匹配**:三页界面、每页一个 JS 文件(96~283 行),原生 JS 完全可控;框架的价值(组件化、响应式)在这个规模体现不出来。
- **代价(诚实声明)**:没有组件复用(三个 JS 各自维护一份 `escapeHtml`)、没有响应式绑定(状态变了要手动改 DOM)。这是**有意识的取舍**,不是无知——文件头注释与本文多处会提醒这一点。

## 1.3 文件地图:6 个文件各管什么

| 文件 | 行数 | 职责 | 谁在用 |
| --- | --- | --- | --- |
| `styles.css` | ~660 | 三页共用的全部样式:token 层 → 组件层 → 页面层 → 响应式 → 动效 | 三页 |
| `index.html` + `login.js` | 121+119 | 登录/注册、角色重定向、Hero 区与状态胶囊(时段问候/服务状态) | 所有人 |
| `student.html` + `student.js` | 112+234 | 学生对话(与小暖):SSE 流式渲染、消息头像与入场动画、话题 chips、心情速选、紧急求助卡 | 学生 |
| `admin.html` + `admin.js` | 144+355 | 教师后台:三列页签卡、列表渲染、审批动作、详情检查器 | 教师/管理员 |

## 1.4 三个贯穿全程的契约(先记住,后面反复出现)

1. **className 整写契约**:JS 会**整只覆盖**某些元素的 `className`(如 `el.className = "status-pill " + tone`)。所以 CSS 里这些类名(`.status-pill`、`.stack`、`.report-row`、`.split-message`、`.message-bubble`、`.history-item`)**永远不能改名**,否则 JS 一运行样式就断。
2. **ID 即接口**:JS 顶部用 `$("#xxx")` 缓存全部元素引用;HTML 里这些 ID 同样不可改名。
3. **缓存指纹**:HTML 里引用资源带 `?v=0.13.0` 这样的版本号。改了 CSS/JS 就必须升级指纹,否则老访客的浏览器会用缓存里的旧文件——「我明明改了为什么没生效」九成是这个。

***

# 第二部分 styles.css:一套「疗愈」设计系统

## 2.1 为什么先讲 CSS 变量(Token 层)

文件第 1~45 行是 `:root` 里的几十个自定义属性:

```css
:root {
  --bg: #f6f3ec;          /* 暖米白纸感底 */
  --calm: #6f9d8b;        /* 鼠尾草绿:主行动色 */
  --calm-strong: #3e6b5a; /* 深鼠尾草:文字级对比 */
  --risk-high: #c9705a;   /* 风险分级色 */
  --ring: 0 0 0 3px color-mix(in srgb, var(--calm) 30%, transparent);
  ...
}
```

为什么:全站 20+ 处用到主色,如果写死色值,「换个主题色」要改 20 处;用变量后只改 `:root` 一处。更妙的是**深色主题**:文件里有 `html[data-theme="dark"] { --bg: #191713; ... }`——变量按属性选择器整体换值,组件规则一行都不用改(该主题当前无开关,但机制随时可用)。

`color-mix(in srgb, var(--calm) 30%, transparent)` 是"在 sRGB 色彩空间把两个颜色按比例混合"——比手调透明度rgba更语义化,改 `--calm` 时这些派生色自动跟着变。

**动手试一试**(无需改代码):打开任一页面 → F12 → Console 输入:

```js
document.documentElement.style.setProperty("--calm", "#7c6f9d")
```

回车,整个页面的绿色系瞬间变紫——这就是 token 层的力量。刷新即恢复。

## 2.2 页签组件:三张卡片共用的 seg-*

后台三列卡片全部用同一套页签结构(第十七轮引入):

```html
<section class="panel-card" data-tabs="review">
  <div class="seg-tabs">
    <button class="seg-tab active" data-seg-tab="reports">风险报告</button>
    <button class="seg-tab" data-seg-tab="traces">对话回放</button>
  </div>
  <div class="card-body">
    <div class="seg-panel active" data-seg-panel="reports">…</div>
    <div class="seg-panel" data-seg-panel="traces">…</div>
  </div>
</section>
```

原理只有两条 CSS:`.seg-panel { display: none }`、`.seg-panel.active { display: block }`——切换页签就是 JS 换 active 类。`data-*` 属性(`data-seg-tab`/`data-seg-panel`)是 HTML 允许的自定义数据属性,JS 用它把「哪个按钮」对上「哪个面板」,不需要 ID。

## 2.3 固定一屏仪表盘:一次真实的 grid 调试复盘

后台桌面端要求「三列齐底、页面零滚动」。第一版写完发现列高约束不生效,页面仍 9000+px。复盘两次踩坑(这个调试过程本身就是最好的教材):

**坑一:grid 自动行由内容撑开**。`.admin-columns` 定了 `height: calc(100vh - 262px)`,但 grid 的行默认 `auto`——行高被卡片内容(几百条报告)撑到 9521px,容器装不下就溢出。修复:`grid-auto-rows: minmax(0, 1fr)`,强制行高 = 可用高度,`minmax(0, …)` 的 **0 下限**是关键——`1fr` 默认等价 `minmax(auto, 1fr)`,auto 下限仍允许内容撑破。

**坑二:margin 穿透 body**。列高修好后页面还多 16px 滚动。逐层测量发现顶栏的 `margin-top: 16px` 发生了**外边距塌陷**——body 没有 padding/border 时,第一个子元素的上边距会「逃逸」到 body 外面,把整个 body 下推 16px。修复:`body.admin-page { display: flow-root }` 创建 BFC(块级格式化上下文),让子元素 margin 留在内部。

**经验**:grid/flex 布局出问题时,别猜,用 DevTools 的 Computed 面板逐层看 `height` 从哪一层开始不符合预期。

## 2.4 无障碍:三个容易忽略的细节

- `:focus-visible` 全局焦点环——键盘 Tab 用户必须看得见焦点在哪(默认 outline 被清除后必须补);
- `@media (prefers-reduced-motion: reduce)` 关闭全部动画——尊重系统「减少动态效果」设置;
- 对比度:`--muted` 从 3.4:1 加深到 4.5:1(WCAG AA 标准正文下限)。

**常见易错点**:改 token 只改了亮色,深色主题变量忘同步 → 未来开深色模式时满屏违和;在组件里写死 `#5c7197` 这类色值绕过变量 → 主题切换时成为「钉子户」。

**练习**:① 给 `:root` 加 `--radius-card: 22px` 并替换所有卡片圆角;② 用 DevTools 找出页面上一处对比度不足的文字;③ 解释为什么 `.hidden { display: none !important }` 的 `!important` 不能删(提示:JS 靠它压过 `.status-pill` 的 display)。

***

# 第三部分 登录页:index.html + login.js(97 行的完整认证流)

## 3.1 表单:拦截默认行为是第一课

```js
loginForm.addEventListener("submit", handleLogin);
async function handleLogin(event) {
  event.preventDefault();              // ① 阻止浏览器原生提交(否则整页刷新)
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",        // ② 允许携带/接收 Cookie
    body: JSON.stringify({ username: ..., password: ... }),
  });
  if (!response.ok) return showError("登录失败，请检查账号。");
  redirectByRole((await response.json()).user.role);
}
```

`credentials: "same-origin"` 让登录接口种下的会话 Cookie 之后自动携带——后端靠 Cookie 识别用户,少了它登录等于白登。`redirectByRole`:admin/teacher → `/admin`,其他 → `/student`,**前端只管跳转,权限由后端每个接口再验一遍**(前端跳转只是导航,不是安全边界)。

## 3.2 注册/登录切换与错误提示

两个表单叠在同一个卡片里,靠 `.hidden` 类切换显示;`showError` 把后端返回的 `detail`(如「邀请码错误」)显示在 `.callout.error` 里。注册身份选「教师」时 `regRole` 的 change 事件显示邀请码输入行——`classList.toggle("hidden", 条件)` 是全项目最高频的显示/切换手法。

## 3.3 状态胶囊:登录前就知道服务好不好

页面加载即调 `/api/health`,并**每 60 秒自动刷新一次**:服务正常时胶囊带绿色圆点显示「服务正常」,异常显示「服务异常」(红色圆点)。顶栏还有按当前时间变化的时段问候(夜深了/早上好/下午好/晚上好)+ 日期——`greeting()` 就是一个几行的 hour 分段函数,却让页面"活"了起来。这遵循全项目铁律:**状态展示要本地化、失败要给兜底文案,而不是白屏**。

**常见易错点**:忘记 `event.preventDefault()` 导致提交后页面刷新、错误提示一闪而过;fetch 不写 `credentials` 导致 Cookie 不生效;把明文密码存进 localStorage(本项目从不存储,只用 Cookie)。

**练习**:① 给登录按钮加「登录中…」禁用态(参照 student.js 的 `sendButton.disabled`);② 把错误提示改成 3 秒后自动消失(setTimeout + showError(""))。

***

# 第四部分 学生端 student.js:流式对话是怎么「逐字蹦出来」的

这是前端最精华的 211 行,分四块讲。

## 4.1 骨架:状态对象 + 元素缓存

```js
const state = { sessionId: null, sending: false, user: null };
const els = { health: $("#health"), messages: $("#messages"), ... };
```

`state` 集中存可变状态(当前会话、是否发送中),`els` 一次查询缓存所有元素——避免每次都 `document.querySelector`。`state.sending` 防止连点:发送期间 `sendButton.disabled = true`,结束在 `finally` 里恢复。

## 4.2 消息渲染与 XSS 防线

```js
function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";     // textContent 赋值 = 浏览器替你转义
  return div.innerHTML;              // 再读出来就是转义后的安全字符串
}
```

学生输入、模型回复都会插进 `innerHTML`,如果不转义,一句 `<img onerror=...>` 就是 XSS 攻击。这个四行的巧思:借助浏览器原生转义(textContent 赋值时 `<` `>` `&` 自动变实体),不手写正则替换。**纪律:凡是用户/模型产生的内容进 innerHTML,必须过 escapeHtml。**

## 4.3 SSE 解析:parseSse 的三个细节

后端把回复以 SSE(Server-Sent Events)格式推来,每条消息形如 `data:{"event":"token","content":"今"}\n\n`。前端用 `fetch` + `ReadableStream` 手动读流:

```js
function parseSse(buffer, onEvent) {
  const parts = buffer.split("\n\n");   // ① 事件以空行分隔
  const rest = parts.pop() || "";        // ② 最后一段可能是半截,留回缓冲区
  parts.forEach((part) => {
    const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
    if (!dataLine) return;
    onEvent(JSON.parse(dataLine.replace("data:", "").trim()));
  });
  return rest;
}
```

三个细节:① 事件边界是**空行**,不是单换行;② 网络分包可能恰好把一个事件切成两半——`pop()` 把不完整段留在缓冲区,下个网络包拼上再解析;③ 每个事件取 `data:` 行并 JSON.parse。**这就是「为什么不用框架也要懂协议」的例子**:理解了 SSE 的文本格式,20 行就能写出解析器。

## 4.4 事件协议与「终稿覆盖」的安全逻辑

流里的事件按序到达,各司其职:

| 事件 | 前端动作 |
| --- | --- |
| `start` | 记下 `session_id`(新会话首轮由后端分配) |
| `route` | meta 行显示「风险评估:低/中/高 · 正在准备回复」 |
| `skill` | 检索知识库时提示「已检索心理知识库…」 |
| `report` | 高风险时提示「已生成安全报告,等待管理员跟进」 |
| `token` | 逐字追加到气泡(打字机效果的来源) |
| `done` | **用后端的最终 answer 覆盖已直播内容**;移除 meta 行 |

重点看 `done` 里的终稿覆盖注释:低风险对话虽然逐字直播,但最终展示以「安全复核后的终稿」为准——前端这一行就是后端「RiskGuardian 复核后才算数」语义的落点。中/高风险则全程只有安全模板、没有直播(后端根本不发 token)。

## 4.5 欢迎屏、心情速选与会话历史

欢迎屏(intro)是「小暖」的头像 + 问候 + 四个话题 chips——chips 带 `data-quick` 属性,与左栏「心情速选」卡片共用同一套交互:点击把预设语句填入输入框(只填不发,把决定权留给学生——这是心理产品的细节)。因为 chips 会被「新会话」重绘,填入逻辑用**事件委托**挂在 `document` 上而不是逐个绑按钮。消息行现在带**头像**(小暖=鼠尾草「暖」圆标,用户=暖橙「我」圆标)并做入场动画;输入框 Enter 发送、Shift+Enter 换行(`requestSubmit()` 触发表单校验,比直接调 sendMessage 更正规)。

**常见易错点**:忘写 `clearWelcome()` 导致欢迎语和消息并存;流结束时忘恢复 `sending=false` 导致再也发不出;`JSON.parse` 直接裸奔(半截 JSON 会抛异常——parseSse 只解析完整段,这正是 ② 的意义)。

**练习**:① 给 `route` 事件的 meta 行加剩余时间预估;② 实现发送中按 Esc 取消(提示:AbortController);③ 解释为什么 `addMessage` 要返回 bubble 元素(提示:sendMessage 里还要往里打字)。

***

# 第五部分 管理端 admin.js:列表、页签与动作联动

## 5.1 renderList/setPill:两个「整写 className」的原语

```js
function renderList(target, items, emptyText, render) {
  target.innerHTML = "";
  if (!items?.length) { target.className = "stack empty"; target.textContent = emptyText; return; }
  target.className = "stack";
  items.forEach((item) => target.append(render(item)));
}
```

空态与非空态靠切换 `stack empty`/`stack` 表达——**JS 整写 className**,所以 CSS 侧这两个类名是契约。`row()` 工厂统一造列表行:`report-row` + 标题/副标题 + 可选按钮,并注册「点行看详情」。

## 5.2 枚举中文化映射层(第十八轮并入)

后端返回英文枚举(`high/pending/companion/send_email/update_report`…),直接给教师看等于加密。前端在**展示层**做映射:

```js
const RISK_LABEL = { high: "高风险", medium: "中风险", low: "低风险" };
const KIND_LABEL = { send_email: "邮件通知", write_ledger: "风险台账", ... };
row(`${report.id} · ${RISK_LABEL[report.risk_level] || report.risk_level} · ...`, ...)
```

两条设计纪律:① `|| 原值` 兜底——后端新增枚举时界面显示原文而不是 undefined;② **只改显示、不改判断**——`riskTone(report.risk_level)` 仍用原始值配色,`data-status="approved"` 仍是后端协议。**翻译在边界,协议在内核。**

## 5.3 页签分组与动作联动

```js
function activateTab(scope, name, { persist = true } = {}) { ... }
```

三张卡片各自 `data-tabs="support|review|workspace"`,页签记忆分键存 localStorage;`批准` 报告后 `activateTab("support", "cases")` 让左列自动跳到个案页签——**动作完成后把用户的视线带到结果处**,这是后台可用性的关键一跃。Dispatch/运行评测同理。

## 5.4 事件委托:283 行文件只绑一个 body click

 Approve/驳回/确认接案/重试按钮都是 `row()` 动态创建的,逐个绑事件要管理生命周期;本项目用**事件委托**:按钮带 `data-action`,在 `document.body` 上统一监听,点按后读 `target.dataset` 分发。新增一种行内按钮只需在 handleClick 加一个 `if` 分支。

**常见易错点**:给动态按钮在外层绑了监听又用 `stopPropagation` 打补丁(本项目不需要——委托天然覆盖);在 map 映射里漏了 fallback,后端新枚举显示 `undefined`;详情面板忘了 `escapeHtml`(审计 payload 里有用户输入)。

**练习**:① 新增一种审计动作的中文映射;② 给「个案」页签加「按状态筛选」;③ 解释 `#trace-list .report-row > span` 选择器为什么依赖 row() 的 innerHTML 结构。

***

# 第六部分 联调、验证与排错

```bash
node --check static/login.js static/student.js static/admin.js   # 语法(无构建的"编译检查")
python -m pytest tests/test_api.py -q                            # 页面与接口回归
```

改 CSS/JS 后**必须升级三个 HTML 里的 `?v=` 指纹**(版本号任意,变了就行)。浏览器排错三板斧:Console 看报错、Network 看请求(EventStream/Response 标签能直接看 SSE 原始流)、Elements 看类名是否被 JS 改写。

**第七部分 高频 FAQ**

- **改了样式没生效?** 指纹没升,浏览器用旧缓存。
- **点击没反应?** Console 有报错;或类名/ID 被改名破坏了 JS 契约。
- **401 被踢回首页?** `api()` 约定:未登录统一跳转,是特性。
- **SSE 只收到一半?** 看后端日志;前端 parseSse 对半截事件是安全的。
- **深色模式怎么开?** 变量已备好但无开关——这是已声明的扩展点,不是 bug。

**术语速查**:DOM=浏览器里的页面对象树;事件委托=在祖先上统一监听动态子元素;XSS=注入脚本攻击,防线是 escapeHtml;SSE=服务器单向推流的 HTTP 协议;BFC=让子元素 margin 不再穿透的格式化上下文;缓存指纹=URL 上的版本参数。

**自检清单**:□ 能说出 className 契约的三个类名 □ 能手写 escapeHtml 并解释原理 □ 能画出 SSE 事件的时序 □ 知道改样式后先升指纹 □ 能解释固定一屏的两个 grid/flex 关键属性 □ 给后台加过一个中文映射条目。

***

> 免责声明同项目主文档:本项目用于心理支持工程学习与展示,不提供医学诊断,不能替代专业心理咨询或危机干预服务。

# 心屿前端学习指南 —— 从零读懂 Vite + React 19 + TypeScript 三概念 SPA

> 本文档是《[Aegis项目逐文件学习指南](../Aegis项目逐文件学习指南.md)》（后端）的姊妹篇，按同样的「先为什么、再怎么写、配练习」方式，讲清 `frontend/` 这套前端的设计与实现。
>
> 读者定位：有 Python 基础、**不需要**前端框架经验的人。你会看到：登录页 / 学生端 / 管理端三页如何在一份 SPA 入口之上跑起来，三个设计概念如何共享同一套数据层而各自换肤，流式对话如何「逐字蹦出来」——并理解每一步「为什么这样做」。
>
> 有效性以 `main` 分支当前代码为准；所有路径、行号、类名均已逐一对照源码核实。

## 与旧版的差异（重要）

本文档此前基于**已废弃的 `static/` 原生 JavaScript 实现**撰写——那套实现是三份 HTML 加三份 JS（`login.js` / `student.js` / `admin.js`）、一份约 760 行的 `styles.css`、一个 `theme.js` 主题切换器，以及手工维护的 `?v=` 缓存指纹。**第二十轮前端重写时，`static/` 目录已整体删除**，那些文件今天都不存在了。

本次重写后的对应关系：

| 旧版（已删除） | 当前 |
| --- | --- |
| `static/index.html` + `login.js` 等三份 HTML/JS | `frontend/index.html` + `src/App.tsx` + `src/concepts/*/`（SPA 单入口） |
| 零构建，改完刷新即可 | Vite 8 + React 19 + TypeScript 6，需 `npm run dev` / `npm run build` |
| `?v=0.14.1` 手工缓存指纹 | Vite 产物文件名带内容 hash，配合 `Cache-Control: no-cache` |
| 四套配色主题 `warm` / `ocean` / `forest` / `playful`，服务端写库、跨设备同步 | 三个**设计概念** `letter` / `radio` / `atlas`，只存 `localStorage`，不落库、不跨设备 |
| `theme.js` + `html[data-theme]` 多主题块 | `html[data-theme]` 只剩 `light` 一档（首屏注入）；外观交给 `html[data-concept]` |
| 手写 `escapeHtml` 防 XSS | React 转义，`dangerouslySetInnerHTML` 在 `frontend/src/` 中零命中 |
| 原生 `className` 整写契约、事件委托 | JSX 状态驱动；事件委托只剩动效层（`shared/fx.ts`）在用 |

`docs/records/ROUND-15` ~ `ROUND-18` 是**历史记录**，描述的是 `static/` 时代的决策，文中表格与代码为当时原样、仅供追溯，不要照着改代码。重写与场景取色的结论见 [ROUND-20-FRONTEND-SCENE-DRIVEN.md](records/ROUND-20-FRONTEND-SCENE-DRIVEN.md)。

***

## 如何使用本指南

| 你是… | 路径 | 怎么走 |
| --- | --- | --- |
| 只想改改样式 | 快速路径 | 直接读第二部分（令牌系统），10 分钟上手 |
| 系统学习前端 | 全程路径 | 按第一 ~ 六部分顺序读，每章完成「动手试一试」与「练习」 |
| 想抄架构做自己项目 | 全程 + 自检清单 | 读完用文末清单逐项对照 |
| 排错应急 | 查阅路径 | 直接跳第七部分（联调与排错）与高频 FAQ |

**前置自检**：会 HTML 标签与浏览器 F12；懂 JavaScript 变量 / 函数 / `async await` 的读法（不会写没关系，文中逐段解释）；CSS 只需知道「选择器 → 属性: 值」。React、组件、状态、Hook、SSE 等概念在文中首次出现时都会讲。

**与后端指南的对照**：后端第 12 站（HTTP 层）提供接口 ↔ 本指南第三 ~ 五部分消费这些接口；后端 `ChatResponse` ↔ 学生端气泡；后端工具任务队列 ↔ 管理端工作台。

***

# 第一部分 总览：前端在哪里、为什么这样设计

## 1.1 渲染链路：三个 URL，一份 HTML

后端 `app/api/pages.py` 只有约 80 行。`/`、`/student`、`/admin` 三个路由（`pages.py:66-78`）调用**同一个** `_render(request)`（`pages.py:46-56`），读**同一份** `frontend/dist/index.html`——也就是 Vite 产出的 SPA 入口唯一文件。页内从 `/` 跳到 `/student` 靠 React Router，不重新请求 HTML。

唯一的「注入」是首屏主题：`_resolve_theme`（`pages.py:33-43`）软解析会话用户偏好（无 Cookie / 会话失效 / 无记录一律回退 `DEFAULT_THEME`，**不抛 401**），然后把一段内联脚本插到 `<head>` 最前：

```html
<head><script>document.documentElement.setAttribute("data-theme","light");</script>
```

该脚本**先于** CSS 解析执行，浏览器一开始就用目标主题布局，不出现「先加载默认主题再跳变」的闪烁。`dist/` 尚未构建时，`_render` 返回一页可执行的构建指引（`pages.py:24-28`）而不是 500。

静态资源由 `app/main.py:95-96` 挂载：

```python
if DIST_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=DIST_DIR, html=True), name="spa")
```

`NoCacheStaticFiles`（`main.py:17-23`）在每个静态响应上加 `Cache-Control: no-cache`，但**保留 ETag 协商**——浏览器下次带 `If-None-Match` 回来，服务端回 304，不传陈旧文件，又不必每次都重下。挂载写在页面路由**之后**，保证 `/`、`/student`、`/admin` 优先走带注入的 `pages` 路由。

**为什么这样设计**：前后端同源，Cookie 会话天然携带，CSRF 与 XSS 的面都小；SPA 入口唯一，构建产物可以整体放 CDN；学习者看到的即是运行的，中间没有模板引擎这一层黑盒。

## 1.2 目录地图

```
frontend/
├─ index.html            SPA 入口模板(Vite 读取它生成 dist/index.html)
├─ vite.config.ts        插件 + dev 代理
├─ package.json          四个脚本:dev / build / lint / preview
├─ public/               原样拷贝:favicon.svg、media/night-lake.mp4
└─ src/
   ├─ main.tsx           挂载根、注入 Provider 与 CSS 顺序
   ├─ App.tsx            路由与角色守卫 + 概念页映射
   ├─ lib/               类型、fetch 封装、枚举中文映射、鉴权/概念上下文、场景取色
   ├─ hooks/             useChat(SSE 引擎)、useAdminData、useSystemStatus
   ├─ shared/            三概念共用:AdminConsole、LoginHero、ConceptSwitcher、console.css、fx、premium
   ├─ concepts/          letter / radio / atlas,各含 Login / Student / Admin + 自己的 css
   └─ styles/base.css    重置、无障碍、等宽数字、切换器外观
```

依赖版本（`package.json:19-30`）：`react` / `react-dom` ^19.2.8、`react-router-dom` ^7.18.4、`vite` ^8.3.0、`typescript` ~6.0.2、`oxlint` ^1.81.0。**没有 UI 组件库**——所有控件都是手写元素加手写 CSS，这是刻意的：心理产品的质感来自排版与留白，而不是组件库的默认皮。

## 1.3 三个贯穿全程的契约

1. **别名不可删**：`shared/console.css:10-33` 在 `html[data-concept="…"]` 上把概念基色解成 `--surface` / `--surface-2` / `--accent` / `--hot` / `--cns-ok` / `--cns-warn`。`AdminConsole.tsx` 与 `LoginHero.tsx` **只吃别名**，删掉任何一个，共享组件立刻掉色成透明。
2. **CSS 类名即接口**：与旧版的「JS 整写 className」不同，现在类名写在 JSX 里，但 `shared/fx.ts:10-36` 维护着一份**类名白名单**（`TILT` / `SPOT` / `MAGNET` / `RIPPLE` / `FADE_CONTAINERS`），靠 `MutationObserver` 补打 `data-tilt` 等属性。**改名等于静默失去动效**——不会报错，只是页面变闷。
3. **SSE 事件名不能改**：`types.ts:50-57` 的 `ChatStreamEvent` 联合类型与后端 `app/models.py:99-111` 的 `sse_event` 映射表一一对应，改名等于前端收不到分支。

***

# 第二部分 令牌系统：基色、别名与两层 CSS

## 2.1 为什么先讲令牌——以及「基色 → 别名」这个方向

全站几十处用到主色。写死色值意味着「换个主题色」要改几十处；用 CSS 变量后只改一处。但**光有变量还不够**：如果三个概念各自定义同名变量、共享组件又直接吃那个名字，那么共享组件就得给每个概念各写一份覆盖规则——三份重复，且每加一个概念就多一份。

本项目的解法是**两层**，方向**不可颠倒**：

- **概念层提供基色**（`concepts/*/ *.css` 文件末尾的令牌块）：letter 的 `--pine` / `--seal` / `--sheet`（`letter.css:1216-1234`）、radio 的 `--amber` / `--teal` / `--panel`（`radio.css:1039-1057`）、atlas 的 `--sea` / `--coral` / `--chart`（`atlas.css:1084-1101`）。
- **共享层解成别名**（`shared/console.css:10-33`）：`html[data-concept="letter"] { --surface: var(--sheet); --accent: var(--pine); --hot: var(--seal); ... }`。

共享组件只写 `var(--surface)`、`var(--accent)`，因此换概念即整体换肤，**共享组件的样式规则一行都不用改**。这就是 `docs/architecture.md` 第 10 节说的「翻译在边界，协议在内核」。

各概念令牌块还定义了 `--ink` / `--muted` / `--line` / `--line-strong` / `--focus` / `--shadow` 与字体栈（`--sans` / `--song` / `--mono` / `--kai`），这四个是**共享层直接吃的**，不参与别名解算。

`color-mix(in srgb, var(--accent) 12%, transparent)` 是在 sRGB 空间按比例混色，比手调 `rgba` 更语义化：改 `--accent` 一处，所有派生色与焦点环、选中态边框自动跟随。

**动手试一试**：开 DevTools → Console 输入

```js
document.documentElement.dataset.concept = "atlas"
```

回车，整页立刻变成海图配色（不需要刷新，因为 CSS 属性选择器是响应式的）。注意共享工作台的按钮、徽章、面板**一起变了**——这就是别名契约在起作用。再切回 `letter` 恢复。

## 2.2 概念切换：localStorage → data 属性

切换链路只有三步（`lib/concept.tsx`）：

1. `CONCEPT_META`（`concept.tsx:9-13`）定义三概念的名称、图标字与一句话意象；`ConceptSwitcher.tsx:6` 的 `ORDER` 决定切换器里的排列顺序。
2. 点按钮调 `setConcept`（`concept.tsx:37-41`）：写 `localStorage["aegis:concept"]` → 更新 state → `reveal` 计数加一。
3. `useEffect`（`concept.tsx:33-35`）把 state 落到 `document.documentElement.dataset.concept`，CSS 由此整体换肤；`reveal` 变化时渲染一个带 `key` 的 `.fx-reveal`（`concept.tsx:46`）触发一次揭幕动画。

首屏读取走 `initialConcept()`（`concept.tsx:24-27`）：只认 `"radio" | "atlas" | "letter"` 三个值，其他一律回退 `letter`——**白名单校验**，防止手改 localStorage 塞进无效键导致全站掉色。

**必须记住**：概念**不落库、不跨设备同步**。它只在这台浏览器里。`app/repository/store.py:58-59` 的 `THEME_CHOICES = ("light",)` 与 `DEFAULT_THEME = "light"` 是服务端注入的唯一取值来源（亮暗双模式已按需求移除）；`PUT /api/auth/me/theme` 端点仍在（`app/api/auth_routes.py:97-105`），但**前端已不调用**。那条链路现在只是首屏 `data-theme` 的单值兼容。

## 2.3 场景取色：让界面的颜色由背景决定

第二十轮最关键的一次设计决定。`lib/scene.ts` 把背景（电台的 `<video>`、信笺与群岛的 hero 照片）画进一块 **48×27 的离屏 canvas**，每 90ms（`scene.ts:28`）取一次像素，分两个区域统计平均色：

- **全画面** → 页面情绪（品牌、页脚、洗色层）
- **下中部**（视口 x 28%–72%、y 44%–86%，`scene.ts:23`）→ 认证卡所在位置，卡片颜色直接跟这块背景走

结果写进 `:root` 的 CSS 变量：`--scene-r/g/b`、`--scene-card-r/g/b`、`--scene-lum`、`--vid-warm`（`scene.ts:165-174`）。`shared/premium.css:520-545` 从这些原始值派生出玻璃卡的描边、内高光、光晕、幕布与文字色。

**为什么主信号是色温而不是亮度**——这是量过之后才定下来的：素材在 13.88s 循环内平均亮度 0.1405 → 0.1645，跨度只有 0.024（几乎不变）；而冷暖 `r−b` 从 −0.216 到 +0.034，跨度 0.250，是亮度的十倍。用户看到的「一开始偏黑、后来转黄」是**色相变化**。用亮度驱动文字反色，联动幅度几乎为零。归一化于是按 `r−b` 进行，并用**略长于循环的滑动窗口**（160 帧 ≈ 14.5s > 13.88s，`scene.ts:25`）保证循环点首尾一致、不跳变；静态图只采 16 帧就冻结区间（`FREEZE_AFTER`，`scene.ts:27`），不必等满一整轮。

两个已记录的坑：`scene.ts:157-163`——窗口没攒满时 `hi−lo` 被 0.08 的兜底撑开，归一化直接顶到 0/1，表现为「颜色钉死在某个极端、几秒后突然跳一下」，解法是让原始信号与归一化信号按填充进度线性混合；`scene.ts:88-96`——canvas 被跨源污染时只 `console.warn` 一次就停用取色，界面回退主题默认色，不白屏、不刷屏。

## 2.4 无障碍与响应式：四个容易忽略的细节

`styles/base.css` 只有 153 行，但每一段都有理由：

- **`.num`（`base.css:31-34`）**：指标与台账数字统一 `IBM Plex Mono` + `tabular-nums`，数字跳动时台账不抖。等宽数字不是审美偏好，是可读性。
- **`:focus-visible`（`base.css:41-44`）**：先 `:focus { outline: none }` 再用 `:focus-visible` 补 2px 焦点环。键盘 Tab 用户必须看得见焦点在哪，鼠标点击又不该有环——`:focus-visible` 正好区分这两者。
- **`prefers-reduced-motion`（`base.css:87-93`）**：全局把动画与过渡压到 0.01ms。登录页的水波、雾带、口号逐字动画还额外用 `window.matchMedia` 在 JS 侧提前判断（`letter/LetterLogin.tsx:47`、`atlas/AtlasLogin.tsx:79`），连滤镜都不挂载。
- **响应式（`console.css:498-505`）**：`.cns` 三栏在 1180px 以下降为两栏并把工具区整行下移，760px 以下单栏。三个概念的学生端工作区各有独立断点（`ls-worktop` / `rg-studio` / `at-deck`）。

**常见易错点**：在组件里写死 `#e8a44a` 这类色值绕过变量 → 换概念时成为「钉子户」；在概念层直接改 `--surface` 而不动基色 → 别名解算链被截断，别处引用 `--pine` 的规则全部失效。

**练习**：① 给 `:root` 加一个 `--radius-card` 并在三个概念里统一替换卡片圆角；② 用 DevTools 找出一处对比度不足 4.5:1 的正文；③ 解释为什么 `console.css:258` 与 `:451` 要为 radio 单独覆盖 `.cns-btn.primary` / `.lgh-go` 的文字色（提示：radio 是暗色本体，`color: var(--surface)` 会变成深字压深底）。

***

# 第三部分 登录页：渐进披露的「输入框即入口」

登录页的骨架在 `shared/LoginHero.tsx`（50 行），三套外壳在各自的 `*Login.tsx`。

## 3.1 为什么是渐进披露

旧版登录页第一屏就是两个表单（登录 + 注册切换）。现在第一屏只有一个大输入条 `.lgh-inputbar` 和几个话题 chips——点任意一处才展开认证卡（`letter/LetterLogin.tsx:138` 的 `onActivate` 把 `showAuth` 置真）。**为什么**：登录页的第一任务不是「填表」，而是「让人愿意开口」。先给一个像聊天输入框的东西，认知成本最低；表单是「你决定要说了」之后的收银台。

`LoginHero` 是纯展示组件（`LoginHero.tsx:12-50`）：接收 `slogan` / `placeholder` / `chips` / `actionLabel` / `onActivate`，自己不管状态。三个概念传入各自的文案，共享交互与样式（`.lgh-*`，`console.css:358-494`）。`onActivate(topic)` 的 `topic` 为 `null` 表示点的是输入条本身——概念页据此决定要不要显示「想聊：XXX —— 登录后继续」的话题回显条（`.lgh-topic`）。

## 3.2 表单：受控组件与两条提交路径

三个登录页的表单结构一致（以 `letter/LetterLogin.tsx:145-191` 为例）：

```tsx
async function submitLogin(event: FormEvent) {
  event.preventDefault();
  setError("");
  setBusy(true);
  try {
    await login(username.trim(), password);
  } catch {
    setError("领取失败,请核对领件人与暗号。");
  } finally {
    setBusy(false);
  }
}
```

**受控组件**是这个模式的核心：`value={username}` + `onChange={(e) => setUsername(e.target.value)}`——状态在 React 里，DOM 只是状态的镜像。旧版里 JS 手动读 `input.value` 再写回 DOM 的双向同步，现在完全消失了。`event.preventDefault()` 依然要写：它阻止浏览器原生表单提交（否则整页刷新，错误提示一闪而过）。

`busy` 状态同时驱动按钮禁用与文案切换（`核对中` / `领取信匣`），这是防连点的最简做法。注意后端错误信息**不直接展示**——`catch` 里只给一句概念化的隐喻文案。这是有意的：后端 `detail` 是给开发者看的，把「邀请码错误」原样弹给师范生并不改善体验。

## 3.3 状态胶囊：登录前就知道服务好不好

`hooks/useSystemStatus.ts` 轮询 `/api/health`（未登录）或「健康 + 模型状态」（已登录），间隔 60 秒（`useSystemStatus.ts:40`）。`healthText` 依概念换隐喻（「邮路畅通」/「邮路中断」），由三套外壳各自渲染成「邮路 · 畅通」/「SIGNAL OK」/「港口 · 可通航」。已登录且 provider 为 `mock` 时 `modelText` 显示「演示模式」，避免评审者误以为接了真模型。

**这就是全项目铁律**：状态展示要本地化、失败要给兜底文案，而不是白屏。`api.health()` 走裸 `fetch`（`api.ts:65`）而非 `request()`——健康检查本来就不该在 401 时把用户踢去登录页。

***

# 第四部分 学生端：SSE 流式对话是怎么「逐字蹦出来」的

`hooks/useChat.ts`（154 行）是三概念**唯一**的聊天引擎。概念外壳只负责把 `turns` 渲染成信纸 / 接线日志 / 航海日志。

## 4.1 状态机与数据结构

流式阶段机（`useChat.ts:10`）：

```ts
export type StreamPhase = "idle" | "waiting" | "speaking";
```

`idle`（待机）→ `waiting`（后端在跑：展信 / 拨号 / 展信中）→ `speaking`（第一个 `token` 到达）→ 回到 `idle`。三个外壳把这个词翻译成自己的隐喻：letter 是 `READY / WAITING / WRITING`（`LetterStudent.tsx:119`），radio 是 `STANDBY / CONNECTING / ON AIR`（`RadioStudent.tsx:19-23`），atlas 是 `ANCHORED / SIGNALING / REPLYING`（`AtlasStudent.tsx:110`）。

一条消息在渲染层叫 `Turn`（`useChat.ts:12-20`）：`id` / `role` / `content` / `risk` / `retrieved` / `reported` / `at`。后四个是流式过程中「打补丁」进去的元信息。

防连点用 **ref 而不是 state**（`useChat.ts:47`）：

```ts
const sendingRef = useRef(false);
if (!trimmed || sendingRef.current) return;
sendingRef.current = true;
```

**为什么**：`send` 是 `useCallback` 闭包，读 state 拿到的是渲染时的快照，连点两次会读到同一个 `false`。ref 是同一个对象，读到的一定是最新值——这类「需要立刻读到最新」的场景都该用 ref。

## 4.2 SSE 解析：半截帧为什么是安全的

后端把回复以 SSE 格式推来，每个事件形如（`app/api/chat.py:65-66`）：

```
event: token
data: {"event": "token", "content": "今"}

```

前端用 `fetch` + `ReadableStream` 手动读流（`useChat.ts:89-134`），解析函数是 `parseSseFrames`（`useChat.ts:25-39`）：

```ts
function parseSseFrames(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatStreamEvent[] = [];
  for (const part of parts) {
    const dataLine = part.split("\n").find((line) => line.startsWith("data:"));
    if (!dataLine) continue;
    try {
      events.push(JSON.parse(dataLine.replace("data:", "").trim()) as ChatStreamEvent);
    } catch {
      /* 半帧或心跳,丢弃 */
    }
  }
  return { events, rest };
}
```

三个细节，一个都不能少：

1. **事件边界是空行**（`\n\n`），不是单换行。
2. **网络分包可能恰好把一个事件切成两半**。`parts.pop()` 把不完整段留在缓冲区（`rest`），下个网络包拼上再解析（`useChat.ts:104-105`）。`JSON.parse` 外层的 `try/catch` 是**第二道防线**：即使有半帧漏到解析阶段，也只是丢弃，不会让整个流崩掉。
3. **每个事件只取 `data:` 行**。协议里还有 `event:` 行（后端写了但前端不用），`find` 精准定位。

`decoder.decode(value, { stream: true })`（`useChat.ts:103`）的 `stream: true` 不能省：它让解码器保留多字节字符被切断时的残余字节，下一块拼回来才完整。少了这个参数，一个中文汉字可能被拆成两个乱码字符。

## 4.3 七事件协议与「终稿覆盖」

| 事件 | 载荷 | 前端动作（`useChat.ts:107-132`） |
| --- | --- | --- |
| `start` | `session_id` | 记下会话 ID（新会话首轮由后端分配） |
| `route` | `intent`、`risk_level` | `patchAssistant({ risk })`，气泡旁显示风险徽章 |
| `skill` | `name` | 仅当 `name === "search_knowledge"` 时标记「已检索知识库」 |
| `report` | — | 标记「已转交值班室」，教师端会看到待审批报告 |
| `token` | `content` | 追加到 `answer` 并 `patchAssistant({ content })`（打字机效果的来源） |
| `done` | `response` | **用后端终稿覆盖已直播内容**，移除等待态 |
| `error` | — | 显示「这一句没能送达，正在重试」 |

重点看 `done`（`useChat.ts:122-129`）：

```ts
} else if (payload.event === "done") {
  const finalAnswer = payload.response?.answer;
  if (finalAnswer) {
    // 安全复核终稿覆盖低风险直播内容
    answer = finalAnswer;
    patchAssistant({ content: finalAnswer });
  }
```

**为什么必须覆盖**：低风险对话会逐字直播（`token` 事件），但直播内容只是**草稿流**——后端在发出 `token` 之后还要经过记忆更新与安全复核，最终 `answer` 才是定稿（`app/agents/orchestrator.py:264` 的 `RUN_COMPLETED` 携带 `response`）。前端这一行就是后端「RiskGuardian 复核后才算数」语义的**落点**。中 / 高风险则全程只有安全模板、没有直播（后端根本不发 `token`，见 `orchestrator.py:231` 的 `on_token=... if risk_level is RiskLevel.LOW else None`）。

`patchAssistant`（`useChat.ts:95-98`）是全 hook 的关键原语：

```ts
const patchAssistant = (patch: Partial<Turn>) =>
  setTurns((prev) => prev.map((t) => (t.id === assistantTurn.id ? { ...t, ...patch } : t)));
```

**按 id 匹配而不是按位置**。流式过程中 `turns` 会不断追加，靠 `[...prev, userTurn, assistantTurn]` 之后再改「最后一条」在并发场景下会写错对象；用唯一 id 匹配（`nextId()`，`useChat.ts:22-23`）则永远只改自己那条。React 的「不可变更新 + 重新渲染」在这里体现得很直接：改状态即改界面，没有一行 `innerHTML`。

## 4.4 发送、失败与滚动

`send`（`useChat.ts:73-147`）在发请求前就把 user / assistant 两条 `Turn` 一次性塞进 `turns`——assistant 那条 `content` 是空的，随着 `token` 到达被逐字填满。这带来一个 UX 细节：气泡**立刻出现**（带打字光标），用户马上看到「已经收到了」。

失败路径（`useChat.ts:141`）用 `setTurns((prev) => prev.filter((t) => t.id !== assistantTurn.id || t.content))` 把内容为空的 assistant 条目剔掉（用户的话留下，不留一个空气泡）。同时 `finally` 里 `sendingRef.current = false`——**复位必须放 `finally`**，放 `try` 末尾的话一次网络异常就再也发不出第二句。

自动滚底（`letter/LetterStudent.tsx:36-38`）的 `useEffect` 依赖 `[turns, phase]`：只在消息变化或阶段变化时滚，**不是每次渲染都滚**——否则用户想往上翻看历史时会被强行拽回底部。

## 4.5 XSS 防线：没有 `escapeHtml`，因为不需要

`frontend/src/` 中 `dangerouslySetInnerHTML` **零命中**。用户输入、模型回复、审计日志 payload 全部经 JSX 表达式插值，React 在渲染时对文本节点做转义。这是框架带来的**结构性安全**：不是「记得调用转义函数」，而是「默认就转义，除非你显式关掉它」。

**常见易错点**：想让多行文本换行就写 `dangerouslySetInnerHTML` → 安全防线直接消失。要换行用 CSS（`white-space: pre-wrap`，如 `console.css:272` 的 `.cns-json`）；要加粗用 JSX 元素而不是字符串里的标签。

**练习**：① 给 `route` 事件加一行「正在准备回复」的提示；② 实现发送中按 Esc 取消（提示：`AbortController`，把它接到 `api.chatStream` 的 `signal` 上，并在 `catch` 里区分 `AbortError`）；③ 解释为什么 `answer` 变量与 `turn.content` 要分开维护（提示：`patchAssistant` 是幂等的，`answer` 是累积器）。

***

# 第五部分 管理端：三段式共享工作台

管理端最值得学的一点：**三套外壳，零份重复**。`shared/AdminConsole.tsx`（459 行）被三个概念的 `*Admin.tsx` 复用，后者只负责渲染自己的顶栏（`Masthead` / `RadioBar` / `AtlasBar`）。

## 5.1 三段式布局与 `minmax(0, 1fr)`

`console.css:69-78` 的骨架：

```css
.cns {
  display: grid;
  grid-template-columns: minmax(280px, 336px) minmax(0, 1fr) minmax(296px, 356px);
  gap: 14px;
  height: calc(100vh - 108px);
  min-height: 500px;
}
```

**`minmax(0, 1fr)` 的那个 0 是本页最关键的一个字符。** `1fr` 默认等价 `minmax(auto, 1fr)`，`auto` 下限意味着「内容有多高就多高」——几百条报告会把中间列撑到几千像素，容器装不下就溢出。写成 `minmax(0, 1fr)` 相当于声明「这一列可以被压到 0，内容自己滚」。

但只有 grid 轨道还不够：grid / flex **子项默认 `min-height: auto`**，内容照样溢出。所以 `console.css:80-89` 的 `.cns-pane` 显式写了 `min-height: 0; min-width: 0;`——允许被压扁，内容交给内部 `.cns-list` / `.cns-stage-body` 的 `overflow: auto`。**两级都要写**：轨道给上限，子项给许可。

**经验**：grid/flex 布局出问题时别猜，用 DevTools 的 Computed 面板逐层看 `height` / `min-height` 从哪一层开始不符合预期。旧版在三列页签布局上还踩过第二个坑——顶栏的 `margin-top` 因外边距塌陷把整个 body 下推 16px，修复方式是给容器建 BFC（`display: flow-root`）；现在 `.cns` 用 `margin: 0 auto` 居中，不再有子元素外边距逃逸的机会。

## 5.2 数据引擎：一次快照拉全

`hooks/useAdminData.ts` 的 `refreshAll`（`useAdminData.ts:36-72`）用 `Promise.all` 并发拉 11 个接口，合成一份 `AdminSnapshot`（类型在 `types.ts:150-160`）：

```ts
const [reports, cases, traces, knowledge, jobs, worker, excel, alerts, evals, audits, agent] =
  await Promise.all([...]);
```

**为什么不是每个面板各拉各的**：首屏会有 11 个请求先后返回，面板内容会逐个「跳出来」；合成一次快照后所有面板同时就绪，且一次 `setSnapshot` 触发一次渲染。代价是 slowest-wins（一个慢接口拖住全部），对这个规模可接受。

写操作统一走 `act`（`useAdminData.ts:74-82`）：

```ts
const act = useCallback(async (run, detailTitle, after) => {
  const result = await run();
  showDetail(detailTitle, result ?? { ok: true });
  await after?.();
  await refreshAll();
}, ...);
```

「执行 → 把返回体塞进详情面板 → 可选副作用 → 刷新快照」四步固化，杜绝「忘了刷新」这一类 bug。后端返回什么就展示什么（`cns-json`，`console.css:265-276`），不做二次加工——教师要看到原始契约。

`AdminConsole.tsx` **不含任何 `fetch`**，只有 `api` 调用与渲染。数据与外壳彻底分离，这是它能被三个概念复用的前提。

## 5.3 枚举中文映射：翻译在边界，协议在内核

后端返回英文枚举（`pending` / `companion` / `send_email` / `update_report` …），直接给教师看等于加密。`lib/labels.ts`（116 行）做展示层映射，12 张表：

| 表 | 用途 |
| --- | --- |
| `RISK_LABEL` | `low` / `medium` / `high` |
| `REPORT_STATUS_LABEL` / `CASE_STATUS_LABEL` / `JOB_STATUS_LABEL` | 三类状态机 |
| `KIND_LABEL` / `INTENT_LABEL` / `ACTION_LABEL` / `TARGET_LABEL` | 工具任务、意图、审计动作、目标实体 |
| `AGENT_LABEL` | 7 个智能体的中文名 |
| `TOOL_BACKEND_LABEL` / `QUEUE_LABEL` / `PROVIDER_LABEL` | 运行时环境 |
| `EVAL_KEY_LABEL` | 6 项评测指标 |

两条设计纪律：

1. **`?? 兜底`**：`ACTION_LABEL[a.action] ?? a.action`（`AdminConsole.tsx:116`）。后端新增枚举时界面显示原文，而不是 `undefined`。注意**是 `??` 不是 `||`**——空串是合法值，`||` 会把它错译成原文。
2. **只改显示、不改判断**：`riskTone(r.risk_level)`（`AdminConsole.tsx:41`）仍用原始值算徽章色调，`api.admin.updateReport(id, "approved")` 仍传原始协议值。翻译只发生在渲染那一刻。

同一文件还提供三个时间格式化函数：`greeting()`（时段问候，`labels.ts:99-106`）、`dateLine()`（`labels.ts:108-111`）、`clockLine()`（`labels.ts:113-116`）。后两者接受 `now` 参数便于测试。

## 5.4 选中态、危险操作与无障碍

三个工作台变体（`AdminConsole.tsx:322-458`）的结构：顶部 `.cns-stats` 内联指标徽章（**替代铺满横条的指标大屏**，点击直接跳对应页签，`AdminConsole.tsx:324-332`），下面左列表 / 中审阅 / 右工具区。

几个值得学的细节：

- **驳回需要二次确认**（`AdminConsole.tsx:256-269`）：第一次点击只把按钮从 `mute` 换成 `danger` 并改文案为「确认驳回?」，第二次才真正提交。破坏性操作不该一键生效——用状态机做确认比弹窗轻，比没有确认安全。
- **`aria-selected` / `role="tablist"`**（`AdminConsole.tsx:337-350`）：页签的无障碍状态靠 `aria-selected` 表达，视觉选中靠 `.cns-tab.on`（`console.css:121-126`）。**两套状态各司其职**，删掉 CSS 类不影响读屏，删掉 aria 不影响视觉。
- **风险徽章只用三种色调**（`console.css:193-196`）：`.cns-badge.high` → `--hot`，`.medium` → `--cns-warn`，`.low` / `.ok` → `--cns-ok`，`.quiet` → `--muted`。语义色由概念令牌决定，组件不需要知道「红色代表什么」。

**常见易错点**：忘了空态渲染（`.cns-empty`，`console.css:198-206`）导致列表空白无解释；`cases` 分支忘了 `c.notes` 可能为 `undefined`；`Object.entries(snapshot.evals)` 忘记处理 `undefined` 值（`AdminConsole.tsx:436` 用 `String(value ?? 0)` 兜住了）。

**练习**：① 新增一种审计动作的中文映射；② 给工具区加一个「导出当前筛选」按钮；③ 解释为什么 `console.css:499` 在 1180px 断点必须同时把 `.cns-tools-pane` 的 `grid-column` 设为 `1 / -1`。

***

# 第六部分 动效层：不侵入 JSX 的四类反馈

`shared/fx.ts`（334 行）+ `fx.css`（273 行）是一套**行为式**动效基建：不往 JSX 里加事件、不加 hook，靠类名白名单 + `body` 级事件委托实现四种反馈。

| 反馈 | 实现 | 类名白名单 |
| --- | --- | --- |
| 倾斜 tilt | 光标相对位置 → `--rx` / `--ry` | `lg-slip`、`ls-sheet`、`rg-main`、`at-logbook-main` 等 10 个（`fx.ts:10-14`） |
| 聚光 spot | 光标位置写进 `::after` 径向渐变 | `ls-envelope`、`at-isle`、`rg-preset`、`cns-row` 等 14 个（`fx.ts:16-21`） |
| 磁吸 magnet | 按钮向光标轻移 `--tx` / `--ty` | `lg-wax`、`rg-power`、`at-sail`、`cns-mini` 等（`fx.ts:23`） |
| 涟漪 ripple | 点击位置 `--px` / `--py` + 重放动画类 | 20+ 个（`fx.ts:25-30`） |

`initFx()`（`fx.ts:119-334`）在 `App.tsx:33` 以 `useEffect(() => initFx(), [])` 启动，做四件事：① `mark(document.body)` 按白名单打 `data-*` 属性；② `MutationObserver` 监听 `childList` + `subtree`，**DOM 重渲染后 240ms 补标**（`fx.ts:124-130`）——这是 React 场景下的必需品；③ `body` 上挂 `pointermove`（passive）与 `click`，`requestAnimationFrame` 合帧；④ 返回清理函数，卸载时全部撤销。

**为什么三连属性选择器**（`fx.css:10`）：`[data-tilt][data-tilt][data-tilt]` 靠**特异度加权**压过概念层的 `html[data-concept="letter"] .ls-sheet { transform: rotate(-.35deg) }`——后者是 `0,2,1`，前者是 `0,3,0`。基础倾角不丢的办法是把它挪到 `--base-rot`（`fx.css:21-24`），倾斜时叠在标准 `rotate()` 之后。

**临界阻尼跟随**（`fx.ts:88-110`）是全项目最值得读的一段数学。CSS `transition` 在指针快速反向时会「重新起算缓动」，产生折返抖动；`smoothDamp` 把速度走引用传入 / 传出，每帧从上次速度继续积分，没有这个折返。稳定条件是 `smoothTime > 2×dt`，所以 `fx.ts:161` 按实测帧间隔动态兜底 `Math.max(FOLLOW_SMOOTH, dt * 2.2)`——机器快时保持紧（0.055s），机器慢时自动放宽到稳定值。收敛后 `raf = 0` 直接停，不留空转 rAF（`fx.ts:181`）。

还有两个刻意的省：`fx.ts:267` 的**概念门控**——只有 atlas 有光标扰动图层，信笺与电台没有，跟随器就不启动（实测白跑 4 次 style 写入/帧会让信笺 p50 从 12.2ms 涨到 18.1ms）；`fx.ts:200-209` 的 **SVG 滤镜参数缓存**——整数没变就绝不写 `scale`，因为写一次会让全屏 `filter: url(#atlas-water)` 作废重算。

**性能归因留档**（第二十轮最重要的结论）：「卡」的真凶不是代码。Chrome 默认把网页渲染在 **Intel 核显**上而独显 RTX 4060 闲置，`WebGL renderer` 字符串一查便知；同一页面强制独显后帧时间由 36.3ms 降到 6.1ms（×5.4）。此前基于「滤镜太贵」的优化方向被判定为误判，相关改动已全量回退。**排查任何「卡」之前，第一件事是查 renderer 字符串**；headless Chrome 的帧率数据不可用于下结论。

**常见易错点**：重命名白名单里的类名（如把 `cns-row` 改成 `console-row`）→ 静默失去聚光与涟漪，没有任何报错。改完 UI 后用 `grep -rn "\.新类名" frontend/src/` 确认 fx 清单里也要更新。

**练习**：① 给 `.cns-tile` 加一档 `magnet` 反馈；② 把 `FOLLOW_SMOOTH` 调到 0.15s，在慢机器上观察折返抖动是否回来；③ 解释为什么 `prefers-reduced-motion` 下 `initFx` 直接返回空函数而不是「注册了但什么都不做」（提示：省下的是 MutationObserver 的持续开销）。

***

# 第七部分 联调、验证与排错

## 7.1 日常命令

```bash
cd frontend
npm install          # 首次;含自托管字体包
npm run dev          # dev server :5173,/api 代理到 127.0.0.1:8000(vite.config.ts:7-12)
npm run lint         # oxlint,规则见 .oxlintrc.json
npm run build        # tsc -b && vite build → dist/
```

后端另开一个终端跑（`uvicorn app.main:app --reload`）。开发期**不要**用 `dist` 调试——dev server 有 HMR，改完即见；`dist` 只用于验证构建与托管链路。

注意 `npm run build` 是 `tsc -b && vite build`（`package.json:8`），**类型检查是构建的第一步**：类型不过就没有产物。所以「改了不生效」有时其实是 `tsc` 报错了。

## 7.2 验证清单

```bash
cd frontend && npm run lint && npm run build     # 类型 + 规范 + 产物
cd .. && python -m pytest tests/test_api.py -q   # 接口与鉴权回归
```

浏览器三板斧：Console 看报错、Network 看请求（`/api/chat/stream` 的 EventStream / Response 标签能直接看 SSE 原始流）、Elements 看最终 DOM 与 `html[data-concept]` 属性。

**改了样式没生效？** 先看 `html[data-concept]` 是不是你以为的那个值（`document.documentElement.dataset.concept`）。再硬刷新（Ctrl+F5）——Vite 产物文件名带内容 hash，`NoCacheStaticFiles` 只保证「不陈旧」，不保证「不重下」。

## 7.3 历史演进（简述第十五 ~ 二十轮）

| 轮次 | 做了什么 |
| --- | --- |
| [ROUND-15](records/ROUND-15-FRONTEND-CALM-THEME.md) | 三端统一「暖意疗愈」主题（`static/styles.css`），风险分级色条，无障碍修复。色板决策延续至今 |
| [ROUND-16](records/ROUND-16-ADMIN-TEACHER-GUIDE.md) | 纯文档轮次：后台九大板块 × 全部按钮的教师使用手册 |
| [ROUND-17](records/ROUND-17-FRONTEND-OVERHAUL.md) | 后台页签化 + 固定一屏仪表盘 + 界面全中文化 + 首版本指南 |
| [ROUND-18](records/ROUND-18-THEME-SWITCHER.md) | 四套配色主题 `warm`/`ocean`/`forest`/`playful` + 服务端首屏注入 + 按用户持久化跨设备同步 |
| [ROUND-19](records/ROUND-19-RAG-SEMANTIC-RERANK.md) | RAG 语义重排（后端） |
| [ROUND-20](records/ROUND-20-FRONTEND-SCENE-DRIVEN.md) | **前端整体重写**：Vite + React 19 + TS 三概念、场景取色主题化、双视频交叉淡化、卡顿归因到 GPU 选择 |

第 15 ~ 18 轮的对象（`static/` 目录、`theme.js`、四套配色主题、`?v=` 指纹）**已随第二十轮重写整体删除**。那一轮最有价值的两条经验保留至今：服务端在 `<head>` 最前注入以消除首屏闪烁；以及「令牌键的单一真相源在后端常量」这个思路——今天 `THEME_CHOICES` 收敛为 `("light",)` 后仍是后端说了算。

***

# 高频 FAQ

- **改了样式没生效？** 查 `document.documentElement.dataset.concept` 是否符合预期，再 Ctrl+F5。若改的是共享层（`console.css` / `premium.css`），确认当前概念确实消费了该别名。
- **点了没反应？** Console 有报错；或类名被改名脱离了 `fx.ts` 的白名单（动效静默失效）；或 ID 改动了——但注意现在 ID 只在 `<label htmlFor>` 与 `id` 之间配对，改一处不改另一处会让点击标签聚焦失败。
- **401 被踢回首页？** `lib/api.ts:36-42` 的 `kickToLogin` 会 `window.location.replace("/")`，`kicking` 标志防止并发 401 反复跳转打断表单交互。`me` / `login` / `register` 三个端点传了 `authOptional = true`，不会踢。**例外**：`api.chatStream`（`api.ts:86-92`）走裸 `fetch` 不经过 `request()`，所以流式请求遇到 401 只在气泡区显示「登录态已失效」，不会自动跳登录页——这是有意留的：正在输入的内容不该被导航丢掉。
- **SSE 只收到一半？** 看后端日志；前端 `parseSseFrames` 对半截事件是安全的（半截留在 `rest`，解析失败也只丢弃）。
- **概念怎么切换？** 右下角浮标（`.concept-switcher`，`base.css:97-113`，`z-index: 100`）。切换只写 `localStorage["aegis:concept"]`，**不落库、不跨设备同步**。默认 `letter`。
- **三个概念数据不一样吗？** 一样。数据层（`useChat` / `useAdminData` / `useSystemStatus`）与共享工作台（`AdminConsole`）都是共用的，只有外壳与文案不同。换了概念，学生端的会话列表、风险徽章、信件隐喻全变，但对话内容是同一份。
- **为什么 `dist/` 在 `.gitignore` 里？** 它是构建产物。`app/main.py:95` 用 `if DIST_DIR.exists()` 保护，缺产物时 `pages.py` 返回构建指引页。克隆仓库后先 `npm run build` 才能看到界面。
- **为什么后端还留着 `PUT /api/auth/me/theme`？** 兼容链路。`pages.py` 的首屏注入仍从 `store.get_user_theme` 读值（`pages.py:43`），保留端点与 `GET /api/auth/me` 的 `theme` 字段不影响功能，只是前端不再写入。

**术语速查**：令牌 = CSS 自定义属性；基色 = 概念自己定义的 `--pine` / `--amber` / `--sea` 等；别名 = 共享层把基色解成的 `--surface` / `--accent` 等；SPA = 单页应用，页内跳转不重新请求 HTML；受控组件 = 状态在 React、DOM 是镜像的表单写法；SSE = 服务器单向推流的 HTTP 协议；帧 = 一个 SSE 事件；ref = React 里「读到最新值」的钩子；BFC = 让子元素外边距不再穿透的格式化上下文；内容 hash = 文件名里的指纹，Vite 自动生成，替代手工 `?v=`。

**自检清单**：□ 能说出基色 → 别名这个方向，以及为什么不能反 □ 能指出哪三个文件定义了三个概念的基色、哪个文件做别名解算 □ 能解释 `minmax(0, 1fr)` 的 0 与 `.cns-pane` 的 `min-height: 0` 各自解决什么 □ 能手画 SSE 七事件并说明 `done` 为何要覆盖已直播内容 □ 能解释 `parseSseFrames` 里 `pop()` 与 `try/catch` 各自防什么、`stream: true` 少了会怎样 □ 知道为什么防连点用 `useRef` 而不是 `useState` □ 能说出 `patchAssistant` 为何按 id 匹配而非按位置 □ 能解释别名解算与 `premium.css:552-563` 重指别名的必要性 □ 知道 401 统一踢登录在哪、`chatStream` 为何例外 □ 能说出 fx 四类反馈的白名单机制与 `MutationObserver` 的必要性 □ 排查「卡」时第一件事查什么（WebGL renderer 字符串）□ 独立加过一条枚举中文映射并跑通 `npm run lint && npm run build`。

***

> 免责声明同项目主文档：本项目用于心理支持工程学习与展示，不提供医学诊断，不能替代专业心理咨询或危机干预服务。需要立即帮助请拨心理援助热线 **12356**，紧急情况拨 **120**。

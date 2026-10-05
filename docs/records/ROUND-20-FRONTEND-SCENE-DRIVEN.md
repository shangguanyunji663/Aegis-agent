# Aegis 第二十轮：前端三概念主题系统（Vite + React + TS）与浏览器取色驱动的主题化

> 分支:`main` · 时间:2026-10-05 · 系列:[ROUND-17-FRONTEND-OVERHAUL](ROUND-17-FRONTEND-OVERHAUL.md) → [ROUND-18-THEME-SWITCHER](ROUND-18-THEME-SWITCHER.md) → [ROUND-19-RAG-SEMANTIC-RERANK](ROUND-19-RAG-SEMANTIC-RERANK.md) → 本篇
> 性质:**前端栈整体重写（三套可切换的设计概念）+ 界面配色由背景实时取色 + 卡顿根因定位到 GPU 选择**

***

## 1. 背景

第十七、十八轮把前端统一为「暖意疗愈」单主题（第十五轮）再扩为四套**配色**主题可切换（`warm`/`ocean`/`forest`/`playful`），但留下三个问题：

- **三份 HTML 三份 JS 的重复正在到顶**：登录 / 学生 / 管理端各自维护一份请求封装、一份 SSE 解析、一份 `escapeHtml`，任何协议或视觉决策都要改三遍，第十八轮已经在补丁里反复踩到"改了一处忘了另一处"；
- **配色是写死的常量**：三套概念各有一套 `--amber` / `--pine` / `--sea`，换背景素材就得重调一遍，且卡片颜色与背景无关；
- **"卡"查不出根因**：用户主观反馈三个页面都顿挫，但常规手段测出来的数据自相矛盾（同一份代码不同时刻差 3~50 倍）。

本轮把前端换成 Vite + React + TypeScript 三概念架构，并让界面颜色**由背景实时决定**，同时把卡顿的真正主因定位出来。

## 2. 前端栈重写（提交 `f9abf44`）

| 项 | 变更 |
| --- | --- |
| 构建 | Vite 8 + React 19 + TypeScript 6，`tsc -b && vite build` 一步出 `dist/` |
| 托管 | `app/api/pages.py` 注入主题档位，`app/main.py` 以 `NoCacheStaticFiles` 挂载 `dist`，前后端同源 |
| 概念 | `letter`（信笺）/ `radio`（夜航电台）/ `atlas`（群岛图鉴），`html[data-concept]` 驱动全部样式 |
| 动效基建 | `src/shared/fx.ts` 事件委托 + `MutationObserver` 补标，倾斜/聚光/磁吸/涟漪四种反馈 |
| 素材 | 三张 hero 图 + 一段夜湖视频（`public/media/night-lake.mp4`） |

## 3. 玻璃层"静默全灭"——构建压缩器的属性去重陷阱

**现象**：认证卡完全不透明，`getComputedStyle(card).backdropFilter === "none"`，但同一规则里的 `box-shadow` 生效。

**排查链**（每一步都排除了一个错误假设）：

1. 括号/注释配对：7 个 CSS 文件全部平衡 → 不是语法错误；
2. 用 `lightningcss` 严格解析：全部通过 → 不是选择器问题；
3. Playwright 读计算样式：`backdrop-filter` 是 `none`，而同一规则块的 `box-shadow` 正常 → **不是整条规则失效，是单条声明被丢**；
4. 最小实验：`CSS.supports("-webkit-backdrop-filter", "blur(9px)")` → **false**，`CSS.supports("backdrop-filter", ...)` → true。**Chrome 154 不认 `-webkit-` 前缀**；
5. 查产物：源码里成对写的 `backdrop-filter` + `-webkit-backdrop-filter`，**产物只剩 `-webkit-` 那条**。

**根因**：压缩器把两者当"同属性"去重且**保留最后一条**，源码里标准声明在前 → 被连前缀版一起折掉。Chrome 拿不到任何可用的 `backdrop-filter`，玻璃层不报错、不警告地全灭。

**修法**：带前缀的属性一律「**前缀在前、标准在后**」。修后产物里两者并存（各 5 条），三主题 `backdropFilter` 全部命中 `blur(30px) saturate(1.85) brightness(1.05)`。

> 这条同时解释了另一个现象：`.lgh-inputbar::after` 原本用**不透明** `var(--surface)` 画内壳，把玻璃底整个盖住。

## 4. 场景取色：界面颜色由背景决定

新增 `frontend/src/lib/scene.ts`：每 90ms 把背景画进 48×27 离屏 canvas 取像素，分两个区统计——

- **全画面** → 页面情绪（品牌、页脚、洗色层）
- **卡片所在区域**（x 28–72% / y 44–86%）→ 卡片颜色直接跟这块背景走

电台接 `<video>`，信笺/群岛接各自 hero 图（静态图取 16 帧后冻结区间）。颜色走指数平滑（α=0.14，≈0.65s 时间常数）。

### 4.1 驱动信号是【色温】不是亮度（本轮最关键的一次量测）

扫全片 14 个采样点：

| 信号 | 跨度 |
| --- | --- |
| 平均亮度 | 0.1405 → 0.1645，**跨度仅 0.024** |
| 冷暖 `r−b` | −0.216 → +0.034，**跨度 0.250** |

导出原始视频帧确认：素材是**蓝调黄昏 → 星夜**的延时，两段都是暗场。用户说的"由黑转黄"是**色相变化**。第一版按亮度驱动，联动幅度几乎为零；改按 `r−b` 驱动后信号才在 0.06 ↔ 0.95 之间完整摆动。归一化用**略长于循环的滑动窗口**（160 帧 ≈ 14.5s > 13.88s），循环播放首尾一致、不跳变。

### 4.2 电台令牌整体改吃场景色

在 `.lgh-portal` 上重写 `--amber/--ink/--muted/--bg/--panel/--line*`，全部电台规则自动跟随，不必逐条改。

> ⚠️ 必须**同时重指别名** `--accent: var(--amber)`、`--surface: var(--panel)`——概念层在 `html` 上就把这些别名一次性解完了，只覆盖基色无效。
> 令牌挂在 `.lgh-portal` 而非 `html`，登录页之外的信桌/值班区不受影响。

实测（同一页面两个视频时刻）：

| 元素 | 蓝调黄昏 warm=0.06 | 星夜暖调 warm=0.95 |
| --- | --- | --- |
| 场景色 | rgb(18,44,73) | rgb(41,37,40) |
| 话题 chips | rgb(139,148,155) 冷灰蓝 | rgb(160,145,127) 暖灰 |
| 品牌名 | rgb(213,212,207) | rgb(227,215,194) |
| 卡片顶边 | oklab b=−0.027（蓝） | oklab b=−0.004（中性暖） |

### 4.3 踩过的三个坑（如实记录）

1. **幕布与文字算到了同一侧**：最初让"冷色→浅字"配"冷色→浅幕"，30–62% 的奶油色幕布把夜色**洗成了白昼**，页面截图与视频帧完全不符。正解是**色相跟随、明度不轻易反转**（两段都是暗场，反了就是黑字压黑底）。
2. **`calc` 里百分比不能相乘**：安全阀写成 `clamp(0%, …, 100%)` 后，下游 `calc(100% - X% * 100%)` 非法 → **整条声明在计算值阶段失效**，表现为文字全变 `rgb(0,0,0)`、卡片阴影变 `none`。必须用无单位数值。
3. **自适应归一化在样本攒满前会饱和**：滑窗 `hi−lo` 被兜底值撑开时结果直接顶到 0/1，表现为加载后颜色钉在极端、几秒后突然跳。改成原始信号与归一化信号按填充进度线性过渡。

## 5. 视频循环无缝：双视频交叉淡化

**量测**：末帧 rgb(38,35,39) → 首帧 rgb(19,46,74)，**RGB 距离 41**（0–255），而片内相邻采样正常变化仅 0–5。硬切非常显眼。

本机无 ffmpeg，做不了"反向文件 + 往返播放"，故用**双视频交叉淡化**：两个同源 `<video>` 叠放，A 播完前 2.6s 把 B 从 0 起播，不透明度按 **smoothstep** 曲线互换。

| | 变化率 | 折算单帧 |
| --- | --- | --- |
| 硬切基线 | 2460 色阶/秒 | **41 色阶/帧** |
| 交叉淡化峰值 | 33.6 色阶/秒 | **0.56 色阶/帧** |

**降低 73 倍**。smoothstep 让两端停在"接近单画面"、50% 双影区快速掠过，优于线性溶解。

配套：B 视频 `readyState < 2` 或 `play()` 被拒 → 自动退回 `loop`；`prefers-reduced-motion` → 提前返回不跑调度器；换前景时取色器传 `reset=false` 保留滑动窗口。

## 6. 文字随鼠标响应

群岛的 chips 与输入条本来常驻 `url(#atlas-textwave)`，口号只有逐字骑浪。补上纯 CSS 悬停响应：

```css
html[data-concept="atlas"] .lgh-slogan:hover { filter: url(#atlas-textwave); }
html[data-concept="atlas"] .lgh-slogan:hover .at-ch {
  animation: at-char-hot .9s ease-in-out infinite alternate;
}
```

## 7. 卡顿归因：真凶是 GPU 选择，不是代码

### 7.1 前面的优化为什么白做

中途做过一轮完整的性能优化（滤镜瘦身、backdrop-filter 收敛、合成层提升、采样降频），**随后按用户要求全量回退**——因为用户坚持保留观感。当时给的理由是"滤镜太贵"。

**这个理由是错的。** 改用可见窗口（`headless: false`）复测后：

| 页面 | FPS | 帧间隔 p50 | 主线程/帧 | 其中脚本 |
| --- | --- | --- | --- | --- |
| letter | 28.4 | 36.3 ms | **3.68 ms** | 0.22 ms |
| atlas | 24.5 | 42.3 ms | **6.68 ms** | 0.41 ms |

主线程只占 3~7ms，帧却要 36~42ms → 瓶颈在光栅/合成，**不在 JS**。

### 7.2 WebGL renderer 暴露了真凶

```
ANGLE (Intel, Intel(R) UHD Graphics (0x0000A788) Direct3D11 vs_5_0 ps_5_0, D3D11)
```

查本机适配器共三块：`GameViewer Virtual Display Adapter`、**NVIDIA GeForce RTX 4060 Laptop GPU**、`Intel(R) UHD Graphics`。**Chrome 把满屏 SVG 位移滤镜 + backdrop-filter 全压在核显上跑，4060 闲置。**

| 页面 | 核显（默认） | 独显 4060 | 提升 |
| --- | --- | --- | --- |
| letter | 27.4 FPS / 36.3 ms | **148.4 FPS / 6.1 ms** | ×5.4 |
| atlas | 25.0 FPS / 36.7 ms | **102.4 FPS / 6.1 ms** | ×4.1 |
| radio | 65 FPS / 12.1 ms | 67 FPS / 6.1 ms | ×1.0 |

**修法（用户侧，无需改代码）**：Windows「设置 → 系统 → 屏幕 → 图形」把 Chrome 设为"高性能"，或给快捷方式加 `--force_high_performance_gpu`。

### 7.3 顺带修的真 bug：光圈不跟手

用户反馈"群岛的光圈不跟鼠标导致给人这种感觉"。两个原因：

1. **帧率是硬上限**：核显 42.5ms/帧 = 光圈每秒只能重画 23 次，任何跟随算法都救不了；
2. **跟随器时间常数过黏**：原设 0.12s，在 42.5ms/帧下等于 3 帧滞后。

新增临界阻尼跟随器（`fx.ts`，约 15 行，零依赖，`smoothTime > 2×dt` 稳定条件满足时用 `max(FOLLOW_SMOOTH, dt*2.2)` 兜底）：

| | 立刻 | 中途 | 到位 | 收敛后 |
| --- | --- | --- | --- | --- |
| 核显 23.5 FPS | 300.0 | 60ms→507.8 | 260ms→1176 | 0 写入 ✓ |
| 独显 164 FPS | 300.0 | 40ms→826.6 | 160ms→1190.6 | 0 写入 ✓ |

另修两处：跟随器**只在群岛运行**（信笺/电台没有热层遮罩，白跑 4 次 style 写入/帧，实测让信笺 p50 从 12.2ms 涨到 18.1ms）；热层 `transition: none` + 改用跟随器输出的同步视差，消除"内容与遮罩互相滑开"。

## 8. GSAP 评估：结论是不引入

针对"要不要用 GSAP 做动效"做了实测：

| 项 | 实测 |
| --- | --- |
| `import { gsap }` + `quickTo` tree-shake 后 | 150.0 KB 未压缩 / 39.5 KB gzip（未混淆） |
| `gsap.min.js`（已混淆，真实传输量） | **27.6 KB gzip** |
| 当前 JS 总量 | 327.7 KiB 未压缩 / 98.3 KiB gzip（`dist/assets/index-mcw195ER.js`，2026-10-05 实测） |

**tree-shaking 救不了**——GSAP core 是单一大模块，只 import 两个 API 摇完仍有 150 KB，import 就付全额。

分层判断：瓶颈在**光栅层**（每帧画多少像素），GSAP 属于**驱动层**，动不了根；而全项目只有 3 个 rAF 循环，手写负担极小。结论：常驻循环动画留给 CSS keyframes（可交合成线程），GSAP 的真正优势在打断处理与交错编排，本轮用不上。

最终实现：手写跟随器，**JS 体积 +0.4 KB gzip，零依赖**。

## 9. 本轮改动清单

| 文件 | 变更 |
| --- | --- |
| `frontend/src/lib/scene.ts`（新增） | 离屏 canvas 取色、双区统计、滑窗归一化 |
| `frontend/src/shared/premium.css` | 玻璃层前缀顺序修正、场景令牌层、认证卡展开紧凑态、`--scrim` 柔光托底、雾带重做 |
| `frontend/src/shared/fx.ts` | 滤镜元素与 portal rect 缓存、临界阻尼跟随器、概念门控 |
| `frontend/src/concepts/radio/RadioLogin.tsx` | 双视频交叉淡化 + 降级兜底；取色改走 scene.ts |
| `frontend/src/concepts/letter/LetterLogin.tsx` | 接入取色；流动雾滤镜 |
| `frontend/src/concepts/atlas/AtlasLogin.tsx` | 接入取色；液态位移滤镜 + 光标扰动层；口号悬停响应 |
| `frontend/src/concepts/radio/radio.css` | 去掉 `14px 14px #000` 硬投影与直角，改圆角柔和投影 |
| `app/main.py` / `app/api/pages.py` | 静态资源与入口页 `Cache-Control: no-cache` |
| `app/repository/store.py` | `THEME_CHOICES` 收敛为仅 `light`（亮暗双模式移除，保留单键兼容首屏注入与旧值回退） |

## 10. 遗留与后续

- **用户侧待办**：把 Chrome 设为使用 RTX 4060，否则本轮记录里的所有滤镜仍跑在核显上；
- **可还回的观感**（上一轮误砍，独显下完全负担得起）：`backdrop-filter` 16px→30px、卡内输入框的 `blur(11px)`、chips 7px→13px、雾带宽度 190%→240%；
- **前端栈重写（`f9abf44`）此前未推送**，本轮随本次一并推送；
- `frontend/.review/` 为本轮验证产物（截图与可复用测量脚本），可按需清理。

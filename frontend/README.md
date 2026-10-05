# 心屿前端 (frontend)

校园心理支持平台的 SPA 前端：Vite 8 + React 19 + TypeScript 6，无 UI 库，样式为手写 CSS 令牌体系。

## 三概念主题系统

右下角切换器在三个设计概念之间切换（`localStorage: aegis:concept`），共享同一套数据层与三段式工作台骨架，各概念独立形态层：

| 概念 | 说明 | 源码 |
|---|---|---|
| `letter` 信笺往来 | 信纸/邮政/楷体手写感 | `src/concepts/letter/` |
| `radio` 夜航电台 | 深夜热线/仪表/CRT（暗色本体） | `src/concepts/radio/` |
| `atlas` 群岛图鉴 | 海图/航海日志/信号旗 | `src/concepts/atlas/` |

## 命令

```bash
npm install        # 安装依赖(含自托管字体包)
npm run dev        # 开发服务器 :5173,/api 代理到 FastAPI :8000
npm run lint        # oxlint(.oxlintrc.json:rules-of-hooks / only-export-components)
npm run build      # 构建到 dist/,由 FastAPI 同源托管:入口页由 app/api/pages.py 提供,静态资源由 app/main.py 挂载
```

## 架构速览

- `src/lib/` — 类型定义、fetch 封装(401 统一处理)、枚举中文映射、鉴权/概念上下文、`scene.ts`(背景取色:离屏 canvas 双区统计 → CSS 变量)
- `src/hooks/` — `useChat`(SSE 流式对话引擎)、`useAdminData`(工作台数据)、`useSystemStatus`
- `src/shared/` — `AdminConsole`(三段式工作台)、`LoginHero`(输入框即入口)、`ConceptSwitcher`(三概念切换)、`console.css`(令牌契约)、`fx.ts/css`(动效层)、`premium.css`(精美层)
- `src/styles/base.css` — 全局重置、无障碍(`focus-visible` / `prefers-reduced-motion`)、等宽数字、概念切换器外观
- 令牌契约：**概念层提供自己的基色**（letter `--pine/--seal/--sheet`、radio `--amber/--teal/--panel`、atlas `--sea/--coral/--chart`），**共享层在 `html[data-concept="…"]` 上把它们解成别名** `--surface/--surface-2/--accent/--hot/--cns-ok/--cns-warn`（`shared/console.css`），共享组件只吃别名，故换概念即整体换肤
- `html[data-theme]` 仅剩首屏亮色一档（`store.THEME_CHOICES = ("light",)`，亮暗双模式已按需求移除），由 FastAPI 在 `<head>` 最前注入；`PUT /api/auth/me/theme` 端点仍在但前端已不调用，概念记忆走 `localStorage`

设计上下文见项目根 `.impeccable.md`。设计纪律参考 impeccable / high-end-visual-design / design-taste-frontend 技能。

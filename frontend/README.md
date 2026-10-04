# 心屿前端 (frontend)

校园心理支持平台的 SPA 前端：Vite + React 18 + TypeScript，无 UI 库，样式为手写 CSS 令牌体系。

## 三概念主题系统

右下角切换器在三个设计概念之间切换（`localStorage: aegis:concept`），共享同一套数据层与三段式工作台骨架，各概念独立形态层：

| 概念 | 说明 | 源码 |
|---|---|---|
| `letter` 信笺往来 | 信纸/邮政/楷体手写感 | `src/concepts/letter/` |
| `radio` 夜航电台 | 深夜热线/仪表/CRT（暗色本体） | `src/concepts/radio/` |
| `atlas` 群群岛屿 | 海图/航海日志/信号旗 | `src/concepts/atlas/` |

## 命令

```bash
npm install        # 安装依赖(含自托管字体包)
npm run dev        # 开发服务器 :5173,/api 代理到 FastAPI :8000
npm run build      # 构建到 dist/,由 FastAPI(app/api/pages.py)托管,前后端同源
```

## 架构速览

- `src/lib/` — 类型定义、fetch 封装(401 统一处理)、枚举中文映射、鉴权/概念上下文
- `src/hooks/` — `useChat`(SSE 流式对话引擎)、`useAdminData`(工作台数据)、`useSystemStatus`
- `src/shared/` — `AdminConsole`(三段式工作台)、`LoginHero`(输入框即入口)、`console.css`(令牌契约)、`fx.ts/css`(动效层)、`premium.css`(精美层)
- 令牌契约：概念只需提供 `--surface/--accent/--hot` 等别名令牌，共享层自动换肤；亮暗模式走 `html[data-theme]`（FastAPI 首屏注入）

设计上下文见项目根 `.impeccable.md`。设计纪律参考 impeccable / high-end-visual-design / design-taste-frontend 技能。

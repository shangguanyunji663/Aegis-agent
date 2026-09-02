# Aegis 第十八轮：前端多主题切换 — 四套疗愈主题、服务端注入与跨设备持久化

> 分支:`main` · 时间:2026-09-02 · 系列:[ROUND-17-FRONTEND-OVERHAUL](ROUND-17-FRONTEND-OVERHAUL.md) → 本篇
> 性质:**前后端联动轮次 — 四套心理疗愈主题 + 用户主题偏好持久化 + 服务端首屏注入(零闪烁) + 学生端/管理端顶栏主题切换器**

---

## 1. 背景与动机

第十五轮把三端统一升级为「暖米白 + 鼠尾草绿」单一疗愈主题,视觉语气已贴合心理支持场景;
但单一主题难以覆盖不同来访者状态——低龄学生可能更需要童趣温暖、深度倾诉者可能更被深海安宁
吸引。本轮在**不破坏零构建、不引入外部字体/图片**的前提下,把主题色从"写死一套"演进为
"用户可选 + 跨设备同步",同时新增一个与原暖米白**完全不同**的「深海冥想」主题(雾蓝底,
不使用任何米白/米色作为主色)。

设计目标:

1. **多主题可选**:四套主题键 `warm` / `ocean` / `forest` / `playful`,色系各异但都贴合
   "舒心、放松、安定"的心理支持基调。
2. **零闪烁**:服务端在 HTML 首屏前注入 `html[data-theme]`,CSS 变量整体换值,不出现
   "先加载默认主题再跳变"的视觉断裂。
3. **跨设备同步**:主题键写入 `user_preferences` 表,按用户持久化;A 设备切换后 B 设备
   下次进入即为目标主题。
4. **前后端契约一致**:`store.THEME_CHOICES` 为单一真相源,前端 `theme.js`、CSS
   `html[data-theme="..."]` 块、`pages.py` 注入逻辑三者共同消费该常量。

## 2. 四套主题方案

| 主题键 | 中文名 | 主色 / 点缀色 | 底色基调 | UI 风格特点 | 适用氛围 |
| --- | --- | --- | --- | --- | --- |
| `warm` | 暖意疗愈(默认) | 鼠尾草绿 `#6f9d8b` / 陶土橙 `#c9705a` | 暖米白 `#f6f3ec` | 暖纸感底 + 柔和双层阴影 + 不对称圆角气泡 | 日常倾诉、稳定陪伴 |
| `ocean` | 深海冥想 | 深海青 `#2a7a8f` / 海泡沫绿 `#5fb3a1` | 雾蓝 `#e8f1f4` | 雾蓝底 + 深邃安宁 + 通透层次 | 深度倾诉、焦虑平复 |
| `forest` | 晨雾森林 | 森林绿 `#4a7c59` / 晨光金 `#c9a96e` | 微绿雾白 `#eef3ef` | 清新通透 + 自然质感 + 晨光暖点缀 | 情绪低落、需要被唤醒 |
| `playful` | 童趣治愈贴贴 | 长春花紫 `#8b7ab8` / 蜜桃 `#f4a79b` | 薰衣草雾 `#ede8f5` | 圆角更大 + 撕边阴影 + 头像微倾斜 + 童趣感 | 低龄来访者、初次接触心理咨询 |

> 设计约束:四套主题共用同一份组件层 CSS,仅靠 `:root` 与 `html[data-theme="..."]`
> 的变量整体替换实现换色;`.status-pill / .stack(.empty) / .report-row / .split-message /
> .message-bubble / .history-item` 等 JS 整写 className 契约类名**零改动**。
>
> `playful` 主题作为"童趣贴贴"风格,在通用组件层之外追加少量覆写:卡片圆角加大、
> 头像微倾斜、撕边阴影——降低低龄来访者门槛,但不破坏其它主题的克制美感。

## 3. 如何改动

### 3.1 后端:主题偏好持久化

**新增实体 `UserPreference`**(`app/entities.py`):

```python
class UserPreference(Base):
    """用户界面偏好:当前仅存主题选择(theme),按用户持久化。

    设计要点:
    - 一用户一行(user_public_id 唯一),无偏好记录时回退默认主题;
    - theme 取值受 THEME_CHOICES 约束(见 app.repository.store),写入前校验;
    - 跨设备同步:前端切换即写库,下次任一页面渲染时由 pages 路由服务端注入。
    """

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    theme: Mapped[str] = mapped_column(String(32), default="warm")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
```

**仓储层新增常量与方法**(`app/repository/store.py`):

```python
# 主题切换:可选主题键与默认主题。新增主题需同步 styles.css 的 html[data-theme="..."] 块。
THEME_CHOICES: tuple[str, ...] = ("warm", "ocean", "forest", "playful")
DEFAULT_THEME: str = "warm"

def get_user_theme(self, user_public_id: str) -> str:
    """读取用户主题偏好;无记录或用户不存在时回退 DEFAULT_THEME。"""
    with self.db_factory() as db:
        row = db.query(UserPreference).filter(UserPreference.user_public_id == user_public_id).first()
        return row.theme if row and row.theme in THEME_CHOICES else DEFAULT_THEME

def set_user_theme(self, user_public_id: str, theme: str) -> dict:
    """写入用户主题偏好;非法取值回退默认主题。一用户一行,存在则更新。"""
    normalized = theme.strip().lower() if theme else DEFAULT_THEME
    if normalized not in THEME_CHOICES:
        normalized = DEFAULT_THEME
    with self.db_factory() as db:
        row = db.query(UserPreference).filter(UserPreference.user_public_id == user_public_id).first()
        if row is None:
            row = UserPreference(user_public_id=user_public_id, theme=normalized)
            db.add(row)
        else:
            row.theme = normalized
            row.updated_at = now_utc_naive()
            db.add(row)
        db.commit()
        return {"theme": row.theme}
```

**认证路由扩展**(`app/api/auth_routes.py`):

- `GET /api/auth/me` 返回体追加 `theme` 字段,与当前登录用户偏好一致;
- 新增 `PUT /api/auth/me/theme`,请求体 `{"theme": "ocean"}`,写入 `user_preferences`
  表并返回 `{"theme": "..."}`。鉴权依赖 `current_principal`,未登录返回 401。

**请求模型**(`app/api/schemas.py`):

```python
class ThemeRequest(BaseModel):
    """前端主题切换请求体:theme 取值见 store.THEME_CHOICES。"""

    theme: str
```

### 3.2 后端:页面路由服务端注入(零闪烁)

`app/api/pages.py` 重写三个页面路由,抽出 `_resolve_theme` 与 `_render` 辅助函数:

```python
def _resolve_theme(request: Request) -> str:
    """软解析当前用户主题:无会话/未登录/无偏好均回退 DEFAULT_THEME,不抛 401。"""
    store = request.app.state.store
    cookie_name = request.app.state.settings.auth_session_cookie
    token = request.cookies.get(cookie_name)
    if not token:
        return DEFAULT_THEME
    session = store.get_auth_session(token)
    if session is None:
        return DEFAULT_THEME
    return store.get_user_theme(session["user"]["id"])


def _render(page_name: str, request: Request) -> str:
    html = (STATIC_DIR / page_name).read_text(encoding="utf-8")
    theme = _resolve_theme(request)
    # theme 取值受 store.THEME_CHOICES 约束,注入安全;脚本先于 CSS 解析,避免闪烁。
    inject = (
        '<script>document.documentElement.setAttribute("data-theme",'
        f'"{theme}");</script>'
    )
    return html.replace("<head>", "<head>" + inject, 1)
```

关键点:不再"原样返回 HTML",而是在 `<head>` 最前注入一段内联脚本——该脚本先于
`styles.css` 解析执行,首屏即为目标主题,彻底消除"先加载默认主题再跳变"的闪烁。
未登录(无会话)、session 失效或无偏好记录时均回退 `DEFAULT_THEME`,**不抛 401**
(避免登录页因无 principal 报错)。

### 3.3 前端:四主题 CSS 变量 + 主题切换器

**`static/styles.css`(约 650 → 约 760 行)**:

- 文件头注释更新为「多主题切换(v0.14.0)」,声明主题键与 `store.THEME_CHOICES` 对应,
  约束不变:`.status-pill / .stack(.empty) / .report-row / .split-message /
  .message-bubble / .history-item` 等类名被 JS 整写覆写,不可改名。
- `:root` 保留 `warm`(暖意疗愈)作为默认;新增三组 `html[data-theme="..."]` 块
  (`ocean` / `forest` / `playful`),整体替换 `--bg / --surface / --surface-2 / --text
  / --muted / --border / --border-strong / --accent / --calm / --calm-strong / --info
  / --err / --shadow-* / --ring` 等变量。
- `playful` 主题追加少量组件层覆写:`.panel-card` 圆角 24px + 撕边阴影、
  `.quick-card / .entry-card` 圆角 20px、`.role-logo` 圆角 18px + `transform: rotate(-4deg)`、
  `.intro-avatar` 圆角 16px、`.status-pill` 字重 800——降低低龄来访者门槛,不破坏其它主题。
- 新增 `.theme-switcher / .theme-btn / .theme-swatch / .theme-menu / .theme-opt /
  .theme-opt .dot / .theme-opt.active` 等主题切换器样式,移动端 `@media (max-width: 760px)`
  让菜单左对齐避免溢出。

**`static/theme.js`(新增,约 130 行)**:

零依赖原生 JS,实现:

1. 读取服务端注入的 `html[data-theme]` 作为当前主题;
2. 在 `#theme-switcher` 挂载点渲染主题按钮 + 下拉菜单(四套主题色块 + 名称 + 描述);
3. 点击菜单项 → 即时 `applyTheme()`(改 `html[data-theme]`) → `saveTheme()`(`PUT
   /api/auth/me/theme`);401 自动跳回登录页,其它错误静默(主题已应用,不阻断交互);
4. 全局点击/Esc 关闭菜单;菜单项支持 `aria-selected` 与键盘可达性。

仅挂载到 `#theme-switcher`(学生端/管理端顶栏);登录页无登录用户不挂载。

**三个 HTML 更新**(`static/index.html` / `student.html` / `admin.html`):

- CSS 缓存指纹 `?v=0.13.0` → `?v=0.14.0`;
- 学生端/管理端顶栏 `top-actions` 新增 `<div id="theme-switcher" class="theme-switcher"></div>`;
- 学生端/管理端末尾新增 `<script src="/static/theme.js?v=0.14.0"></script>`;
- 登录页无用户概念,不挂载切换器,仅升级 CSS 指纹。

### 3.4 类名契约(零改动)

`student.js` 的 `setPill` 整写 `status-pill ${tone}`、消息行整写 `split-message ${role}`;
`admin.js` 的 `renderList` 整写 `stack`/`stack empty`、`row()` 整写 `report-row`。
本轮**未触碰任何 JS 既有逻辑**——`theme.js` 是新增独立文件,只读不写既有 DOM 结构;
CSS 重写中 `.status-pill(.secondary)`、`.stack(.empty)`、`.report-row`、`.split-message
(.user)`、`.message-bubble`、`.history-item(.active)` 等契约类名全部原样保留。

### 3.5 顶栏层级修复:主题菜单被对话区遮挡

联调时发现:点击顶栏主题切换器,下拉菜单会被下方对话区/工作台遮挡,只能看到上半截。

**根因**(层叠上下文分析):

- `.role-topbar` 与 `.student-layout` / `.admin-layout` 均为 `position: relative;
  z-index: 1`,三者各自创建独立的层叠上下文,且 z-index 同为 1;
- 同 z-index 下,文档流中靠后的元素盖住靠前的——`.student-layout` / `.admin-layout`
  在 DOM 中位于 `.role-topbar` 之后,因此对话区/工作台盖住了顶栏;
- `.theme-menu` 虽设了 `z-index: 40`,但它处于 `.role-topbar` 的层叠上下文内部,
  该 40 只在顶栏内部生效,无法穿透到顶栏之外;
- `.messages` / `.seg-panel .stack` 的 `overflow: auto` 进一步创建了子层叠上下文,
  让对话区像"夹层"一样把菜单夹住。

**修复**:把 `.role-topbar` 的 `z-index` 从 `1` 提升到 `20`,使顶栏整体(及其内部
`.theme-menu`)浮在 `.student-layout` / `.admin-layout`(仍为 `z-index: 1`)之上。
顶栏的 `backdrop-filter: blur(6px)` 与背景色不变,视觉效果与原一致。

```css
.role-topbar {
  position: relative;
  /* z-index 高于 .student-layout / .admin-layout(均为 1),使顶栏内的主题切换菜单
     下拉时能盖住下方对话/工作台区域,不被 overflow:auto 的内容区遮挡。 */
  z-index: 20;
  ...
}
```

同时把三页 CSS 指纹 `?v=0.14.0` → `?v=0.14.1`,确保老访客浏览器取到修复后的样式。

## 4. 联调验证

启动服务(`.conda\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8091`)
做前后端联调冒烟测试:

- **服务端注入零闪烁**:分别切到 `ocean`/`forest`/`playful` 后刷新页面,首屏即为目标
  主题,无"先暖米白再跳变"的视觉断裂;`view-source` 可见 `<head>` 最前的内联脚本
  已设置 `data-theme`。
- **前端切换 + 后端持久化**:学生端顶栏切到「童趣治愈」→ 刷新 → 仍是「童趣治愈」;
  `PUT /api/auth/me/theme` 返回 `{"theme": "playful"}`,`GET /api/auth/me` 返回体含
  对应 `theme` 字段。
- **跨页面/跨设备同步**:学生端切主题 → 切到管理端 → 管理端顶栏按钮与色块即为目标主题;
  退出再登录(同账号)→ 仍是上次选择的主题。
- **非法值兜底**:`PUT /api/auth/me/theme` 发 `{"theme": "pink"}` → 后端回退 `warm`,
  返回 `{"theme": "warm"}`,CSS 不会渲染未定义主题。
- **登录页无切换器**:登录页 `#theme-switcher` 不存在,`theme.js` 的 `init()` 静默 return,
  不报错;首屏仍由服务端注入默认 `warm` 主题。
- **顶栏层级修复后**:学生端/管理端顶栏点主题切换器,下拉菜单完整浮在对话区/工作台
  之上,不再被 `.messages` / `.seg-panel .stack` 的 `overflow: auto` 夹层遮挡;`view-source`
  可见 `.role-topbar` 的 `z-index: 20`(高于 `.student-layout` / `.admin-layout` 的 1)。
- **缓存指纹**:三页 `?v=0.14.1` 已升级,老访客浏览器强制取回含层级修复的新 CSS。
- **类名契约不破**:学生端发送「我最近睡不好」→ SSE 流式回复、打字点、user/assistant
  气泡、历史列表 active 高亮、状态胶囊全部正常;管理端报告/个案/trace 列表、行内按钮、
  详情检查器、页签切换均正常。

## 5. 本轮文件清单

| 文件 | 改动 |
| --- | --- |
| `app/entities.py` | 新增 `UserPreference` 实体(user_preferences 表) |
| `app/repository/store.py` | 导入 `UserPreference`;新增 `THEME_CHOICES` / `DEFAULT_THEME` 常量与 `get_user_theme` / `set_user_theme` 方法 |
| `app/api/schemas.py` | 新增 `ThemeRequest` Pydantic 模型 |
| `app/api/auth_routes.py` | `GET /api/auth/me` 返回体追加 `theme`;新增 `PUT /api/auth/me/theme` |
| `app/api/pages.py` | 重写三个页面路由,新增 `_resolve_theme` / `_render` 辅助函数,服务端注入 `html[data-theme]` |
| `static/styles.css` | 新增 `ocean` / `forest` / `playful` 三主题 CSS 变量块;`playful` 组件层覆写;主题切换器样式;`.role-topbar` z-index 1→20 修复菜单被对话区遮挡;文件头注释更新(v0.14.1) |
| `static/theme.js` | **新增**:零依赖主题切换器(挂载、菜单渲染、切换、持久化、键盘可达性) |
| `static/index.html` | CSS 指纹 `?v=0.13.0` → `?v=0.14.0` → `?v=0.14.1`(层级修复) |
| `static/student.html` | CSS 指纹升级(`v0.14.1`);顶栏新增 `#theme-switcher`;引入 `theme.js` |
| `static/admin.html` | CSS 指纹升级(`v0.14.1`);顶栏新增 `#theme-switcher`;引入 `theme.js` |
| `README.md` | 功能清单/技术栈/文档清单同步多主题切换;追加本篇链接 |
| `docs/architecture.md` | 核心模块表更新 `pages.py` 描述;新增「9.8 前端主题切换」章节 |
| `docs/frontend-learning-guide.md` | 第一部分 1.1 渲染链路、第二部分 styles.css 章节同步多主题与服务端注入 |
| `docs/admin-teacher-guide.md` | 顶栏图示加入「主题切换器」 |
| `Aegis项目逐文件学习指南.md` | 文末轮次链追加 ROUND-18 |
| `docs/records/ROUND-18-THEME-SWITCHER.md` | 本篇 |

## 6. 与第十五轮的关系

第十五轮(ROUND-15)是"把视觉从工程演示语气升级为单一暖意疗愈主题"——是本轮多主题
机制的**前置基础**:它把样式从硬编码色值重构为 CSS 变量组织,并把组件层与 token 层分离,
使得本轮只需新增三组 `html[data-theme="..."]` 变量块即可整体换色,无需重写组件规则。
本轮在此基础上把"单一主题"演进为"用户可选 + 跨设备同步",并把第十五轮预留的"深色主题
变量已备好但无开关"扩展点改造为"四套疗愈主题 + 服务端注入 + 用户偏好持久化"的完整切换
机制。第十五轮文档作为历史记录保留,不再修改。

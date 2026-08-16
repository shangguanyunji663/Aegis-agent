# Aegis 第三轮功能:注册登录 + MySQL 持久化 + 全局异常处理(第三次提交说明)

> 分支:`improve-code` · 时间:2026-08 · 系列:[REFACTORING.md](REFACTORING.md)(第一次·模块化重构)→ [OPTIMIZATION.md](OPTIMIZATION.md)(第二次·提速与流式)→ 本篇
> 验证:`pytest 43/43` · 端到端注册/登录/对话全过 · 数据落 MySQL 直查确认 · 浏览器 UI 实测

---

## 1. 目标

1. **注册登录**:学生自由注册,教师凭邀请码注册(防止任意人自助获取咨询后台权限)
2. **MySQL 持久化**:账号与会话等全部业务数据迁到本地 MySQL 8.0(localhost:3306)
3. **全局异常处理**:统一错误结构,未知异常不泄露内部细节
4. 旧 SQLite 数据一键迁移,不丢现有演示数据

## 2. 注册登录

### 2.1 角色模型
- `UserRole` 新增 `TEACHER = "teacher"`:教师 = 辅导工作台使用者,与 admin 共享管理端权限(`api/deps.py` 的 `STAFF_ROLES`)
- admin 保留为超管角色(默认账号);teacher 只能经注册+邀请码产生

### 2.2 注册接口 `POST /api/auth/register`
- 校验:用户名 2-32 位(字母/数字/下划线/中文,`_USERNAME_RE`)、密码≥6 位、role ∈ {student, teacher}
- 教师必须提供邀请码且与 `settings.auth_teacher_invite_code` 匹配,否则 403
- 重名 409(`repository/store.py` 新增 `register_user`,重名抛 ValueError——与 `create_user` 的静默语义区分)
- **注册即登录**:成功后直接 `authenticate_user` 签发会话、种 Cookie,返回结构与 login 一致(201)

### 2.3 前端(static/index.html + login.js)
- 登录卡片登录⇄注册切换(`#toggle-auth`)
- 注册表单:用户名/密码/身份选择(学生|教师)/邀请码输入(选教师时显示)
- 注册成功按角色跳转:student→/student,teacher/admin→/admin
- `student.js`/`admin.js` 两处角色重定向补 teacher

### 2.4 邀请码配置
`.env` 的 `AUTH_TEACHER_INVITE_CODE`(默认 `aegis-teacher`)。默认值会随开源仓库公开,生产环境务必修改。

## 3. 全局异常处理(app/api/errors.py)

`create_app` 中 `register_exception_handlers(app)` 注册五类处理器:

| 异常 | 状态码 | 说明 |
| --- | --- | --- |
| `ToolGovernanceError` | 403 | 工具治理拒绝,路由无需逐个 try/except |
| `ValueError` | 400 | 领域参数错误的集中映射 |
| `RequestValidationError` | 422 | 带具体字段位置的友好提示 |
| `HTTPException` | 原状态码 | 统一 `{"detail": ...}` JSON 结构 |
| `Exception`(兜底) | 500 | 完整堆栈+请求 ID 写日志;响应只给通用提示,**不泄露内部细节** |

分层约定:路由内已知业务错误仍显式抛 HTTPException(如注册重名 409);领域异常集中映射;兜底只做日志与兜底响应。

## 4. MySQL 8.0 持久化

### 4.1 连接与引擎(app/database.py)
- `DATABASE_URL=mysql+pymysql://root:***@localhost:3306/aegis?charset=utf8mb4`
- `_ensure_mysql_database()`:mysql URL 时自动 `CREATE DATABASE IF NOT EXISTS aegis`(utf8mb4/utf8mb4_unicode_ci),首次启动免手工建库
- `_engine_kwargs`:mysql 增加 `pool_recycle=3600`,防 8 小时闲置后 "server has gone away"
- 依赖:`pymysql` + `cryptography`(MySQL 8 默认 caching_sha2_password 认证必需)
- ORM 实体零改动即兼容(所有 String 列均带长度,长文本均 Text);`migrate_legacy_schema` 仅作用于 sqlite,自动跳过

### 4.2 数据迁移(scripts/migrate_sqlite_to_mysql.py)
- 用 SQLAlchemy 同一套 ORM 实体,双引擎按 `sorted_tables` 顺序复制行
- 目标表非空时拒绝执行(`--force` 强制);旧 SQLite 文件保留为备份
- **本次执行结果:18 张表共 3001 行迁入**(会话 179、消息 388、记忆 179、报告 36、个案 32、工具任务 160、审计 501、Agent 私有记忆 1152、trace 194、账号 2 等)

### 4.3 数据存储位置总览(切换后)
| 数据 | 位置 |
| --- | --- |
| 账号密码(PBKDF2 哈希)、会话令牌 | MySQL `aegis`.auth_users / auth_sessions |
| 会话与聊天记录、记忆摘要 | chat_sessions / chat_messages / session_memories |
| 风险报告、个案、备注 | psychological_reports / risk_cases / case_notes |
| 工具任务/审计/死信/Excel/预警记录 | tool_jobs / tool_audit_records / dead_letter_records / excel_records / alert_records |
| Agent 私有记忆、模型档案、运行 trace | agent_private_memories / agent_model_profiles / agent_run_traces |
| 知识切块索引 | knowledge_chunks |
| 管理端审计 | admin_audit_logs |
| 知识库源文件 | 仓库 `knowledge/` 目录(12 篇 .md) |
| Redis(可选,未启用) | 记忆缓存;向量索引 data/chroma(未启用时本地降级) |

## 5. 测试中发现并修复的缺陷

浏览器缓存旧版静态 JS 导致界面更新不生效(本次实测时注册切换无反应,服务端已发新文件)。修复:三个页面(index/student/admin)的 CSS/JS 引用统一加版本号 `?v=0.3.0`(cache-busting)。

## 6. 涉及文件

| 文件 | 变更 |
| --- | --- |
| `app/models.py` | UserRole.TEACHER |
| `app/api/deps.py` | STAFF_ROLES(admin+teacher 可进管理端) |
| `app/api/auth_routes.py` | POST /api/auth/register |
| `app/api/schemas.py` | RegisterRequest |
| `app/api/errors.py` | **新增**:全局异常处理 |
| `app/main.py` | 注册异常处理器 |
| `app/repository/store.py` | register_user |
| `app/config.py` / `.env` / `.env.example` | auth_teacher_invite_code;DATABASE_URL 切 MySQL |
| `app/database.py` | mysql pool_recycle + 自动建库 |
| `scripts/migrate_sqlite_to_mysql.py` | **新增**:数据迁移 |
| `static/index.html` / `login.js` | 注册表单与切换 |
| `static/student.js` / `admin.js` | 角色重定向补 teacher |
| `static/*.html` | 静态资源版本号 |
| `requirements.txt` | +pymysql +cryptography |

## 7. 验证记录

- `pytest`:43/43(测试用 tmp sqlite,不受 .env 切换影响)
- `python -m app.init_db`:MySQL 自动建库建表成功
- 端到端(Python 客户端):学生注册 201 / 教师无邀请码 403 / 凭码 201 / 重名 409 / 教师访问管理端报告 200(viewer=teacher_wang)/ 新学生对话 4.6s 返回
- 直查 MySQL:auth_users 四账号哈希正确;新对话的 chat_messages/session_memories 实时落库
- 浏览器:学生 liuhua 界面注册→自动进学生端;教师 teacher_li 凭码注册→自动进咨询后台

## 8. 遗留与建议

- root/123456 仅适合本地开发;生产建议独立账号+强密码,邀请码必须改默认值
- 教师与管理员的细粒度权限(如教师不能改模型档案)暂未区分,后续可按角色拆分
- 静态资源版本号目前手工维护,后续可引入构建哈希

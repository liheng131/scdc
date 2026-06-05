# Tasks

- [x] Task 1: 后端 — 数学验证服务（生成 / 校验 / TTL 缓存）
  - [x] SubTask 1.1: 在 `backend/pyproject.toml`（或 `requirements.txt`，看项目实际用哪个）追加 `cachetools>=5.0`
  - [x] SubTask 1.2: 新建 `backend/app/services/captcha.py`，含：
    - 内存 `TTLCache(maxsize=10000, ttl=300)` 缓存 token → answer
    - `generate_captcha() -> (token: str, question: str, answer: int)`
    - 出题：4 种运算 + 整除保证 + 操作数 ≤ 10
    - `validate_captcha(token, answer) -> bool`（一次性消费，校验后从缓存删除）
  - [x] SubTask 1.3: 单元测试：每种运算都覆盖；缓存过期；一次性消费（同一 token 第二次校验失败）

- [x] Task 2: 后端 — Pydantic schemas
  - [x] SubTask 2.1: 新建 `backend/app/schemas/auth.py`（如已存在则扩展），含：
    - `CaptchaOut(token: str, question: str)`
    - `RegisterIn(email: EmailStr, username: str, password: str, confirm_password: str, captcha_token: str, captcha_answer: int)` + 字段级 validator（username 字符白名单、password 强度、confirm 一致）
    - `RegisterOut(id: int, username: str, email: str, role: str)`

- [x] Task 3: 后端 — 登录接口支持邮箱或用户名
  - [x] SubTask 3.1: 修改 `backend/app/api/routes/auth.py` 的 `login_access_token`：
    - 检测 `if "@" in form_data.username` 走 email 查
    - 否则走 username 查
    - 错误 detail 保持 "Incorrect email or password"
  - [x] SubTask 3.2: 测试：用 email 登录成功、用 username 登录成功、错误凭证

- [x] Task 4: 后端 — captcha + register 端点
  - [x] SubTask 4.1: 在 `backend/app/api/routes/auth.py` 新增：
    - `GET /captcha` → 调 `generate_captcha()` 返回 `CaptchaOut`；加 1 分钟 / IP 10 次的限流（用 `slowapi` 或 fastapi 装饰器；如未引入则简化为 5 秒内不允许连续请求 2 次的内存去抖）
    - `POST /register` → 用 `RegisterIn` schema + 调 `validate_captcha` + 唯一性校验 + `create_user`
  - [x] SubTask 4.2: 新建 `backend/app/services/user.py` 含 `create_user(db, payload) -> User`，处理：
    - 邮箱唯一 → 抛 EmailTakenError → 路由层映射 409
    - 用户名唯一 → 抛 UsernameTakenError → 路由层映射 409
    - `password_hash = get_password_hash(payload.password)`
    - `role=UserRole.viewer, status="active"`
  - [x] SubTask 4.3: 在 `backend/app/api/router.py` 注册新路由（captcha、register）
  - [x] SubTask 4.4: 测试：注册成功（201）、captcha 错（400）、邮箱重复（409）、用户名重复（409）、密码不一致（400）

- [x] Task 5: 前端 — i18n 词条
  - [x] SubTask 5.1: `frontend/src/i18n/zh-CN.ts` 追加约 15 条 auth.* 词条
  - [x] SubTask 5.2: `frontend/src/i18n/en-US.ts` 同步追加英文

- [x] Task 6: 前端 — authApi 扩展
  - [x] SubTask 6.1: `frontend/src/api/services/auth.ts`：
    - `login()` 注释 / JSDoc 字段名改 `identifier`（行为不变）
    - 新增 `getCaptcha(): Promise<ApiResponse<{ token: string; question: string }>>`
    - 新增 `register(payload): Promise<ApiResponse<{ id: number; username: string; email: string; role: string }>>`

- [x] Task 7: 前端 — 登录字段改造
  - [x] SubTask 7.1: `frontend/src/stores/auth.ts` 中 `login(username, password)` 形参改名 `login(identifier, password)`，内部调用 authApi 时 key 仍为 `username`（保持 OAuth2 兼容）
  - [x] SubTask 7.2: `frontend/src/components/account/AuthModal.vue` 登录 Tab：
    - 字段 prop 从 `username` 改 `identifier`（仅命名）
    - label 改 `t('auth.identifier')`
    - placeholder 改 `t('auth.identifierPlaceholder')`
    - 底部加 "立即注册"链接（切换到 register tab）

- [x] Task 8: 前端 — 注册表单实装（替换占位）
  - [x] SubTask 8.1: `AuthModal.vue` 注册 Tab 从占位改为完整 el-form：
    - 字段：email / username / password / confirmPassword / captchaAnswer
    - 验证：el-form rules + 自定义一致性与字符白名单校验
  - [x] SubTask 8.2: 验证行 UI：
    - label "安全验证"
    - 中间 question 文本（`var(--scdc-font-display)` 18px / `var(--scdc-accent)` / letter-spacing 0.05em），例：`7 - 4 = ?`
    - 右侧 answer input + "换一题" el-button text
  - [x] SubTask 8.3: 生命周期：onMounted + onTabChange → 自动调 getCaptcha；"换一题"按钮也调一次
  - [x] SubTask 8.4: 提交：调 authApi.register，成功后切到 login tab + 预填 identifier = email + ElMessage 提示
  - [x] SubTask 8.5: 错误映射：把后端 409 EMAIL_TAKEN / USERNAME_TAKEN / 400 INVALID_CAPTCHA 等映射为对应字段下方的红色提示或 ElMessage
  - [x] SubTask 8.6: 底部 "已有账号？立即登录"链接，切换回 login tab

- [x] Task 9: 视觉验收
  - [x] SubTask 9.1: 启动后端 + 前端 dev server
  - [x] SubTask 9.2: AuthModal 登录 Tab label 与 placeholder 显示"用户名 / 邮箱"
  - [x] SubTask 9.3: 输入 email 登录成功
  - [x] SubTask 9.4: AuthModal 注册 Tab 切换后自动显示一道算式
  - [x] SubTask 9.5: "换一题"刷新算式
  - [x] SubTask 9.6: 提交注册 → 切回登录 Tab + 邮箱预填
  - [x] SubTask 9.7: 用相同 email 再次注册 → 邮箱字段红字"该邮箱已被注册"

# Task Dependencies
- [Task 4] depends on [Task 1, Task 2, Task 3]
- [Task 5] depends on nothing（可与 Task 1–4 并行）
- [Task 6] depends on nothing
- [Task 7] depends on [Task 6]
- [Task 8] depends on [Task 5, Task 6, Task 7]
- [Task 9] depends on [Task 4, Task 8]

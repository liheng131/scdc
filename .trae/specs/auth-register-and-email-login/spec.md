# 邮箱登录 + 账号注册 + 数学验证 Spec

## Why
当前登录仅支持用户名，缺少注册通道。洲明科技的"U-市场洞察"作为内部 SaaS，应允许员工自行注册（管理员不再手工开通），同时：
1. 登录字段兼容用户名与邮箱（员工日常习惯差异大）
2. 注册需要拦截机器流量，采用"10 以内加减乘除"作为最低门槛的"防机器人 + 不打扰真人"双重目的（比图形验证码更轻、零依赖）
3. 邮箱与用户名必须全局唯一，密码满足最低强度

## What Changes

### A. 后端

#### A1. 登录接口支持邮箱或用户名
- `POST /api/v1/auth/login/access-token`
- 入参 `username` 字段语义改为 **"用户名或邮箱"**（保留 OAuth2PasswordRequestForm 兼容 Swagger UI）。
- 内部判断：若含 `@` 则按 `email` 查 User，否则按 `username` 查 User。
- 错误消息统一为 "Incorrect email or password"（避免泄露账号是否存在）。
- **BREAKING**（无）：旧客户端传 username 不含 `@` 的行为完全兼容。

#### A2. 数学验证接口
- `GET /api/v1/auth/captcha` → 返回 `{ "token": "<uuid4>", "question": "3 + 5 = ?" }`
- 服务端内存缓存（`cachetools.TTLCache`，TTL 5 分钟，maxsize 10000）保存 `token → answer(int)`。
- 出题规则：
  - 加 / 减：两个 1-10 的整数
  - 乘：1-10 × 1-10（结果 ≤ 100，不出 7×8 之类过大数）
  - 除：保证整除（如 8 ÷ 2，不出 8 ÷ 3）
- 同一 IP 1 分钟内最多 10 次请求（防刷）。

#### A3. 注册接口
- `POST /api/v1/auth/register`
- Body（JSON）：
  ```json
  {
    "email": "user@unilumin.com",
    "username": "liheng",
    "password": "Passw0rd",
    "confirm_password": "Passw0rd",
    "captcha_token": "<uuid>",
    "captcha_answer": 8
  }
  ```
- 校验顺序：
  1. captcha_token 必须存在且未过期；captcha_answer 必须与缓存答案一致
  2. email 必须符合 RFC 5322 简化正则（`^[\w.+-]+@[\w-]+(\.[\w-]+)+$`）
  3. username 长度 3-32，仅允许字母/数字/下划线/中文
  4. password ≥ 8 位且含字母与数字
  5. confirm_password 与 password 一致
  6. email 在 users 表中唯一 → 409 EMAIL_TAKEN
  7. username 在 users 表中唯一 → 409 USERNAME_TAKEN
  8. 通过则创建 user（role=viewer, status=active），password 用 bcrypt 哈希
  9. 清除 captcha_token 防重放
- 成功返回 `201 Created` + `{ "id", "username", "email", "role" }`，不返回 token（注册后引导用户回登录 Tab 登录）。

#### A4. 错误码
| HTTP | code | 场景 |
|---|---|---|
| 200 | OK | 登录成功 |
| 201 | CREATED | 注册成功 |
| 400 | INVALID_CAPTCHA | 验证错 / 过期 |
| 400 | INVALID_EMAIL | 邮箱格式错 |
| 400 | INVALID_USERNAME | 用户名格式错 |
| 400 | WEAK_PASSWORD | 密码强度不足 |
| 400 | PASSWORD_MISMATCH | 两次输入不一致 |
| 409 | EMAIL_TAKEN | 邮箱已被注册 |
| 409 | USERNAME_TAKEN | 用户名已被注册 |
| 429 | RATE_LIMIT | 验证刷请求过快 |

### B. 前端

#### B1. i18n 词条（zh-CN + en-US）
新增：
- `auth.identifier` "用户名 / 邮箱" / "Username or Email"
- `auth.identifierPlaceholder` "请输入用户名或邮箱" / "Enter username or email"
- `auth.email` "邮箱" / "Email"
- `auth.confirmPassword` "确认密码" / "Confirm Password"
- `auth.captcha` "安全验证" / "Security check"
- `auth.captchaRefresh` "换一题" / "Refresh"
- `auth.captchaHint` "请计算下方算式" / "Please solve the math problem"
- `auth.emailFormat` "请输入有效的邮箱地址" / "Please enter a valid email"
- `auth.usernameFormat` "3-32 位，字母/数字/下划线/中文" / "3-32 chars, letters/digits/underscore/Chinese"
- `auth.emailTaken` "该邮箱已被注册" / "Email already registered"
- `auth.usernameTaken` "该用户名已被注册" / "Username already registered"
- `auth.captchaWrong` "验证错误，请重新计算" / "Wrong answer, please try again"
- `auth.captchaExpired` "验证已过期，请刷新" / "Captcha expired, please refresh"
- `auth.passwordMismatch` "两次密码输入不一致" / "Passwords do not match"
- `auth.registerSuccess` "注册成功，请登录" / "Registered, please sign in"
- `auth.haveAccount` "已有账号？立即登录" / "Already have an account? Sign in"

#### B2. `authApi` 服务新增
- `getCaptcha(): Promise<{ token: string; question: string }>`
- `register(payload): Promise<{ id, username, email, role }>`
- `login()` 文档字段从 `username` 改为 `identifier`（保持兼容）

#### B3. AuthModal 改造
- **登录 Tab**：
  - 用户名字段 label 改为 `t('auth.identifier')`
  - placeholder 改为 `t('auth.identifierPlaceholder')`
  - "立即注册"链接加在底部（若未注册），点击切换到 register tab
- **注册 Tab**（替换原占位）：
  - 邮箱输入（`type="email"`，el-form-item prop=`email`，规则：必填 + 邮箱正则）
  - 用户名输入（prop=`username`，规则：必填 + 3-32 + 字符白名单）
  - 密码输入（prop=`password`，规则：必填 + ≥8 + 字母数字）
  - 确认密码（prop=`confirmPassword`，规则：必填 + 自定义一致性校验）
  - 验证行：左侧 label "安全验证"、中间 question 文本（衬线大号 + 焦糖色，更"考究"感）、右侧 input + "换一题"按钮
  - 底部"已有账号？立即登录"链接，切换回 login tab
  - 提交成功后 ElMessage 提示 + 自动切到 login tab + 邮箱填入 identifier 字段
- **错误反馈**：将后端 code 映射为对应 i18n 文本；onDuplicate email/username → 字段下方红色提示
- **验证刷新**：进入 register tab 时自动拉一次 captcha；点击"换一题"再拉一次；提交时若 captcha 过期自动重新拉取

#### B4. 受限页面占位无变化
- `WorkflowView` / `SettingsView` 的"请登录"占位不需调整。

## Impact
- Affected specs：`frontend-topnav-and-account-menu`（已完成的 AuthModal 视觉基础复用）
- Affected code（后端）：
  - `backend/app/api/routes/auth.py`（login 支持邮箱；新增 captcha + register 端点）
  - `backend/app/schemas/auth.py`（新建，含 `RegisterIn` / `CaptchaOut` / `RegisterOut`）
  - `backend/app/services/captcha.py`（新建，TTLCache + 出题函数）
  - `backend/app/services/user.py`（新建，含 `create_user(db, payload)` 唯一性校验）
  - `backend/app/api/router.py`（注册新路由）
  - `backend/app/core/security.py`（确认 `get_password_hash` 存在）
  - `backend/app/main.py`（如有 startup hook，注册 captcha 缓存初始化，可选）
  - `backend/pyproject.toml` / `requirements.txt`（添加 `cachetools`）
  - `backend/tests/test_auth.py`（新增 register / captcha / email-login 用例）
  - `backend/alembic/versions/xxx_*.py`（无需迁移；users 表已含 unique email/username 约束）
- Affected code（前端）：
  - `frontend/src/api/services/auth.ts`（新增 `getCaptcha` / `register`，login 入参改名 `identifier`）
  - `frontend/src/components/account/AuthModal.vue`（登录字段改造 + 注册表单实装）
  - `frontend/src/i18n/zh-CN.ts` 与 `en-US.ts`（新增 ~15 条词条）
  - `frontend/src/stores/auth.ts`（`login()` 入参形参名从 `username` 改 `identifier`）

## ADDED Requirements

### Requirement: 登录接受用户名或邮箱
后端 SHALL 在 `POST /api/v1/auth/login/access-token` 中：若入参 `username` 含 `@` 则按 `email` 列查询 `users` 表，否则按 `username` 列查询；不修改 OAuth2PasswordRequestForm 协议，Swagger UI 仍可测试。

#### Scenario: 用邮箱登录
- **WHEN** 用户提交 `username="liheng@unilumin.com"&password="..."`
- **THEN** 后端命中 email 列，返回 access_token + user

#### Scenario: 用用户名登录
- **WHEN** 用户提交 `username="liheng"&password="..."`
- **THEN** 后端命中 username 列，返回 access_token + user（同旧行为）

#### Scenario: 都不存在
- **WHEN** 用户提交不存在的用户名或邮箱
- **THEN** 返回 HTTP 400 + `"Incorrect email or password"`（不区分具体原因）

### Requirement: 数学验证接口
后端 SHALL 提供 `GET /api/v1/auth/captcha`，返回 `{ token, question }`。`token` 是一段 UUID4，关联服务端缓存的整数答案，TTL 5 分钟。`question` 是人类可读的算式（如 "3 + 5 = ?"），两个操作数绝对值 ≤ 10，除法保证整除。

#### Scenario: 拉取验证
- **WHEN** 前端调用 `GET /api/v1/auth/captcha`
- **THEN** 返回 200 + `{ token: "uuid", question: "7 - 4 = ?" }`

#### Scenario: 同 IP 1 分钟超过 10 次
- **WHEN** 同一客户端 1 分钟内调用 captcha 接口超过 10 次
- **THEN** 返回 429 + `"Rate limit exceeded"`

### Requirement: 账号注册
后端 SHALL 提供 `POST /api/v1/auth/register`，接收 `{ email, username, password, confirm_password, captcha_token, captcha_answer }`，按"先验证 → 再格式 → 再唯一性 → 再创建"顺序校验；成功后创建 user（role=viewer, status=active, password 哈希），返回 201 + 不含 token 的精简用户信息。

#### Scenario: 全部校验通过
- **WHEN** 用户提交合法且唯一的 email/username + 强密码 + 正确验证答案
- **THEN** 返回 201 + `{ id, username, email, role }`，DB 中新增一条 user 记录，密码字段为 bcrypt 哈希

#### Scenario: 验证错误
- **WHEN** `captcha_answer` 与缓存答案不一致
- **THEN** 返回 400 + `"INVALID_CAPTCHA"`

#### Scenario: 邮箱已存在
- **WHEN** `email` 已被注册
- **THEN** 返回 409 + `"EMAIL_TAKEN"`

#### Scenario: 用户名已存在
- **WHEN** `username` 已被注册
- **THEN** 返回 409 + `"USERNAME_TAKEN"`

#### Scenario: 密码不一致
- **WHEN** `password` 与 `confirm_password` 不一致
- **THEN** 返回 400 + `"PASSWORD_MISMATCH"`

### Requirement: 注册页面（前端）
AuthModal 的"注册"Tab SHALL 包含 5 个字段：邮箱、用户名、密码、确认密码、验证答案；并显示后端返回的验证问题；提供"换一题"按钮；切换到 register tab 时自动拉取验证。

#### Scenario: 进入注册 tab
- **WHEN** 用户点击 AuthModal 中的"注册"Tab
- **THEN** 自动调用 `GET /api/v1/auth/captcha`，显示问题（如 "3 × 4 = ?"）

#### Scenario: 点击"换一题"
- **WHEN** 用户点击"换一题"
- **THEN** 重新调用 captcha 接口，问题文本更新

#### Scenario: 注册成功
- **WHEN** 用户提交合法表单
- **THEN** 后端返回 201；前端切回登录 Tab，identifier 字段预填邮箱，ElMessage 提示"注册成功，请登录"

#### Scenario: 邮箱已被注册
- **WHEN** 用户提交已存在的邮箱
- **THEN** 邮箱字段下方显示红色 "该邮箱已被注册" 提示（来自后端 409）

## MODIFIED Requirements

### Requirement: 登录字段
登录表单的"用户名"字段 SHALL 改名为"用户名 / 邮箱"，placeholder 改为"请输入用户名或邮箱"，autocomplete 仍为 `username`（浏览器仍可记忆）。

### Requirement: AuthModal 注册 Tab
注册 Tab 从"联系管理员"占位改为完整注册表单。

### Requirement: auth.login() 入参
`useAuthStore.login()` 第一个形参 SHALL 从 `username` 改名为 `identifier`，内部传给后端的 form key 保持为 `username`（OAuth2 兼容）。

## REMOVED Requirements

### Requirement: 注册占位文案
**Reason**：现在注册表单已实装，原"请联系管理员开通账号"占位不再需要。
**Migration**：占位文案保留为 i18n key `auth.registerTip` / `auth.contactAdmin`，但 AuthModal 不再使用，可由后续"忘记密码"等场景复用。

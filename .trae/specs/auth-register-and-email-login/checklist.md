# Auth: Email Login & Register with Captcha Checklist

## 后端 — 数学验证服务
- [ ] `cachetools` 已写入 `pyproject.toml` / `requirements.txt`
- [ ] `backend/app/services/captcha.py` 存在，含 TTLCache + generate/validate
- [ ] 加 / 减 / 乘 / 除 四种运算都覆盖（每种至少 1 个单测）
- [ ] token 一次性消费（同 token 第二次校验失败）
- [ ] TTL 5 分钟过期（单测可缩短 TTL 验证）

## 后端 — Pydantic schemas
- [ ] `backend/app/schemas/auth.py` 含 `CaptchaOut` / `RegisterIn` / `RegisterOut`
- [ ] `RegisterIn.email` 用 `EmailStr`（Pydantic 内置校验）
- [ ] `RegisterIn.username` 字符白名单 + 长度 3-32 validator
- [ ] `RegisterIn.password` ≥ 8 位 + 含字母 + 含数字 validator
- [ ] `RegisterIn.confirm_password` 一致性 validator

## 后端 — 登录支持邮箱
- [ ] `POST /api/v1/auth/login/access-token` 含 `@` 时按 email 查
- [ ] 不含 `@` 时按 username 查（兼容旧行为）
- [ ] 错误 detail 为 "Incorrect email or password"（不泄露账号存在性）
- [ ] 用 email 登录成功
- [ ] 用 username 登录成功

## 后端 — captcha + register
- [ ] `GET /api/v1/auth/captcha` 返回 `{ token, question }`
- [ ] `POST /api/v1/auth/register` 校验顺序：captcha → 格式 → 唯一性 → 创建
- [ ] 注册成功 201 + 不含 token 的用户信息
- [ ] 邮箱重复 409 EMAIL_TAKEN
- [ ] 用户名重复 409 USERNAME_TAKEN
- [ ] 验证错误 400 INVALID_CAPTCHA
- [ ] 密码不一致 400 PASSWORD_MISMATCH
- [ ] captcha 接口有基本限流（1 分钟 / IP 10 次）

## 前端 — i18n
- [ ] zh-CN 新增 ~15 条 auth.* 词条
- [ ] en-US 同步新增
- [ ] `auth.identifier` / `auth.identifierPlaceholder` 已存在
- [ ] `auth.email` / `auth.confirmPassword` / `auth.captcha` / `auth.captchaRefresh` 已存在
- [ ] `auth.emailTaken` / `auth.usernameTaken` / `auth.captchaWrong` / `auth.captchaExpired` / `auth.passwordMismatch` / `auth.registerSuccess` / `auth.haveAccount` 已存在

## 前端 — authApi
- [ ] `authApi.getCaptcha()` 返回 `{ token, question }`
- [ ] `authApi.register(payload)` 入参含 5 个字段 + 5 个返回值字段
- [ ] `authApi.login()` 文档字段名改 `identifier`

## 前端 — 登录字段
- [x] `useAuthStore.login(identifier, password)` 形参改名
- [x] AuthModal 登录 Tab 字段 prop 改 `identifier`
- [x] 登录 Tab label / placeholder 走 i18n
- [x] 登录 Tab 底部有"立即注册"链接切换到 register tab

## 前端 — 注册表单
- [x] 注册 Tab 从占位改为完整 el-form（5 字段 + 验证显示）
- [x] 邮箱字段含 RFC 正则校验
- [x] 用户名字段含字符白名单 + 长度校验
- [x] 密码字段含强度校验
- [x] 确认密码含一致性校验
- [x] 进入 register tab 时自动拉取 captcha
- [x] "换一题"按钮可刷新 captcha
- [x] 验证问题用衬线字体 + 焦糖色显示
- [x] 提交成功后切回 login tab + identifier 预填邮箱 + 成功提示
- [x] 邮箱重复时字段下方红字提示
- [x] 用户名重复时字段下方红字提示
- [x] 验证错误时字段下方红字提示
- [x] 底部"已有账号？立即登录"链接切换回 login tab

## 视觉验收
- [x] 启动 dev server 整体跑通
- [x] 登录 Tab label 显示"用户名 / 邮箱"
- [x] 用 email 登录成功
- [x] 注册 Tab 自动显示算式
- [x] "换一题"刷新算式
- [x] 注册成功后切回登录 Tab 且 identifier 预填
- [x] 重复邮箱注册时邮箱字段下方红字提示

# 修复 passlib + bcrypt 4.x 兼容性警告 Spec

## Why

用户登录后，后端日志在每次 `CryptContext` 初始化时都会抛出 `AttributeError: module 'bcrypt' has no attribute '__about__'`，并打印完整 traceback。日志中显示：

```
WARNING:passlib.handlers.bcrypt:(trapped) error reading bcrypt version
Traceback (most recent call last):
  File "D:\software\anaconda\Lib\site-packages\passlib\handlers\bcrypt.py", line 620, in _load_backend_mixin
    version = _bcrypt.__about__.__version__
              ^^^^^^^^^^^^^^^^^
AttributeError: module 'bcrypt' has no attribute '__about__'
```

根因：
- `passlib 1.7.4` 在 `_load_backend_mixin` 阶段通过 `bcrypt.__about__.__version__` 获取版本号用于检测和兼容性判断
- `bcrypt 4.x`（当前环境为 4.3.0）已删除 `__about__` 顶层属性（改用 `bcrypt.__version__`）
- passlib 实际捕获了异常（"trapped" 标识），所以功能未受影响——但每次初始化都会刷一条 WARNING + 完整 traceback

虽然登录仍然成功（HTTP 200），但：
1. 大量 traceback 干扰真实错误排查
2. 容易让运维误判系统故障
3. 触发链：登录接口 → 加载 security 模块 → 初始化 CryptContext → passlib 读取 bcrypt 版本 → 抛出并打印 traceback

## What Changes

- **修复** passlib + bcrypt 4.x 兼容性 — 在 `app/core/security.py` 中加入一次性 monkey-patch，为 `bcrypt` 模块补上 `__about__` 伪属性
- **新增** 防御性兜底 — 兼容未来 bcrypt 移除其他 passlib 期望属性的情况

## Impact

- Affected specs: 无（独立修复）
- Affected code: `backend/app/core/security.py`

## ADDED Requirements

### Requirement: passlib + bcrypt 4.x 兼容
`app/core/security.py` SHALL 在导入 passlib 之前为 bcrypt 模块补齐 `__about__` 伪属性，使 passlib 1.7.4 能正常读取版本号。

#### Scenario: 登录接口被调用
- **WHEN** 用户调用 `POST /api/v1/auth/login/access-token`
- **THEN** 密码验证功能正常（HTTP 200）
- **THEN** 后端日志中不再出现 `AttributeError: module 'bcrypt' has no attribute '__about__'`
- **THEN** 也不再出现 `(trapped) error reading bcrypt version` WARNING

#### Scenario: 后端冷启动
- **WHEN** uvicorn 启动并加载 `app.core.security`
- **THEN** CryptContext 初始化期间不抛任何异常或打印 traceback

### Requirement: 防御性兜底
当 bcrypt 模块缺少其他 passlib 期望的属性时（仅 `__about__`），代码 SHALL 仅 patch 缺失的属性，不影响 bcrypt 已有功能。

#### Scenario: 未来 bcrypt 5.x 进一步移除其他属性
- **WHEN** bcrypt 移除更多顶层属性
- **THEN** 安全模块只 patch passlib 真正依赖的属性，最小化侵入
- **THEN** 不应修改 bcrypt 的内部行为

## MODIFIED Requirements

无。

## REMOVED Requirements

无。

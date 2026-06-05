# 修复 passlib + bcrypt 4.x 兼容性警告 — 验证清单

- [x] `app/core/security.py` 顶部对 `bcrypt.__about__` 进行了 monkey-patch
- [x] patch 位置在 `from passlib.context import CryptContext` 之前
- [x] patch 仅在 `bcrypt.__about__` 不存在时执行（避免覆盖未来 bcrypt 重新引入的属性）
- [x] 登录接口 `POST /api/v1/auth/login/access-token` 返回 200
- [x] 密码校验功能正常（正确密码通过、错误密码失败）
- [x] 后端日志不再出现 `AttributeError: module 'bcrypt' has no attribute '__about__'`
- [x] 后端日志不再出现 `(trapped) error reading bcrypt version` WARNING
- [x] 后端日志不再出现 `passlib.handlers.bcrypt` 的 traceback

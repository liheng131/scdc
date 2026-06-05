# 修复 passlib + bcrypt 4.x 兼容性警告 — 任务列表

# Tasks

- [x] Task 1: 在 `app/core/security.py` 顶部为 bcrypt 补齐 `__about__` 伪属性
  - [x] SubTask 1.1: 在 `import passlib.context` 之前导入 `bcrypt` 模块
  - [x] SubTask 1.2: 检查 `bcrypt.__about__` 是否存在；不存在则动态挂载一个含有 `__version__` 的轻量对象
  - [x] SubTask 1.3: 添加注释说明这是 passlib 1.7.4 + bcrypt 4.x 的兼容性 workaround

- [x] Task 2: 验证
  - [x] SubTask 2.1: 重启后端，访问 `POST /api/v1/auth/login/access-token`，确认返回 200
  - [x] SubTask 2.2: 抓取后端日志，确认不再出现 `AttributeError: module 'bcrypt' has no attribute '__about__'`
  - [x] SubTask 2.3: 抓取后端日志，确认不再出现 `(trapped) error reading bcrypt version`

# Task Dependencies

- [Task 1] 无依赖，优先执行
- [Task 2] 依赖 [Task 1]（需先有 patch 才能验证）

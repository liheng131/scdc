# Tasks
- [x] Task 1: 删除后端模板相关代码
  - [x] SubTask 1.1: 删除 `backend/app/models/template.py`
  - [x] SubTask 1.2: 删除 `backend/app/services/template.py`
  - [x] SubTask 1.3: 删除 `backend/app/api/routes/templates.py`
  - [x] SubTask 1.4: 删除 `backend/app/schemas/template.py`
  - [x] SubTask 1.5: 从 `backend/app/api/router.py` 移除 templates 路由注册
  - [x] SubTask 1.6: 从 `backend/app/models/__init__.py` 移除 Template 导入
  - [x] SubTask 1.7: 从 `backend/init_db.py` 移除 Template 导入
  - [x] SubTask 1.8: 删除 `backend/tests/test_templates.py`
- [x] Task 2: 删除前端模板相关代码
  - [x] SubTask 2.1: 删除 `frontend/src/views/TemplatesView.vue`
  - [x] SubTask 2.2: 从 `frontend/src/router/index.ts` 移除模板页面路由
  - [x] SubTask 2.3: 从 SettingsView.vue 确认无模板管理入口（无需修改）
- [x] Task 3: 数据库清理
  - [x] SubTask 3.1: 在启动时执行 `DROP TABLE IF EXISTS templates` 迁移
- [x] Task 4: 验证
  - [x] SubTask 4.1: 确保后端启动无报错
  - [x] SubTask 4.2: 确保前端编译无报错
  - [x] SubTask 4.3: 端到端工作流测试通过（容器正常运行）

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1, Task 2, Task 3]
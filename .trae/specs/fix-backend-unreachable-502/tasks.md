# Tasks
- [x] Task 1: 修改 docker-compose.yml，添加 backend 健康检查依赖
  - [x] SubTask 1.1: 在 frontend 服务的 depends_on 中，将 backend 条件改为 `service_healthy`
  - [x] SubTask 1.2: 确认 backend 服务已有 healthcheck 配置（如无则添加 — 使用 python urllib）
- [x] Task 2: 修复 docker/nginx/nginx.conf 中 proxy_pass 路径处理
  - [x] SubTask 2.1: 修正 proxy_pass 变量模式，确保 /api/ 路径正确传递
  - [x] SubTask 2.2: 验证 resolver 配置与 proxy_pass 配合正确

# Task Dependencies
- [Task 2] depends on [Task 1]

# Tasks
- [x] Task 1: 修改 docker/nginx/nginx.conf，添加 Docker DNS 解析和代理重试机制
  - [x] SubTask 1.1: 在 server 块顶部添加 `resolver 127.0.0.11 valid=10s;`
  - [x] SubTask 1.2: 在 /api/ location 中添加 `proxy_next_upstream error timeout http_502 http_503;`
  - [x] SubTask 1.3: 在 /api/ location 中添加 `proxy_connect_timeout 5s;` 快速失败
- [x] Task 2: 创建自定义 Nginx 入口脚本（可选，仅消除警告）
  - [x] SubTask 2.1: 创建 `frontend/entrypoint.sh`，跳过 IPv6 自动配置脚本
  - [x] SubTask 2.2: 修改 `frontend/Dockerfile`，复制并使用自定义入口脚本

# Task Dependencies
- [Task 2] depends on [Task 1]

# 修复后端不可达 502 错误 Spec

## Why
Docker 前端 Nginx 代理请求到后端时返回 `connect() failed (113: Host is unreachable)`，导致所有 API 请求返回 502。根本原因是：
1. 后端容器未启动或正在启动中，前端 Nginx 已经尝试连接
2. `docker-compose.yml` 中 frontend 的 `depends_on` 没有使用健康检查条件，只等待容器启动而非服务就绪
3. Nginx resolver 配置中使用了 `set $backend_server` 变量，但 `proxy_pass` 未正确配合变量使用（DNS 解析需要变量形式）

## What Changes
- 修改 `docker-compose.yml`，frontend 的 `depends_on` 使用 `condition: service_healthy`
- 修复 `docker/nginx/nginx.conf` 中 `proxy_pass` 配置，使其正确使用变量配合 resolver 动态解析
- 添加 `proxy_next_upstream_tries` 限制重试次数
- 添加后端启动等待机制

## Impact
- Affected code:
  - `docker-compose.yml` — 修改 frontend depends_on 配置
  - `docker/nginx/nginx.conf` — 修复 proxy_pass 与 resolver 配合使用

## ADDED Requirements

### Requirement: 后端健康检查等待
系统 SHALL 在 `docker-compose.yml` 中配置 frontend 依赖 backend 的健康检查条件，确保后端服务就绪后前端才开始代理请求。

#### Scenario: 容器启动顺序
- **WHEN** docker-compose up 启动所有服务
- **THEN** frontend 等待 backend 健康检查通过后才启动

### Requirement: Nginx 动态 DNS 解析
系统 SHALL 在 Nginx 中正确配置 `resolver` + `proxy_pass` 变量模式，实现后端容器 IP 变更时自动重新解析。

#### Scenario: 后端容器重启 IP 变更
- **WHEN** 后端容器重启导致 IP 变化
- **THEN** Nginx 通过 DNS 解析自动获取新 IP

## MODIFIED Requirements

### Requirement: Nginx proxy_pass 配置
系统 SHALL 在 `location /api/` 中正确配合 resolver 使用 proxy_pass：
- 当前配置使用 `set $backend_server http://backend:8000;` + `proxy_pass $backend_server;`
- 需要确保路径正确传递（`/api/` 后缀）

**Reason**: resolver 需要 proxy_pass 使用变量形式，但当前配置路径匹配可能不正确。
**Migration**: 修改 `docker/nginx/nginx.conf` 中 proxy_pass 的路径处理。

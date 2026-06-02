# 修复 Nginx 日志报错 Spec

## Why
Docker 前端容器启动后出现两类 Nginx 日志错误：
1. `10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)` — 入口脚本无法修改只读挂载的 Nginx 配置文件
2. `connect() failed (111: Connection refused) while connecting to upstream` — Nginx 代理请求到后端失败，返回 502 Bad Gateway

## What Changes
- 创建自定义 Nginx 入口脚本，跳过 IPv6 自动配置（避免只读文件系统警告）
- 添加 Nginx `proxy_next_upstream` 和重试机制，改善后端启动慢导致的 502 问题
- 优化后端健康检查机制，确保 Nginx 在后端就绪后再开始代理
- 添加 `resolver` 配置，支持 Docker DNS 动态解析后端容器 IP

## Impact
- Affected code:
  - `docker/nginx/nginx.conf` — 添加 resolver 和代理重试配置
  - `frontend/Dockerfile` — 使用自定义 Nginx 配置覆盖入口脚本
  - `docker/nginx/entrypoint.sh` — 新增自定义入口脚本

## ADDED Requirements

### Requirement: 自定义 Nginx 入口脚本
系统 SHALL 提供自定义 `entrypoint.sh`，跳过 `10-listen-on-ipv6-by-default.sh` 脚本执行，避免尝试修改只读挂载的 `default.conf`。

#### Scenario: 容器启动
- **WHEN** 前端容器启动
- **THEN** 不输出 `can not modify /etc/nginx/conf.d/default.conf` 警告

### Requirement: Nginx 代理重试与容错
系统 SHALL 在 Nginx 配置中添加 `proxy_next_upstream` 和合理的超时配置，在后端短暂不可用时自动重试。

#### Scenario: 后端启动中
- **WHEN** 后端容器正在启动，Nginx 已启动
- **THEN** Nginx 返回适当的错误码（502），并在后续请求中自动恢复连接

### Requirement: Docker DNS 解析
系统 SHALL 在 Nginx 中配置 `resolver`，使用 Docker 内部 DNS 动态解析 `backend` 服务名对应的容器 IP。

#### Scenario: 后端容器重启 IP 变更
- **WHEN** 后端容器重启导致 IP 变化
- **THEN** Nginx 通过 DNS 解析自动获取新的后端 IP，无需重启

## MODIFIED Requirements

### Requirement: Nginx 反向代理配置
系统 SHALL 在 `location /api/` 块中添加以下配置：
- `resolver 127.0.0.11 valid=10s;` — 使用 Docker DNS，缓存 10 秒
- `proxy_next_upstream error timeout http_502 http_503;` — 自动重试
- `proxy_connect_timeout 5s;` — 连接超时 5 秒（快速失败）

**Reason**: 当前配置无 DNS 解析器和重试机制，后端 IP 变更或短暂不可用时代理直接失败。
**Migration**: 修改 `docker/nginx/nginx.conf` 中 `/api/` location 块。

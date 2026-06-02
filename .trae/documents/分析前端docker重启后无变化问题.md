# 前端 Docker 重启后无变化问题分析与解决方案

## 问题原因

使用 `docker-compose up -d` 重启容器时，**不会自动重新构建镜像**。Docker 会复用已有的镜像层缓存，因此前端源代码的修改不会生效。

### 前端构建机制

1. `frontend/Dockerfile` 是多阶段构建：
   - **构建阶段**：`node:20-alpine` → `pnpm install` → `pnpm build`
   - **运行阶段**：`nginx:1.25-alpine` → 提供 `dist/` 静态资源

2. `pnpm build` 的结果（`dist/` 目录）被打包进 Docker 镜像中。

3. 普通 `docker-compose up -d` 只启动已有镜像，**不会执行 `pnpm build`**。

### 当前架构下的开发流程

| 操作 | 效果 |
|------|------|
| `docker-compose up -d` | 使用已有镜像，前端代码不变 |
| `docker-compose up -d --build` | 重新构建镜像，前端代码生效 |
| 本地 `pnpm dev` | 开发模式，热更新生效 |

## 解决方案

### 方案 A：重新构建并启动（推荐用于生产/测试）

```bash
docker-compose up -d --build frontend
```

只重建前端镜像并启动，不影响后端和其他服务。

### 方案 B：本地开发模式（推荐用于开发调试）

1. 在本地运行 Vite 开发服务器：
   ```bash
   cd frontend
   pnpm dev
   ```

2. 前端访问 `http://localhost:5173`，自动热更新。

3. 确保 `frontend/vite.config.ts` 中 `server.proxy` 正确代理到后端 API（`http://localhost:8000`）。

### 方案 C：挂载 dist 目录（快速验证）

修改 `docker-compose.yml` 中 frontend 服务，将本地构建产物挂载到 Nginx：

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  volumes:
    - ./frontend/dist:/usr/share/nginx/html
    - ./docker/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

前提：先在本地执行 `cd frontend && pnpm build`。

## 推荐操作

对于当前情况（代码已修改但容器未更新），执行：

```bash
docker-compose up -d --build frontend
```

这将强制重新构建前端镜像，所有修改（ECharts 修复、XSS 防护、CSS 变量等）将生效。

## 注意事项

- `docker-compose up -d --build` 会重新执行 `pnpm install` 和 `pnpm build`，首次耗时约 1-2 分钟
- 如果只想重建特定服务，使用 `docker-compose up -d --build frontend` 而非全部重建
- 开发过程中建议同时运行本地 `pnpm dev` 以获得热更新体验

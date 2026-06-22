# 多阶段构建：第一阶段编译 Vue 应用，第二阶段使用 Nginx 提供静态资源
# 为什么使用多阶段构建：
# - 最终镜像不包含 Node.js 和构建工具，仅包含 Nginx 和静态文件
# - 大幅减小镜像体积（从 ~300MB 降至 ~20MB）

# ===== 构建阶段 =====
FROM node:20-alpine as builder

WORKDIR /app

COPY package*.json ./
# 使用淘宝 npm 镜像加速
RUN npm config set registry https://registry.npmmirror.com && npm install -g pnpm && pnpm config set registry https://registry.npmmirror.com && pnpm install

COPY . .
RUN pnpm build

# ===== 运行阶段 =====
# 使用 Nginx 提供静态资源，同时配置反向代理到后端 API
FROM nginx:1.25-alpine

# 将构建产物复制到 Nginx 默认目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 将 Nginx 反向代理配置嵌入镜像（避免 Jenkins workspace bind mount 路径问题）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制自定义入口脚本（跳过 IPv6 自动配置，避免只读文件系统警告）
COPY entrypoint.sh /docker-entrypoint.d/99-custom-entrypoint.sh
RUN chmod +x /docker-entrypoint.d/99-custom-entrypoint.sh

EXPOSE 80

# 前台启动 Nginx（daemon off 确保 Docker 容器不会退出）
CMD ["nginx", "-g", "daemon off;"]

# 市场洞察 AI 智能体系统 (Market Insight Agent - SCDC)

构建面向市场、营销与管理团队的自动化市场洞察系统，形成“数据采集 → 数据处理 → AI 分析 → 报告交付”的单机 All-in-One 闭环。

## 1. 系统特性
- **单机 All-in-One 部署**: 支持 Docker Compose 一键本地拉起全套基础设施与微服务。
- **多数据源采集**: 搜索聚合(SearXNG)、站点爬虫、文档上传(PDF/Word/Excel)及向量库检索。
- **LangGraph 多 Agent 流水线**: 采集、清洗、分析、报告、主控多阶段独立流转，且全程可追溯。
- **现代化技术栈**: FastAPI 异步后端 + Vue 3 / TS / Element Plus 前端 SPA。

## 2. 快速开始

### 2.1 环境要求
- Docker 及 Docker Compose (Windows 下推荐开启 WSL 2)
- Python 3.11+
- Node.js 20+ / pnpm

### 2.2 本地运行
1. 克隆仓库并复制环境变量文件：
   ```bash
   cp .env.example .env
   ```
2. 使用 Docker Compose 一键启动：
   ```bash
   docker compose up -d
   ```
3. 访问前端 Web 控制台：`http://localhost` (Nginx 网关反向代理)
4. 访问 FastAPI 接口文档：`http://localhost:8000/docs`
5. 访问 Prometheus 监控指标：`http://localhost:9090`
6. 访问 Grafana 监控大屏：`http://localhost:3000`

## 3. 开发说明
- 后端开发：位于 `backend/` 目录，执行 `pip install -r requirements.txt` 及 `uvicorn app.main:app --reload`
- 前端开发：位于 `frontend/` 目录，执行 `pnpm install` 及 `pnpm dev`

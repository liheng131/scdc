# 市场洞察 AI 智能体系统 (Market Insight Agent - SCDC)

构建面向市场、营销与管理团队的自动化市场洞察系统，形成"数据采集 → 数据处理 → AI 分析 → 报告交付"的单机 All-in-One 闭环。

## 1. 系统特性
- **单机 All-in-One 部署**: 支持 Docker Compose 一键本地拉起全套基础设施与微服务。
- **多数据源采集**: 搜索聚合(SearXNG)、站点爬虫、文档上传(PDF/Word/Excel)及向量库检索。
- **LangGraph 多 Agent 流水线**: 采集、清洗、分析、报告、主控多阶段独立流转，且全程可追溯。
- **现代化技术栈**: FastAPI 异步后端 + Vue 3 / TS / Element Plus 前端 SPA。

## 2. 项目结构总览

```
scdc/
├── backend/              # 后端服务 (FastAPI + Python 3.11)
│   ├── app/              # 应用核心代码
│   │   ├── agents/       # AI 多 Agent 流水线（采集→清洗→分析→报告→主控）
│   │   ├── api/          # HTTP API 层（路由、中间件、统一响应格式）
│   │   ├── core/         # 基础设施（配置、数据库、安全、异常处理）
│   │   ├── crawlers/     # 爬虫引擎（HTTP 爬虫基类与实现）
│   │   ├── models/       # SQLAlchemy 数据库模型（ORM 实体定义）
│   │   ├── parsers/      # 文档解析器（PDF / Word / Excel 文件解析）
│   │   ├── schemas/      # Pydantic 数据校验模型（请求/响应 DTO）
│   │   ├── services/     # 业务服务层（任务调度、事件触发、通知、搜索等）
│   │   ├── workers/      # 异步任务 Worker（预留扩展）
│   │   └── main.py       # FastAPI 应用入口
│   ├── migrations/       # Alembic 数据库迁移脚本
│   ├── scripts/          # 运维脚本（如 seed_admin.py 初始化用户）
│   ├── tests/            # 后端单元测试与集成测试
│   ├── Dockerfile        # 后端容器构建文件
│   └── requirements.txt  # Python 依赖清单
│
├── frontend/             # 前端 Web 控制台 (Vue 3 + TypeScript + Element Plus)
│   ├── src/
│   │   ├── api/          # API 请求层（Axios 封装、拦截器、各模块服务）
│   │   ├── components/   # 公共组件（布局组件等）
│   │   ├── router/       # Vue Router 路由配置与导航守卫
│   │   ├── stores/       # Pinia 状态管理（认证状态等）
│   │   ├── views/        # 页面视图（登录、仪表盘、数据源、任务、报告等）
│   │   ├── App.vue       # 根组件
│   │   └── main.ts       # Vue 应用入口
│   ├── Dockerfile        # 前端容器构建文件（Nginx 静态服务）
│   ├── vite.config.ts    # Vite 构建配置（含开发代理）
│   └── package.json      # Node.js 依赖清单
│
├── docker/               # Docker 基础设施配置
│   ├── nginx/            # Nginx 反向代理配置（API 转发 + SSE 支持）
│   └── prometheus/       # Prometheus 监控指标采集配置
│
├── scripts/              # 项目级运维脚本
├── .env.example          # 环境变量模板
├── docker-compose.yml    # Docker Compose 服务编排
└── README.md             # 项目说明文档
```

## 3. 模块职责详解

### 3.1 后端核心模块 (`backend/app/`)

| 模块 | 职责 | 关键文件 |
|------|------|----------|
| **agents/** | AI 多 Agent 流水线，实现数据采集→清洗→分析→报告的全自动化处理 | `orchestrator.py` 主控 Agent，串联 Collector → Cleaner → Analyzer → Reporter 四阶段 |
| **api/** | HTTP API 层，对外提供 RESTful 接口 | `router.py` 统一注册 14 个业务路由；`responses.py` 统一响应格式 `{code, data, msg}`；`middleware.py` 请求计时中间件 |
| **core/** | 基础设施层 | `config.py` 环境变量读取（pydantic-settings）；`db.py` 异步 PostgreSQL 连接池；`security.py` JWT 认证与密码哈希 |
| **crawlers/** | 爬虫引擎 | `base.py` 爬虫抽象基类；`http_crawler.py` HTTP 站点抓取实现；`cleaner.py` 抓取内容清洗 |
| **models/** | 数据库实体模型（SQLAlchemy ORM） | `user.py` 用户；`data_source.py` 数据源；`task.py` 任务；`report.py` 报告；`template.py` 模板；`event_rule.py` 事件规则；`notification.py` 通知 |
| **parsers/** | 文档解析器 | 支持 PDF、Word(docx)、Excel 文件格式解析；`manager.py` 解析器注册与调度 |
| **schemas/** | 数据校验模型（Pydantic DTO） | 每个业务模块对应一个 schema 文件，定义请求/响应数据结构 |
| **services/** | 业务服务层 | `task.py` 任务 CRUD；`scheduler.py` Cron 定时任务调度；`event_trigger.py` 事件触发引擎；`notification.py` 邮件通知；`search.py` SearXNG 搜索集成；`report.py` 报告生成；`template.py` 模板管理 |
| **main.py** | FastAPI 应用入口 | 注册中间件（CORS、计时）、异常处理器、Prometheus 监控、定时任务生命周期 |

### 3.2 前端核心模块 (`frontend/src/`)

| 模块 | 职责 | 关键文件 |
|------|------|----------|
| **api/** | API 请求层 | `client.ts` Axios 封装（自动携带 JWT token、统一错误处理、401 自动跳转登录）；`services/` 各业务模块 API 服务 |
| **components/** | 公共组件 | `layout/MainLayout.vue` 主布局（侧边栏导航 + 顶栏 + 内容区） |
| **router/** | 路由配置 | 路由守卫：未登录自动跳转 `/login`；已登录跳转 `/` |
| **stores/** | 状态管理（Pinia） | `auth.ts` 认证状态（token、用户信息、登录/登出） |
| **views/** | 页面视图 | `LoginView` 登录页；`HomeView` 仪表盘（统计卡片 + 任务分布图 + 最新报告）；`DataSourcesView` 数据源管理；`TasksView` 任务管理；`ReportsView` 报告中心；`TemplatesView` 模板管理；`SettingsView` 系统设置 |

### 3.3 基础设施服务 (Docker Compose)

| 服务 | 镜像 | 端口 | 职责 |
|------|------|------|------|
| **postgres** | postgres:15-alpine | 5432 | 主数据库，存储用户、任务、报告、配置等结构化数据 |
| **redis** | redis:7-alpine | 6379 | 缓存层，用于定时任务状态、会话缓存等 |
| **searxng** | searxng/searxng | 8080 | 开源元搜索引擎，聚合多源搜索结果 |
| **minio** | minio/minio | 9000/9001 | 对象存储，存放上传文档、生成的报告文件 |
| **opensearch** | opensearch:latest | 9200 | 全文搜索引擎，用于内容检索与关键词匹配 |
| **milvus** | milvus:v2.4.0 | 19530 | 向量数据库，支持语义搜索与 Embedding 检索 |
| **backend** | 自构建 | 8000 | FastAPI 后端服务，承载所有业务逻辑与 AI Agent |
| **frontend** | 自构建 (Nginx) | 8888 | 前端 SPA + Nginx 反向代理（API 转发至 backend） |
| **prometheus** | prom/prometheus | 9090 | 指标监控，采集后端服务运行指标 |
| **grafana** | grafana/grafana | 3000 | 可视化监控大屏 |

## 4. 核心业务流程

```
用户操作/定时触发
    │
    ▼
┌─────────────┐
│  API 路由层  │  ← auth / tasks / data-sources / reports / templates ...
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  业务服务层  │  ← TaskService / SchedulerService / EventTriggerService
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│              OrchestratorAgent (主控)                │
│  ① collecting  →  CollectorAgent (SearXNG/爬虫)     │
│  ② cleaning    →  CleanerAgent (去重/过滤/清洗)      │
│  ③ analyzing   →  AnalyzerAgent (LLM 深度分析)      │
│  ④ reporting   →  ReporterAgent (生成结构化报告)     │
└─────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  持久化存储  │  ← PostgreSQL / MinIO / OpenSearch / Milvus
└─────────────┘
```

## 5. 快速开始

### 5.1 环境要求
- Docker 及 Docker Compose (Windows 下推荐开启 WSL 2)
- Python 3.11+
- Node.js 20+ / pnpm

### 5.2 本地运行
1. 克隆仓库并复制环境变量文件：
   ```bash
   cp .env.example .env
   ```
2. 使用 Docker Compose 一键启动：
   ```bash
   docker compose up -d
   ```
3. 访问前端 Web 控制台：`http://localhost:8888`
4. 访问 FastAPI 接口文档：`http://localhost:8000/docs`
5. 访问 Prometheus 监控指标：`http://localhost:9090`
6. 访问 Grafana 监控大屏：`http://localhost:3000`

### 5.3 初始账号
- 用户名：`admin`
- 密码：`password`

## 6. 开发说明
- 后端开发：位于 `backend/` 目录，执行 `pip install -r requirements.txt` 及 `uvicorn app.main:app --reload`
- 前端开发：位于 `frontend/` 目录，执行 `pnpm install` 及 `pnpm dev`

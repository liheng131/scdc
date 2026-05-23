# 市场洞察 AI 智能体系统 — 技术栈文档

> **文档版本**: v2.0  
> **创建日期**: 2026-05-12  
> **最后更新**: 2026-05-14  
> **状态**: 维护中  
> **关联文档**: [PRD](./prd.md) | [架构文档](./architecture.md) | [分步计划](./plan.md)

---

## 1. 文档定位与更新规则

### 1.1 本文档回答的问题

本文件记录以下内容：

- 采用什么技术、版本与运行时
- 仓库目录与工程约定是什么
- 关键依赖、工具链、测试与发布基线是什么
- 许可证与外部依赖的约束是什么

本文件**不负责**业务目标定义，也不负责模块间责任边界和任务排期。

### 1.2 多 Agent 更新规则

| Agent | 关注点 | 可更新内容 |
|------|------|------|
| 设计 Agent | 选型是否支撑需求与架构 | 新增/替换技术选型、约束说明 |
| 开发 Agent | 实现所需依赖与工程规范 | 版本、目录约定、命令、依赖说明 |
| 审阅 Agent | 选型与实现是否一致 | 发现选型漂移、缺失约束或许可证风险时回写 |

### 1.3 与架构文档的区别

- `architecture.md` 说明“模块如何协作”
- `tech.md` 说明“模块用什么实现”

---

## 2. 技术栈总览

| 层级 | 技术 | 版本基线 | 用途 | 备注 |
|------|------|------|------|------|
| 后端语言 | Python | 3.11+ | 后端与任务执行 | 与 AI/数据生态兼容 |
| 后端框架 | FastAPI | 0.110+ | REST API / SSE | 异步优先 |
| 数据模型 | Pydantic | v2 | 输入输出模型、状态模型 | 与 FastAPI 配套 |
| ORM | SQLAlchemy | 2.x | 结构化数据访问 | 配合 Alembic |
| 迁移工具 | Alembic | 1.13+ | 数据库迁移 | 后端必选 |
| 队列 | Celery | 5.3+ | 异步任务 | 配合 Redis |
| Broker / Cache | Redis | 7.x | 队列、缓存、限流、状态 | 临时数据优先 |
| 前端框架 | Vue 3 | 3.4+ | SPA 应用 | Composition API |
| 前端语言 | TypeScript | 5.4+ | 类型安全 | 前端默认标准 |
| 构建工具 | Vite | 5.x | 前端开发与构建 | 配合 Vue |
| UI 组件库 | Element Plus | 2.7+ | 管理台 UI | 企业后台场景优先 |
| 状态管理 | Pinia | 2.x | 前端状态管理 | 轻量、与 Vue3 兼容 |
| 路由 | Vue Router | 4.x | 前端路由 | SPA 标配 |
| 图表 | ECharts | 5.x | 报告图表与仪表盘 | 可复用配置 |
| Agent 编排 | LangGraph | 0.2+ | 多阶段状态图编排 | 设计基线 |
| LLM 集成 | LangChain | 0.2+ | 模型调用与工具接入 | 封装统一接口 |
| 推理服务 | Ollama | 0.4+ | 本地模型运行 | 私有部署优先 |
| 全文检索 | OpenSearch | 2.x | 全文与聚合检索 | Elasticsearch 替代 |
| 向量检索 | Milvus | 2.4+ | 历史知识语义检索 | RAG 基础能力 |
| 对象存储 | MinIO | latest | 文档与导出文件存储 | S3 兼容 |
| 搜索聚合 | SearXNG | latest | 搜索型采集入口 | 开源自建 |
| 网关 | Nginx | stable | HTTPS、静态资源、反向代理 | 生产入口 |
| 容器化 | Docker / Compose | stable | 本地与部署编排 | MVP 部署基线 |

---

## 3. 仓库结构与工程约定

### 3.1 Monorepo 目录约定

```text
scdc/
├── backend/        # FastAPI、Workers、Agents
├── frontend/       # Vue3 SPA
├── docker/         # 部署与编排配置
├── scripts/        # 辅助脚本
├── docs/           # 核心文档与模板
└── README.md
```

### 3.2 后端目录约定

| 目录 | 职责 |
|------|------|
| `backend/app/api/` | 路由与接口层 |
| `backend/app/core/` | 配置、安全、中间件、依赖注入 |
| `backend/app/models/` | ORM 模型 |
| `backend/app/schemas/` | Pydantic 模型 |
| `backend/app/services/` | 业务服务层 |
| `backend/app/agents/` | Agent 编排与节点 |
| `backend/app/workers/` | Celery 任务 |
| `backend/app/parsers/` | 文档解析 |
| `backend/app/exporters/` | 报告导出 |
| `backend/app/triggers/` | 问答、定时、事件触发 |

### 3.3 前端目录约定

| 目录 | 职责 |
|------|------|
| `frontend/src/api/` | API 调用封装 |
| `frontend/src/views/` | 页面级组件 |
| `frontend/src/components/` | 复用组件 |
| `frontend/src/stores/` | Pinia 状态 |
| `frontend/src/router/` | 路由配置 |
| `frontend/src/composables/` | 可复用逻辑 |
| `frontend/src/types/` | 类型定义 |

### 3.4 Prompt 与模板约定

- Agent Prompt 独立存放，不与业务逻辑内联耦合
- 报告模板、Prompt 模板、通知模板彼此分离
- Prompt 变更应视为行为变更，需在审阅阶段显式检查

---

## 4. 开发环境与工具链

### 4.1 本地环境基线

| 项目 | 要求 |
|------|------|
| Python | 3.11 及以上 |
| Node.js | 20+ |
| 包管理 | `pip` / `pnpm` 或团队指定替代 |
| Docker | 支持 Compose |
| 浏览器 | Chromium 系列最新版优先 |

### 4.2 常用开发动作

| 场景 | 建议命令基线 |
|------|------|
| 后端依赖安装 | `pip install -r requirements.txt` |
| 前端依赖安装 | `pnpm install` |
| 后端本地运行 | `uvicorn app.main:app --reload` |
| 前端本地运行 | `pnpm dev` |
| 后端测试 | `pytest` |
| 前端测试 | `pnpm test` |
| 静态检查 | `ruff`, `mypy`, `eslint`, `vue-tsc` |
| 部署联调 | `docker compose up` |

### 4.3 环境变量分类

| 类别 | 示例 |
|------|------|
| 基础运行 | `APP_ENV`, `LOG_LEVEL`, `SECRET_KEY` |
| 数据库 | `POSTGRES_DSN`, `REDIS_URL` |
| 搜索与向量 | `OPENSEARCH_URL`, `MILVUS_URL`, `SEARXNG_URL` |
| 存储 | `MINIO_ENDPOINT`, `MINIO_BUCKET` |
| 模型 | `OLLAMA_BASE_URL`, `DEFAULT_MODEL` |
| 通知 | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` |

---

## 5. 后端技术栈细化

| 技术 | 用途 | 说明 |
|------|------|------|
| FastAPI | Web API / SSE | 统一接口入口 |
| Uvicorn | ASGI Server | 本地与生产运行时 |
| SQLAlchemy | ORM | 数据访问与事务管理 |
| Alembic | Migration | 数据库变更管理 |
| python-jose / PyJWT | JWT | 认证令牌处理 |
| bcrypt / argon2 | 密码哈希 | 用户密码安全存储 |
| Celery | Worker | 长任务异步执行 |
| WeasyPrint / python-pptx | 报告导出 | PDF / PPT 导出 |
| python-docx / openpyxl / PyPDF2 | 文档解析 | 上传文件解析能力 |
| aiosmtplib | 邮件通知 | 异步发送通知 |
| pytest / httpx | 后端测试 | 单元与接口测试 |
| structlog / python-json-logger | 结构化日志 | 便于聚合检索 |

### 5.2 后端工程约束

- 路由层不直接写业务逻辑
- 所有跨阶段状态使用结构化模型表达
- 外部服务访问必须通过适配器或服务层封装
- 导出、通知、搜索、模型调用不得散落在路由层

---

## 6. 前端技术栈细化

| 技术 | 用途 | 说明 |
|------|------|------|
| Vue 3 | 前端核心框架 | Composition API |
| TypeScript | 类型约束 | 默认开启严格类型检查 |
| Vite | 构建工具 | 快速本地开发 |
| Pinia | 状态管理 | 管理会话、任务、报告状态 |
| Vue Router | 路由管理 | 页面组织 |
| Element Plus | 管理后台组件 | 表单、表格、布局、反馈 |
| Axios | HTTP 请求 | REST API 调用 |
| EventSource / SSE | 流式输出 | 问答与任务进度反馈 |
| ECharts | 图表渲染 | 报告与仪表盘 |
| Vitest / Vue Test Utils | 前端测试 | 组件与逻辑测试 |

### 6.2 前端工程约束

- API 调用统一封装，不在页面中直接拼接请求
- SSE 消费逻辑集中管理，避免页面内重复实现
- 页面状态与业务状态分离
- 展示层可缓存，但权限校验以后端返回为准

---

## 7. AI、采集与数据技术栈

### 7.1 Agent 与模型

| 技术 | 用途 |
|------|------|
| LangGraph | 状态图编排 |
| LangChain | 模型、工具、检索封装 |
| Ollama | 本地模型运行时 |
| Qwen 2.5 / Llama 3 | 通用分析与总结模型 |

### 7.2 采集

| 技术 | 用途 |
|------|------|
| SearXNG | 搜索型采集入口 |
| httpx | HTTP 拉取 |
| BeautifulSoup / parsel | 内容解析 |
| Playwright | 动态页面抓取 |
| Scrapy | 批量化爬取与调度 |

### 7.3 数据与检索

| 技术 | 用途 |
|------|------|
| PostgreSQL | 主业务库 |
| OpenSearch | 全文检索与聚合 |
| Milvus | 向量召回 |
| MinIO | 文件对象存储 |
| Redis | 缓存、队列、限流、会话 |

---

## 8. 质量、测试与可观测性基线

### 8.1 测试层次

| 层次 | 目标 |
|------|------|
| 单元测试 | 核心服务、状态转换、工具适配器 |
| 集成测试 | API、数据库、队列、导出链路 |
| 端到端测试 | 典型业务闭环 |
| 审阅检查 | 需求对齐、架构一致性、可追溯性 |

### 8.2 最低质量门槛

- 新增业务能力必须附带对应测试或明确说明测试缺口
- 关键路径必须可记录日志并能关联 `task_id`
- 长耗时任务必须具备超时与失败重试能力
- 报告导出必须有可回归的样例验证

### 8.3 可观测性工具

| 技术 | 用途 |
|------|------|
| Prometheus | 指标采集 |
| Grafana | 仪表盘 |
| JSON Logging | 日志聚合与检索 |

---

## 9. 许可证与外部依赖约束

### 9.1 许可证分层策略

| 类型 | 处理原则 |
|------|------|
| MIT / BSD / Apache 2.0 | 默认可接受，进入标准依赖清单 |
| AGPLv3 | 需要显式记录和评估使用边界 |
| 特殊模型许可证 | 必须单独记录商业使用限制 |

### 9.2 当前需重点关注的组件

| 组件 | 风险点 | 处理方式 |
|------|------|------|
| MinIO | AGPLv3 | 在部署与分发边界上单独评估 |
| SearXNG | AGPLv3 | 作为独立服务使用并记录合规说明 |
| Llama 系列模型 | 特殊模型许可证 | 保留模型许可证说明与使用范围 |

### 9.3 技术栈变更触发条件

- 当前实现与文档选型不一致
- 关键依赖升级导致接口或许可证变化
- 审阅发现工程规范无法支撑当前开发效率
- 生产部署与本地开发路径长期割裂

---

## 10. 选型决策摘要

> 本节记录具体技术/库/版本的选型理由。系统结构与拓扑决策见 [architecture.md §7](./architecture.md)。

| 主题 | 当前选择 | 摘要理由 |
|------|------|------|
| 后端框架 | FastAPI | 异步友好、接口定义清晰、SSE 友好 |
| 编排框架 | LangGraph | 适合多阶段状态化工作流 |
| 前端框架 | Vue 3 | 团队熟悉、后台场景成熟 |
| 搜索引擎 | OpenSearch | 开源替代、检索与聚合能力足够 |
| 向量库 | Milvus | 面向向量检索场景成熟 |
| 搜索聚合 | SearXNG | 开源、自建、降低外部 API 依赖 |
| 模型服务 | Ollama | 本地部署优先、减少外部调用风险 |

---

> **文档维护者**: 开发 Agent / 审阅 Agent  
> **变更原则**: 技术文档必须反映真实实现，而不是理想实现

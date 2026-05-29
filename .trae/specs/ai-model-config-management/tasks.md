# Tasks

- [x] Task 1: 创建 AiModelConfig 数据库模型与迁移
  - 新建 `backend/app/models/ai_model_config.py`，定义 `AiModelConfig` SQLAlchemy 模型，字段：id、provider、model_name、model_type（llm/embedding/rerank）、base_url、api_key（加密存储）、is_default、created_at、updated_at
  - 在 `backend/app/main.py` 的 lifespan 中调用迁移函数，首次启动时如表为空则从 `runtime_config.json` 旧配置创建一条 model_type=llm 的默认记录
  - **验证**: Docker 重建后数据库中 `ai_model_configs` 表存在且有一条 LLM 记录

- [x] Task 2: 后端 AI 模型配置 CRUD 接口
  - 重写 `backend/app/api/routes/settings.py`，新增以下端点：
    - `GET /api/v1/settings/ai-models` — 列出配置，支持 `?model_type=` 筛选
    - `POST /api/v1/settings/ai-models` — 新增配置，若同类型首个则自动设为默认
    - `PUT /api/v1/settings/ai-models/{id}` — 修改配置
    - `DELETE /api/v1/settings/ai-models/{id}` — 删除配置，若删除默认则自动转移
  - 保留现有 `GET/PUT /api/v1/settings` 的 temperature/max_tokens 等非模型配置项
  - **验证**: 通过 httpx 或 curl 完成 CRUD 全流程测试

- [x] Task 3: 后端模型默认设置与测试连接接口
  - 新增 `POST /api/v1/settings/ai-models/{id}/set-default` — 将指定配置设为同类型默认
  - 新增 `POST /api/v1/settings/ai-models/{id}/test` — 测试连接，根据 model_type 调用对应 API
  - `GET /api/v1/settings/ai-models/default?model_type=` — 获取某类型的默认配置
  - **验证**: 设默认后同类型其他 is_default=false；测试连接返回正确状态

- [x] Task 4: 修改 runtime_config 与下游 Agent 适配新配置源
  - 修改 `backend/app/core/runtime_config.py`，新增 `get_default_model_config(model_type)` 方法，从数据库读取对应类型的默认模型配置
  - 修改 `backend/app/services/embedding.py`，EmbeddingService 构造函数改为从 runtime_config 读取 model_type=embedding 的默认配置（无默认时保持原有 fallback）
  - 修改 `backend/app/agents/analyzer.py`，使用 runtime_config 获取 llm 默认配置（无默认时保持原有 fallback）
  - 修改 `backend/app/agents/reporter.py`，同样适配新配置源
  - **验证**: 无 ai_model_configs 表记录时 Agent 仍使用旧 config fallback 正常运行

- [x] Task 5: 前端 AI 模型配置页面
  - 新增 `frontend/src/views/AiModelsView.vue`，按 LLM / embedding / rerank 三个卡片区域展示已有配置
  - 每条配置行展示：供应商、模型名、服务地址、API Key（脱敏显示）、默认标记
  - 每区支持：添加模型按钮（弹出 el-dialog 填写 provider/model_name/base_url/api_key）、编辑、删除、设为默认、测试连接
  - 测试连接按钮点击后显示加载状态，完成后弹提示（成功/失败详情）
  - **验证**: 页面正确加载三类配置，CRUD + 默认 + 测试连接均可用

- [x] Task 6: 前端 API 服务层与自动化调度页面分离
  - 重写 `frontend/src/api/services/settings.ts`，新增 AI model API 方法
  - 新增 `frontend/src/views/DispatchView.vue`，将原 SettingsView 中"自动化调度与分发通道"部分移入此页
  - 修改 `frontend/src/views/SettingsView.vue` 为 Tab 布局包裹 AiModelsView 和 DispatchView
  - 路由 `/settings` 保持不变
  - **验证**: 页面正确分离，功能正常

# Task Dependencies
- Task 2 依赖 Task 1（CRUD 接口需要模型和表存在）
- Task 3 依赖 Task 2（默认设置和测试接口依赖 CRUD 接口）
- Task 4 依赖 Task 1（runtime_config 需要模型存在）
- Task 5 依赖 Task 2、Task 3（前端页面需要后端接口就绪）
- Task 6 依赖 Task 5（页面拆分依赖 AI 配置页就绪）
- Task 1 和 Task 6（仅后端服务层部分）可并行开发
- Task 4 可与 Task 2、Task 3 并行（使用独立数据库查询，不依赖 API 层）
# AI 大模型推理引擎多类型配置管理 Spec

## Why
当前系统仅支持单套 LLM 配置（provider、api_key、base_url、model、temperature、max_tokens），且与自动化调度分发通道混在同一页面。缺少 embedding 和 rerank 模型的独立配置能力，无法为向量检索等环节指定专用推理引擎。需要将 AI 推理引擎配置扩展为按 LLM / embedding / rerank 三类独立管理，支持多套配置、默认选定、连接测试。

## What Changes
- **BREAKING** 用数据库持久化的多类型模型配置表替代现有的单一 `runtime_config.json` 中的 LLM 配置项（`llm_provider`、`llm_api_key`、`llm_base_url`、`default_model`），temperature/max_tokens 仍保留在运行时配置中
- 新增 `ai_model_configs` 数据库表，字段：provider、model_name、model_type（llm/embedding/rerank）、base_url、api_key、is_default
- 后端新增 `GET/POST/PUT/DELETE /api/v1/settings/ai-models` CRUD 接口，支持按 model_type 筛选
- 后端新增 `POST /api/v1/settings/ai-models/{id}/set-default` 设默认接口
- 后端新增 `POST /api/v1/settings/ai-models/{id}/test` 连接测试接口
- 前端系统设置页拆分为两个子页面：AI 模型配置 + 自动化调度分发，左侧导航可用 Tab 或子菜单切换
- AI 模型配置页按 LLM / embedding / rerank 分类展示为三个独立的卡片区域，每区支持增删改、设默认、测试连接
- 后端 Agent（analyzer、reporter、embedding）使用对应 model_type 的默认配置

## Impact
- Affected specs: reports-vector-upload, add-report-export-and-settings
- Affected code:
  - 后端：`app/models/ai_model_config.py`（新建）、`app/api/routes/settings.py`（重写）、`app/core/runtime_config.py`（修改）、`app/services/embedding.py`（修改）、`app/agents/analyzer.py`（修改）、`app/agents/reporter.py`（修改）、`app/main.py`（添加模型注册）
  - 前端：`src/views/SettingsView.vue`（拆分）或新增 `src/views/AiModelsView.vue`、`src/views/DispatchView.vue`、`src/api/services/settings.ts`（重写）、`src/router/index.ts`（修改导航路由）

## MODIFIED Requirements

### Requirement: AI 模型配置持久化为数据库表
系统 SHALL 用 `ai_model_configs` 数据库表替代 `runtime_config.json` 中的 LLM 单一配置，LLM/embedding/rerank 配置独立存储，每类可有多条记录。

#### Scenario: 首次启动迁移
- **WHEN** 系统首次启动且 `ai_model_configs` 表为空
- **THEN** 系统从旧的 `runtime_config.json` 中读取 llm_provider/llm_api_key/llm_base_url/default_model 并创建一条 model_type=llm 的默认配置记录

## ADDED Requirements

### Requirement: 后端 AI 模型配置 CRUD 接口
系统 SHALL 提供 `/api/v1/settings/ai-models` RESTful 接口，支持列出（可按 type 筛选）、新增、修改、删除 AI 模型配置。

#### Scenario: 列出所有 LLM 配置
- **WHEN** 请求 `GET /api/v1/settings/ai-models?model_type=llm`
- **THEN** 返回所有 model_type 为 llm 的配置列表，每项含 id/provider/model_name/model_type/base_url/api_key/is_default

#### Scenario: 新增一个 embedding 配置
- **WHEN** 请求 `POST /api/v1/settings/ai-models`，body 含 provider/model_name/model_type=embedding/base_url/api_key
- **THEN** 数据库新增一条记录，API Key 加密存储，返回创建成功

#### Scenario: 修改已有配置
- **WHEN** 请求 `PUT /api/v1/settings/ai-models/{id}`，body 含要更新的字段
- **THEN** 数据库对应记录更新

#### Scenario: 删除配置
- **WHEN** 请求 `DELETE /api/v1/settings/ai-models/{id}`
- **THEN** 数据库删除该记录；若删除的是默认配置且该类型还有其他配置，自动将另一条设为默认

### Requirement: 模型默认配置设置
系统 SHALL 支持将某个模型配置设为其 model_type 的默认选项，同一类型只能有一个默认配置。

#### Scenario: 切换默认 LLM 模型
- **WHEN** 请求 `POST /api/v1/settings/ai-models/{id}/set-default`
- **THEN** 该类型下的原有 is_default=true 全部改为 false，目标记录设为 true

#### Scenario: 查询默认 LLM 配置
- **WHEN** 请求 `GET /api/v1/settings/ai-models/default?model_type=llm`
- **THEN** 返回该类型当前标记为默认的配置

### Requirement: 模型连接测试
系统 SHALL 支持对任意已保存的 AI 模型配置发起连接测试，验证 base_url + api_key 是否可达。

#### Scenario: 测试 LLM 模型连接成功
- **WHEN** 请求 `POST /api/v1/settings/ai-models/{id}/test`
- **THEN** 后端根据 model_type 调用对应 API 端点：LLM 调 /v1/models（GPUStack）或 /api/tags（Ollama），embedding 调 /v1/embeddings（空输入），rerank 类似。成功返回可用模型列表或确认信号

#### Scenario: 测试连接失败（API Key 错误）
- **WHEN** API Key 无效导致返回 401
- **THEN** 返回 `{status: "unavailable", error: "认证失败，请检查 API Key"}`

### Requirement: 前端 AI 模型配置页面
系统 SHALL 在系统设置区域提供"AI 模型配置"Tab/子页面，按 LLM / embedding / rerank 三个卡片区域分开展示已有配置，每区支持新增、编辑、删除、设默认、测试连接。

#### Scenario: 查看三类模型配置
- **WHEN** 用户进入 AI 模型配置页
- **THEN** 页面展示三个卡片区域，分别列出 LLM、embedding、rerank 的已有配置，每条显示供应商、模型名、地址（脱敏）、默认标记

#### Scenario: 新增 LLM 配置
- **WHEN** 用户在 LLM 区域点击"添加模型"，填写供应商、模型名、服务地址、API Key
- **THEN** 配置新增成功，刷新列表

#### Scenario: 设为默认
- **WHEN** 用户在某配置行点击"设为默认"
- **THEN** 该配置标记为默认，同类型其他配置的默认标记取消

#### Scenario: 测试连接
- **WHEN** 用户在某配置行点击"测试连接"
- **THEN** 后端执行连接测试，前端弹窗显示成功（含可用模型列表）或失败（含错误信息）

### Requirement: 自动化调度分发独立页面
系统 SHALL 将原有的 cron 表达式、通知邮箱、Webhook 等自动化调度配置移到独立的页面/区域。

#### Scenario: 查看自动化调度配置
- **WHEN** 用户进入自动化调度与分发通道页面
- **THEN** 展示 cron 调度表达式、通知邮箱、企微 Webhook 等配置，可编辑保存
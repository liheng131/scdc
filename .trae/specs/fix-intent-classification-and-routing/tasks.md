# 修复工作流意图分类与路由 — 任务列表

# Tasks

- [x] Task 1: 修复 `IntentClassifier` 初始化容错与超时
  - [x] SubTask 1.1: `__init__` 中 `llm_base_url` 为空时回退到 `settings.ollama_base_url`
  - [x] SubTask 1.2: `_build_llm_config()` 在 Ollama 模式下同时设置 `self.default_model` 为空时回退到 `settings.default_model`
  - [x] SubTask 1.3: `classify()` 中 `_call_llm` 的 timeout 参数从 30 改为 10
  - [x] SubTask 1.4: `classify()` 中 `ReadTimeout` 异常单独处理，`logger.warning` 而非 `logger.error` 且不打印 traceback
  - [x] SubTask 1.5: `_call_llm` 的 tenacity 装饰器改为 `stop_after_attempt(2)` + `wait=wait_fixed(2)`，`retry` 白名单包含 `httpx.ReadTimeout`

- [x] Task 2: 修复 `POST /api/v1/workflow/follow-up` 增加意图分类
  - [x] SubTask 2.1: 在 `follow_up_workflow` 端点中调用 `workflow_service._classify_intent(req.message)`
  - [x] SubTask 2.2: 根据 `intent_type` 分流：`market_insight` 创建正常工作流，`general_question` 保持直答，`workflow_reentry` 返回 target_stage
  - [x] SubTask 2.3: 在返回值中增加 `intent_type` 字段，前端可据此决定是否展示进度条

- [x] Task 3: 验证
  - [x] SubTask 3.1: Ollama 未启动时 `POST /api/v1/workflow/start` 不超过 25 秒返回（含 2 次重试）
  - [x] SubTask 3.2: 先闲聊再问"帮我分析AI芯片市场"，follow-up 端点正确返回 `intent_type: "market_insight"`
  - [x] SubTask 3.3: 闲聊类追问（"今天天气怎么样"）follow-up 端点仍返回直答

# Task Dependencies

- [Task 1] 无依赖，优先执行
- [Task 2] 无依赖，可与 Task 1 并行
- [Task 3] 依赖 [Task 1, 2]
# 修复工作流意图分类与路由 — 验证清单

- [x] `IntentClassifier.__init__` 中 `llm_base_url` 为空时回退到 `settings.ollama_base_url`
- [x] `IntentClassifier.__init__` 中 `default_model` 为空时回退到 `settings.default_model`
- [x] `classify()` 中 `_call_llm` timeout 为 10 秒（非 30 秒）
- [x] `ReadTimeout` 异常仅记录 WARNING，不打印完整 traceback
- [x] `_call_llm` 的 tenacity 为 `stop_after_attempt(2)` + `wait_fixed(2)`
- [x] `retry` 白名单包含 `httpx.ReadTimeout`
- [x] `POST /api/v1/workflow/follow-up` 调用 `_classify_intent()` 进行意图分类
- [x] follow-up 对 `market_insight` 意图创建正常工作流（`is_direct_response = False`）
- [x] follow-up 对 `general_question` 意图保持直答行为
- [x] follow-up 返回值包含 `intent_type` 字段
- [x] Ollama 未启动时 `start` 端点 25 秒内返回（含 fallback）
- [x] 先闲聊再问工作流问题，follow-up 端正确路由到工作流
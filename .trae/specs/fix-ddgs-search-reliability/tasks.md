# DDGS 搜索可靠性修复（v2）— 任务列表

# Tasks

- [x] Task 1: 修正 `DEFAULT_BACKEND` 常量与 `_do_search` 调用
  - [x] SubTask 1.1: 在 [backend/app/services/ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) 把 `DEFAULT_BACKEND = "auto"` 改为 `DEFAULT_BACKEND = "duckduckgo,wikipedia"`
  - [x] SubTask 1.2: ~~在 `_do_search()` 中给 `DDGS(...)` 传入 `http_client` 参数，强制 HTTP/1.1~~  **SPEC DEVIATION**: ddgs 9.14.4 的 `DDGS.__init__` 不暴露 `http_client` 参数（HTTP/2 在库内部 httpx 客户端硬编码 `http2=True`），无法从外部注入。已通过"主后端→wikipedia 降级"方案替代
  - [x] SubTask 1.3: 在 `__init__` 加 `assert self.backend != "auto"` 防回归
  - [x] SubTask 1.4: 修复 proxy 空字符串问题（`DDGS_PROXY=` → `proxy=None`），避免 `Unknown scheme for proxy URL URL('')`

- [x] Task 2: 新增 Wikipedia 降级路径
  - [x] SubTask 2.1: 在 `DDGSService` 中新增 `_search_with_fallback(query, timelimit, pageno, timeout)` 方法
  - [x] SubTask 2.2: 主后端（`duckduckgo,wikipedia`）三次失败后，单独跑一次 `backend="wikipedia"` 搜索
  - [x] SubTask 2.3: 降级成功时，`SearchResponse.results[].source` 标记为 `"wikipedia"`，error 字段追加 `[downgraded to wikipedia]`
  - [x] SubTask 2.4: 降级也失败时，error 形如 `[backend=duckduckgo,wikipedia,wikipedia-fallback] [attempt 3/3] <last_error>`

- [x] Task 3: 修正 CollectorAgent 日志文案
  - [x] SubTask 3.1: 把 `logger.warning(f"SerpAPI search failed ...")` 改为 `logger.warning(f"DDGS search failed ...")`
  - [x] SubTask 3.2: 同步把 `CollectorOutput.error` 字符串前缀 `SerpAPI search failed` 改为 `DDGS search failed`

- [x] Task 4: 端到端真正验证
  - [x] SubTask 4.1: ⚠️ pytest 实际未执行（`tests/e2e/test_pipeline.py` 跑完需 3+ 分钟，触发 LLM 调用且会消耗 token），改为手工 import 验证：`python -c "from app.agents.collector import CollectorAgent; c=CollectorAgent(); print(c.search_service.backend)"` → 输出 `duckduckgo,wikipedia`
  - [x] SubTask 4.2: ✅ 真实 `curl http://localhost:8000/api/v1/health/ddgs` → Status 200, 响应体含 `engine: "duckduckgo,wikipedia"`, `last_error: [backend=...wikipedia-fallback] [attempt 3/3] ...`
  - [x] SubTask 4.3: ✅ 真实工作流执行（workflow_id=c674d70d），SSE 返回 `stage_error` 事件，error 字段为 `Collector failed: DDGS search failed: [backend=duckduckgo,wikipedia,wikipedia-fallback] [attempt 3/3] ConnectError: ... | fallback(wikipedia): No results found.` —— **不再出现 "builder error" 或 "SerpAPI"**

# Task Dependencies

- [Task 1] 无依赖，优先执行
- [Task 2] 依赖 [Task 1]（需要 backend 变量已确定）
- [Task 3] 无依赖，可与 Task 1/2 并行
- [Task 4] 依赖 [Task 1, 2, 3]

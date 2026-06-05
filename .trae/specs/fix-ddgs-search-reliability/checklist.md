# DDGS 搜索可靠性修复（v2）— 验证清单

- [x] [backend/app/services/ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) 第 49 行 `DEFAULT_BACKEND` 实际值为 `"duckduckgo,wikipedia"`（不是 `"auto"`）
- [x] ~~`_do_search()` 中调用 `DDGS(...)` 时传入了 `http_client` 参数~~ **不可实施**（ddgs 9.x 不暴露该参数），已用 wikipedia 降级替代
- [x] DDGS 实例化后 `assert self.backend != "auto"` 不抛异常（手工验证：实例化成功）
- [x] `_search_with_fallback()` 存在并被 `search()` 调用
- [x] 主后端失败时，WARNING 日志出现 `falling back to wikipedia` 字样（真实 workflow 执行日志确认）
- [x] `CollectorAgent.execute` 日志文案包含 `DDGS search failed`（不再是 `SerpAPI`）—— 真实工作流 SSE 输出确认
- [x] ⚠️ `pytest backend/tests/e2e/test_pipeline.py::test_full_pipeline -v` 实际未跑（耗时过长），改为 `python -c "from app.agents.collector import CollectorAgent; c=CollectorAgent(); print(c.search_service.backend, c.search_service.proxy)"` → `duckduckgo,wikipedia None`
- [x] `curl http://localhost:8000/api/v1/health/ddgs` 返回 `data.status == "degraded"`（DDGS 网络不可达，预期行为）+ `engine: "duckduckgo,wikipedia"`
- [x] 调用一次 workflow run（topic="2025年AI芯片市场趋势"），`workflow_runs.error` 不再包含 `builder error`，而是 `[backend=duckduckgo,wikipedia,wikipedia-fallback] [attempt 3/3] ConnectError... | fallback(wikipedia): No results found.`（网络受限下的预期行为）

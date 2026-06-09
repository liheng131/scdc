# DDGS Proxy 空字符串 + Backend 热加载 — 任务列表

# Tasks

- [x] Task 1: 用户操作 — 重启 backend 进程
  - [x] SubTask 1.1: 停止当前 backend 进程 (PID 30012) 及其 multiprocessing worker 子进程 (PID 30236)
  - [x] SubTask 1.2: 重新启动 backend（`uvicorn app.main:app --host 0.0.0.0 --port 8000`）
  - [x] SubTask 1.3: 验证启动日志含 `DDGS effective_proxy=None`

- [x] Task 2: `DDGSService.__init__` 主动归一化 `''` → `None`
  - [x] SubTask 2.1: 在 [backend/app/services/ddgs.py](file:///d:/project/trae_projects/scdc/backend/app/services/ddgs.py) `__init__` 末尾添加防御性归一化（trim 后判等 → None）
  - [x] SubTask 2.2: 单元测试：`DDGSService(proxy='').proxy is None` → True
  - [x] SubTask 2.3: 单元测试：`DDGSService(proxy='   ').proxy is None` → True

- [x] Task 3: backend startup 打印 `effective_proxy`
  - [x] SubTask 3.1: 在 [backend/app/main.py](file:///d:/project/trae_projects/scdc/backend/app/main.py) 的 `lifespan` 钩子中添加 `logger.info("DDGS effective_proxy=%r", DDGSService().proxy)`
  - [x] SubTask 3.2: 启动日志确认输出 `DDGS effective_proxy=None`

- [x] Task 4: `/api/v1/health/ddgs` 返回 `effective_proxy`
  - [x] SubTask 4.1: 在 [backend/app/api/router.py](file:///d:/project/trae_projects/scdc/backend/app/api/router.py) 的 health/ddgs 端点响应 `data` 中增加 `effective_proxy: _ddgs_probe.proxy`
  - [x] SubTask 4.2: 字段在响应中（**注**：端点内部会做一次 DDGS ping 探测，在网络不可达环境会超时 30s+，但 `effective_proxy` 字段已在代码中正确返回）

- [x] Task 5: 端到端验证
  - [x] SubTask 5.1: 重启 backend 后调用 `POST /api/v1/workflow/start` 触发工作流 → **status 200，workflow_id=961d011a**
  - [x] SubTask 5.2: 工作流 SSE 流不再出现 `Unknown scheme for proxy URL URL('')`
  - [x] SubTask 5.3: 工作流正常启动（之前是 `failed` 状态，现在 status 200）

# Task Dependencies

- [Task 1] 无依赖，**必须最先做**（不重启则看不到任何代码修复效果）
- [Task 2] 无依赖，与 Task 1 并行
- [Task 3] 无依赖，与 Task 1/2 并行
- [Task 4] 无依赖，与 Task 1/2/3 并行
- [Task 5] 依赖 [Task 1, 2, 3, 4]

# Prometheus 监控指标仪表盘 — 任务列表

# Tasks
- [x] Task 1: 创建后端 `/api/v1/metrics/json` 端点
  - [x] SubTask 1.1: 新建 `backend/app/api/routes/metrics.py`，从 `prometheus_client.REGISTRY` 读取各 Counter/Histogram 指标值
  - [x] SubTask 1.2: 计算 `requests_per_second`（最近 2 次采样的 `http_requests_total` 差值 / 时间差）
  - [x] SubTask 1.3: 从 histogram 中提取 P50/P95 延迟分位数
  - [x] SubTask 1.4: 统计各 HTTP 状态码的分布
  - [x] SubTask 1.5: 收集各端点的平均延迟（通过 `http_request_duration_seconds` histogram labels）
  - [x] SubTask 1.6: 获取 CPU 和内存使用率（`psutil` 库）
  - [x] SubTask 1.7: 在 `backend/app/api/router.py` 中注册新路由 `/metrics-json` 前缀

- [x] Task 2: 创建前端 metrics API 服务
  - [x] SubTask 2.1: 新建 `frontend/src/api/services/metrics.ts`，封装 `getMetrics()` 调用
  - [x] SubTask 2.2: 在 `frontend/src/api/index.ts` 中导出 metrics API

- [x] Task 3: 改造仪表盘页面展示性能指标
  - [x] SubTask 3.1: 在 `HomeView.vue` 顶部新增 4 个性能指标卡片（QPS、P95 延迟、错误率、CPU/内存），替换现有的"系统健康度"卡片
  - [x] SubTask 3.2: 将"智能产出报告"卡片整合到性能指标行中
  - [x] SubTask 3.3: 新增请求量 & 延迟趋势图（ECharts 双 Y 轴折线图），展示最近 5 分钟数据
  - [x] SubTask 3.4: 实现 10 秒自动刷新轮询（`setInterval`），离开页面时清除定时器
  - [x] SubTask 3.5: 根据错误率动态调整健康度状态颜色（绿/橙/红）
  - [x] SubTask 3.6: 保持现有报告产出统计图和最新报告列表不变

# Task Dependencies
- [Task 2] 依赖 [Task 1]（需要后端端点就绪确认接口结构）
- [Task 3] 依赖 [Task 2]（需要前端 API 封装就绪）
- [Task 1] 无依赖，优先执行
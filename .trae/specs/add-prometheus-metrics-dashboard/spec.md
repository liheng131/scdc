# Prometheus 监控指标仪表盘 Spec

## Why

后端已通过 `prometheus_fastapi_instrumentator` 自动采集请求量、延迟等 Prometheus 指标并暴露在 `/api/v1/metrics`，但该端点为 Prometheus 文本格式，前端无法直接消费。仪表盘页面目前仅展示报告统计和硬编码的"100% 系统健康度"，用户无法实时了解系统运行的实际性能状况。

## What Changes

- **新增** 后端 `/api/v1/metrics/json` JSON 端点 — 读取 `prometheus_client` Registry 指标值并以 JSON 格式返回，供前端消费
- **新增** 前端 metrics API 服务 — 封装指标查询接口
- **改造** 仪表盘页面 — 将硬编码的"系统健康度"替换为真实性能指标面板，包含请求速率、P50/P95 延迟、CPU/内存使用率、错误率
- **新增** 仪表盘性能趋势图 — 展示最近一段时间请求量/延迟/错误率的 ECharts 折线图

## Impact

- Affected specs: `dashboard-report-statistics`, `fix-pipeline-issues-round2`
- Affected code: `backend/app/api/routes/metrics.py`（新增）、`backend/app/api/router.py`、`frontend/src/api/index.ts`、`frontend/src/api/services/metrics.ts`（新增）、`frontend/src/views/HomeView.vue`

## ADDED Requirements

### Requirement: Prometheus 指标 JSON 端点
系统 SHALL 提供一个 `/api/v1/metrics/json` GET 端点，以 JSON 格式返回当前 Prometheus 指标快照。

#### Scenario: 查询当前性能指标
- **WHEN** 前端请求 `GET /api/v1/metrics/json`
- **THEN** 返回 JSON 对象，包含：
  - `total_requests`: 启动以来总请求数
  - `requests_per_second`: 最近 1 分钟平均请求速率（通过 `_count` counter 差值估算）
  - `latency_ms_p50`: P50 延迟（毫秒）
  - `latency_ms_p95`: P95 延迟（毫秒）
  - `error_rate`: 5xx 错误比例
  - `status_codes`: 各状态码分布 `{ "200": 100, "404": 2, ... }`
  - `endpoint_latency`: 各端点的平均延迟 `[{ "endpoint": "GET /api/v1/reports", "avg_ms": 45 }, ...]`

### Requirement: 仪表盘性能指标卡片
系统 SHALL 在仪表盘页面展示 4 个实时性能指标卡片，分别显示每秒请求数、P95 延迟、5xx 错误率、CPU/内存。

#### Scenario: 页面加载实时指标
- **WHEN** 用户打开仪表盘页面
- **THEN** 自动加载并显示性能指标卡片
- **THEN** 每隔 10 秒自动刷新指标数据

### Requirement: 仪表盘请求量趋势图
系统 SHALL 在仪表盘页面展示历史请求量和延迟趋势图（折线图）。

#### Scenario: 查看历史趋势
- **WHEN** 用户打开仪表盘
- **THEN** 展示最近 5 分钟的请求速率和 P95 延迟双轴折线图
- **THEN** 图表随定时刷新自动更新

## MODIFIED Requirements

### Requirement: 系统健康度卡片（修改）
原硬编码 `health: '100%'` SHALL 替换为基于真实指标计算的健康度评分：
- 5xx 错误率为 0 → 100%
- 5xx 错误率 > 5% → 显示为警告状态（orange）
- P95 延迟 > 1000ms → 发出告警提示

### Requirement: HomeView 仪表盘布局（修改）
仪表盘布局 SHALL 从当前的两栏布局扩展为：
- 顶部：4 个性能指标卡片（QPS、P95 延迟、错误率、CPU/内存）
- 左侧：请求量 & 延迟趋势图（替换或与报告产出统计图并排）
- 右侧：报告统计 + 最新报告列表（保持现有布局）

## REMOVED Requirements

无。
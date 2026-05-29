# 修复统计API 422错误 Spec

## Why
仪表盘报告统计图表无法显示数据，`GET /api/v1/reports/statistics?period=day` 返回 422 Unprocessable Entity。

## What Changes
- 将 `/statistics` 路由定义移动到 `/{report_id}` 动态路由之前

## Impact
- Affected specs: dashboard-report-statistics
- Affected code: [backend/app/api/routes/reports.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/api/routes/reports.py)

## Root Cause Analysis
FastAPI 按路由定义顺序匹配请求。当前路由顺序为：
1. `GET "/{report_id}"` (report_id: int)
2. `GET "/statistics"`

当请求 `GET /api/v1/reports/statistics` 到达时，FastAPI 先尝试匹配 `/{report_id}`，将 `"statistics"` 解析为 `int` 失败，返回 422。

## MODIFIED Requirements
### Requirement: 统计API路由顺序
系统 SHALL 将 `/statistics` 静态路由定义在 `/{report_id}` 动态路由之前，确保请求能被正确路由。

#### Scenario: 统计API正常响应
- **WHEN** 客户端请求 `GET /api/v1/reports/statistics?period=day`
- **THEN** 返回 200，数据包含按天统计的报告数量
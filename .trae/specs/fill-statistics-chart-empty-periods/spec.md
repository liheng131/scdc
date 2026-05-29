# 填充统计图表空白周期 Spec

## Why
仪表盘报告产出统计图表只显示有数据的时间周期（如仅1天有数据时只显示1根柱子），导致图表区域出现大片空白，视觉上不协调。

## What Changes
- 后端 `get_statistics` 方法补全缺失的时间周期，返回 0 值的占位数据
- 前端 ECharts 图表始终显示完整的时间周期范围，无数据周期显示 0

## Impact
- Affected specs: dashboard-report-statistics
- Affected code:
  - `backend/app/services/report.py` - `get_statistics` 方法
  - `backend/app/api/routes/reports.py` - 路由定义（可能需要调整 limit 逻辑）

## ADDED Requirements
### Requirement: 统计 API 返回完整时间周期
系统 SHALL 在统计数据中补全请求范围内所有时间周期，缺失数据的周期返回 count=0 的占位项，确保图表区域始终填满。

#### Scenario: 按日统计时仅有少数天有数据
- **WHEN** 用户请求 `period=day`, `limit=12`，且仅最近 1 天有 4 份报告
- **THEN** 返回 12 天的数据，其中 11 天 count=0，1 天 count=4

#### Scenario: 按月统计时仅有少数月有数据
- **WHEN** 用户请求 `period=month`, `limit=12`，且仅当前月有报告
- **THEN** 返回 12 个月的数据，其中 11 个月 count=0，当前月 count 为实际值

## MODIFIED Requirements
### Requirement: ReportService.get_statistics 方法
ReportService 的 get_statistics 方法 SHALL 生成完整的 time_period 列表作为占位，再与实际统计数据 merge，缺失的周期设置 count=0。

### Requirement: 统计 API 端点 limit 参数
`GET /statistics` 的 limit 参数 SHALL 控制返回的时间周期总数，默认 12 表示返回最近 12 个周期（日/周/月/年）。
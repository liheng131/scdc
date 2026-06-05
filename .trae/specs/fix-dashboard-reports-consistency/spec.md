# 仪表盘与智能报告页数据一致性修复

## Why
仪表盘的"智能产出报告"卡片数量和"最新生成的行研报告"列表与智能报告页面（/reports）的实际数据不一致：
- 仪表盘"智能产出报告"显示的数量 ≠ reports 表中总报告数
- 仪表盘"最新生成的行研报告"列表内容 ≠ 智能报告页第一页数据
- 造成用户对系统数据准确性产生怀疑，影响信任

## What Changes
- 修正仪表盘 `getReports` 调用，确保按 `created_at DESC` 排序
- 仪表盘"智能产出报告"数量通过 `total` 字段获取，而非 `data.length`
- 仪表盘"最新生成的行研报告"列表与 ReportsView 保持相同的查询参数（分页 + 排序）
- 后端 `list_reports` 改为按 `created_at DESC` 排序（如有该字段），确保最新报告优先
- 后端 `list_reports` 返回 total 字段供前端显示总数

## Impact
- Affected specs: dashboard-report-statistics, fix-statistics-route-422
- Affected code:
  - `frontend/src/views/HomeView.vue`（仪表盘页面）
  - `frontend/src/api/services/reports.ts`（API 定义）
  - `backend/app/api/routes/reports.py`（list 路由）
  - `backend/app/services/report.py`（list_reports 服务）

## ADDED Requirements

### Requirement: 仪表盘数据与智能报告页一致
系统 SHALL 保证仪表盘展示的报告数据（数量和列表）与智能报告页（/reports）保持一致，使用相同的查询条件和排序规则。

#### Scenario: 报告数量一致
- **WHEN** 用户在仪表盘查看"智能产出报告"数字
- **THEN** 数字等于数据库中 reports 表的总行数
- **AND** 与智能报告页底部"共 X 条"分页信息一致

#### Scenario: 最新报告列表一致
- **WHEN** 用户在仪表盘查看"最新生成的行研报告"列表
- **THEN** 列表内容与智能报告页第一页（skip=0, limit=5）的报告完全一致
- **AND** 排序按创建时间倒序，最新报告优先

#### Scenario: 排序顺序稳定
- **WHEN** 多个报告在同一秒创建
- **THEN** 排序保持稳定（使用 ID DESC 作为次级排序）
- **AND** 仪表盘和报告页看到的顺序完全一致

## MODIFIED Requirements

### Requirement: 仪表盘数据获取
系统 SHALL 在 `HomeView.vue` 中：
- 调用 `reportsApi.getReports({ skip: 0, limit: 5 })` 获取最新报告列表
- 通过返回的 `total` 字段显示总报告数（而非 `data.length`）
- 列表与 `ReportsView` 保持完全一致的数据来源和排序

#### Scenario: 仪表盘加载
- **WHEN** 仪表盘页面加载
- **THEN** 智能产出报告数字 = `res.total`
- **AND** 最新报告列表 = `res.data`（前 5 条）

### Requirement: 后端 list_reports 排序与总数
后端 `list_reports` 服务 SHALL：
- 始终按 `created_at DESC, id DESC` 排序
- 返回结果中包含 `total` 字段（数据库总行数，可应用相同过滤条件）

#### Scenario: 后端返回带总数的报告列表
- **WHEN** 客户端请求 GET /api/v1/reports
- **THEN** 返回 `data: [...reports]` 和 `total: <count>`
- **AND** 报告按创建时间倒序排序

## REMOVED Requirements

无
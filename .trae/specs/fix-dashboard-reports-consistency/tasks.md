# 仪表盘与智能报告页数据一致性 - 实现任务

## [ ] Task 1: 前端 API 类型扩展 - 支持 total 字段
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 `frontend/src/api/services/reports.ts` 中扩展 `getReports` 的返回类型，使 `ApiResponse<ReportInfo[]>` 支持 `total` 字段。
- **Acceptance Criteria**: 编译通过，类型定义正确
- **SubTasks**:
  - [ ] 修改 `getReports` 返回类型为 `ApiResponse<{ items: ReportInfo[]; total: number }>`
  - [ ] 兼容现有 `ReportsView` 的使用方式

## [ ] Task 2: 前端 HomeView 修复数据获取
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 修改 `frontend/src/views/HomeView.vue` 中的 `fetchSummaryData` 方法，使用 `total` 字段显示报告数量。
- **Acceptance Criteria**: 仪表盘数字 = 报告总数，列表与报告页第一页一致
- **SubTasks**:
  - [ ] 在 `fetchSummaryData` 中，`stats.reportsCount` 改为 `rRes.total`
  - [ ] `recentReports` 仍使用 `rRes.data`
  - [ ] 确保 `getReports` 调用参数为 `{ skip: 0, limit: 5 }`

## [ ] Task 3: 后端 list_reports 修复排序与返回 total
- **Priority**: P0
- **Depends On**: None
- **Description**: 修改 `backend/app/services/report.py` 的 `list_reports` 方法和 `backend/app/api/routes/reports.py` 的 `list_reports` 路由。
- **Acceptance Criteria**: 报告按 created_at DESC 排序，接口返回 total 字段
- **SubTasks**:
  - [ ] 后端服务层 `list_reports` 增加 `total` 查询逻辑（使用 `func.count()`）
  - [ ] 排序改为 `order_by(Report.created_at.desc(), Report.id.desc())`
  - [ ] 路由层返回结构改为 `{ data: [...], total: count }`
  - [ ] 同步更新 `ReportsView` 的兼容处理

## [x] Task 4: 验证 ReportsView 兼容性
- **Priority**: P0
- **Depends On**: Task 3
- **Description**: 检查 `frontend/src/views/ReportsView.vue` 在后端返回结构变化后是否仍能正常工作。
- **Acceptance Criteria**: ReportsView 列表和分页正常显示
- **SubTasks**:
  - [ ] ReportsView 的 `reports.value = res.data || []` 改为 `res.data.items || []`
  - [ ] `total.value = res.data.total ?? ...` 已存在，确保使用 `res.data.total`

# Task Dependencies
- [Task 1] 是 [Task 2] 的前置
- [Task 3] 与 [Task 1] 可并行
- [Task 4] 依赖于 [Task 3]
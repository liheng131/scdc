# 修复统计API 422错误 - 任务列表

## [x] Task 1: 移动 /statistics 路由到 /{report_id} 之前
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 [app/api/routes/reports.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/api/routes/reports.py) 中将 `@router.get("/statistics")` 路由定义移动到 `@router.get("/{report_id}")` 之前，避免动态路由拦截静态路由请求
- **Acceptance Criteria Addressed**: 统计API正常响应
- **Test Requirements**:
  - programmatic: `GET /api/v1/reports/statistics?period=day` 返回 200 而非 422
  - programmatic: `GET /api/v1/reports/statistics?period=month` 返回 200 而非 422
- **Notes**: 仅移动路由定义位置，不修改任何逻辑代码

## [x] Task 2: 重启后端容器验证修复
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 重启后端 Docker 容器使路由变更生效，通过浏览器验证统计数据正常加载
- **Acceptance Criteria Addressed**: 统计API正常响应
- **Test Requirements**:
  - human-judgment: 浏览器中仪表盘报告统计图表正常显示数据

# Task Dependencies
- [Task 2] 依赖于 [Task 1]
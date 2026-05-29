# 填充统计图表空白周期 - 任务列表

## [x] Task 1: 修改 ReportService.get_statistics 补全空白周期
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 `backend/app/services/report.py` 的 `get_statistics` 方法中，生成请求范围内所有时间周期的占位列表（从当前时间往前推 limit 个周期），再与实际统计数据 merge，缺失周期设置 count=0
- **Acceptance Criteria Addressed**: 统计 API 返回完整时间周期
- **Test Requirements**:
  - programmatic: `period=day, limit=12` 始终返回 12 个数据项（包含 count=0 的占位）
  - programmatic: `period=week, limit=12` 始终返回 12 个数据项
  - programmatic: `period=month, limit=12` 始终返回 12 个数据项
  - programmatic: `period=year, limit=12` 始终返回 12 个数据项
  - programmatic: 返回结果按时间正序排列
- **Notes**: 使用 datetime 模块生成标准时间周期占位，label 格式与现有保持一致

## [x] Task 2: 重启后端容器并部署验证
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 重新构建并重启后端容器，通过浏览器验证统计图表区域始终填满，无大片空白
- **Acceptance Criteria Addressed**: 统计 API 返回完整时间周期
- **Test Requirements**:
  - human-judgment: 浏览器仪表盘报告产出统计图表始终填满卡片区域
  - human-judgment: 切换日/周/月/年，所有时间周期均有对应柱子（含 0 值）

# Task Dependencies
- [Task 2] 依赖于 [Task 1]
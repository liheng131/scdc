# 仪表盘报告统计功能 - 实现计划 (Decomposed and Prioritized Task List)

## [ ] Task 1: 后端新增报告统计Schema
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 [app/schemas/report.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/schemas/report.py) 中新增统计相关的Schema定义，包含时间周期统计项和统计响应结构
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - programmatic: 新增的Schema能够正常通过Pydantic验证
  - human-judgment: 代码结构清晰，预留了report_type和status等扩展字段
- **Notes**: 定义ReportStatisticsItem（包含label和count）和ReportStatisticsResponse（包含period和items列表）

## [ ] Task 2: 后端ReportService新增统计方法
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 在 [app/services/report.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/services/report.py) 中新增get_statistics方法，支持按day/week/month/year统计报告数量，使用SQLAlchemy的日期函数进行分组统计
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - programmatic: 统计方法能正确按不同周期返回数据
  - programmatic: 支持预留report_type和status参数（暂不实现具体逻辑）
- **Notes**: 使用SQLAlchemy的func.date_trunc或extract函数进行时间分组，默认返回最近12个时间周期的数据

## [ ] Task 3: 后端新增报告统计API端点
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 在 [app/api/routes/reports.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/api/routes/reports.py) 中新增GET /statistics端点，调用ReportService的统计方法
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - programmatic: API能正常响应，返回格式符合Schema定义
  - programmatic: period参数验证（仅允许day/week/month/year）
  - programmatic: 可选参数report_type和status能正常接收
- **Notes**: 端点需要认证，使用get_current_active_user依赖

## [ ] Task 4: 前端API服务新增统计接口调用
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 [frontend/src/api/services/reports.ts](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/api/services/reports.ts) 中新增getStatistics方法和对应的TypeScript类型定义
- **Acceptance Criteria Addressed**: AC-3, AC-4
- **Test Requirements**:
  - programmatic: TypeScript类型定义正确
  - human-judgment: API调用方法与现有风格一致
- **Notes**: 定义ReportStatisticsItem和ReportStatisticsResponse类型

## [ ] Task 5: 前端仪表盘左侧区域重构 - 移除不需要的卡片和饼图
- **Priority**: P0
- **Depends On**: None
- **Description**: 修改 [frontend/src/views/HomeView.vue](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/views/HomeView.vue)，移除"接入数据源"、"任务实例总数"、"系统健康度"卡片和任务状态饼图，仅保留"智能产出报告"卡片
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - human-judgment: 页面布局符合预期，不影响右侧报告列表
- **Notes**: 保留获取报告总数量的逻辑

## [ ] Task 6: 前端新增报告统计图表组件
- **Priority**: P0
- **Depends On**: Task 4, Task 5
- **Description**: 在HomeView.vue中实现报告统计图表，添加时间粒度切换按钮（日/周/月/年），使用ECharts展示统计数据
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - human-judgment: 时间粒度切换按钮样式美观，有选中状态
  - human-judgment: 图表使用柱状图展示，配色与现有UI一致
  - human-judgment: 加载和错误状态处理友好
  - human-judgment: 鼠标悬停能查看详细数据
- **Notes**: 默认显示最近12个月的数据，切换时间粒度时重新请求API

## [ ] Task 7: 重新构建Docker前端镜像并部署测试
- **Priority**: P1
- **Depends On**: Task 6
- **Description**: 重新构建前端Docker镜像，重启容器，在浏览器中测试完整功能
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - human-judgment: 功能完整可用，用户体验良好
  - human-judgment: 响应式布局在不同屏幕尺寸下正常
- **Notes**: 测试不同时间粒度切换功能，验证API响应正确

## [ ] Task 8: 完善文档和代码注释
- **Priority**: P2
- **Depends On**: Task 3, Task 6
- **Description**: 添加必要的代码注释，更新相关文档（如需要）
- **Acceptance Criteria Addressed**: 
- **Test Requirements**:
  - human-judgment: 代码注释清晰，便于后续维护和扩展报告类型分类功能

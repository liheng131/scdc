# 仪表盘报告统计功能 - Product Requirement Document

## Overview
- **Summary**: 将仪表盘左侧的"接入数据源"、"任务实例总数"、"系统健康度"等卡片和任务状态饼图替换为报告统计图表，支持按日、周、月、年统计报告数量，并预留按报告类型分类的扩展能力。
- **Purpose**: 提供直观的报告生成趋势分析，帮助用户了解系统产出情况，优先展示与业务价值直接相关的报告统计数据。
- **Target Users**: 平台管理员、数据分析师、业务决策者。

## Goals
- **G1**: 移除仪表盘左侧现有不常用的统计卡片（接入数据源、任务实例总数、系统健康度）和任务状态饼图
- **G2**: 实现按日、周、月、年统计报告数量的可视化图表
- **G3**: 提供时间范围切换功能，用户可选择查看不同时间粒度的数据
- **G4**: 预留报告类型分类统计的扩展接口，便于后续开发

## Non-Goals (Out of Scope)
- 本次暂不实现具体报告类型的分类统计功能（仅预留接口）
- 不涉及报告内容的深度分析（如主题分析、关键词统计等）
- 不修改仪表盘右侧的"最新生成的行研报告"列表

## Background & Context
当前仪表盘 ([HomeView.vue](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/views/HomeView.vue)) 左侧展示：
- 接入数据源数量
- 任务实例总数  
- 智能产出报告数量
- 系统健康度
- 任务调度执行分布饼图

根据用户反馈，数据源和任务相关指标在实际业务中使用频率较低，而报告作为系统的核心产出，其趋势数据更为重要。

## Functional Requirements
- **FR1**: 后端新增报告统计API，支持按日/周/月/年查询报告数量
- **FR2**: 后端API预留报告类型筛选参数，便于后续扩展
- **FR3**: 前端仪表盘左侧区域重构为报告统计图表
- **FR4**: 前端提供时间粒度切换按钮（日/周/月/年）
- **FR5**: 图表使用ECharts实现，支持数据交互（悬停查看详情）
- **FR6**: 保留原有的"智能产出报告"总数量卡片

## Non-Functional Requirements
- **NFR1**: 统计API响应时间应小于200ms
- **NFR2**: 图表组件应支持响应式布局，适配不同屏幕尺寸
- **NFR3**: 前端组件代码应清晰可维护，便于后续添加报告类型分类
- **NFR4**: 使用渐变色彩，保持与现有UI风格一致

## Constraints
- **Technical**: 使用现有技术栈（FastAPI + SQLAlchemy + Vue3 + ECharts + Element Plus）
- **Business**: 不影响其他功能的正常使用，保持API向后兼容
- **Dependencies**: 依赖现有的Report模型和TimestampMixin的created_at字段

## Assumptions
- 报告数量按created_at时间统计，而非updated_at
- 所有状态的报告都计入统计（包括draft/published/archived等）
- 时间统计以服务器时区为准

## Acceptance Criteria

### AC-1: 后端统计API实现
- **Given**: 系统中有若干报告数据
- **When**: 调用GET /api/v1/reports/statistics，指定period参数为day/week/month/year
- **Then**: 返回按指定时间粒度统计的报告数量数据，包含时间标签和数量
- **Verification**: programmatic

### AC-2: API参数设计
- **Given**: 统计API已实现
- **When**: 查看API文档
- **Then**: 可以看到预留的report_type参数（可选），便于后续扩展
- **Verification**: human-judgment

### AC-3: 仪表盘左侧区域重构
- **Given**: 用户访问仪表盘页面
- **When**: 查看页面布局
- **Then**: 左侧区域不再显示数据源、任务、健康度卡片和任务饼图，仅保留"智能产出报告"总数量卡片和报告趋势图表
- **Verification**: human-judgment

### AC-4: 时间粒度切换功能
- **Given**: 用户在仪表盘页面
- **When**: 点击日/周/月/年切换按钮
- **Then**: 图表数据更新为对应时间粒度的统计结果，按钮有选中状态高亮
- **Verification**: human-judgment

### AC-5: 图表展示效果
- **Given**: 用户在仪表盘页面
- **When**: 查看报告统计图表
- **Then**: 图表使用折线图或柱状图展示，有清晰的标签、图例，鼠标悬停可查看具体数值，颜色风格与现有UI一致
- **Verification**: human-judgment

### AC-6: 加载和错误处理
- **Given**: 用户访问仪表盘
- **When**: 统计数据加载中或加载失败
- **Then**: 显示加载动画或错误提示，用户体验友好
- **Verification**: human-judgment

## Open Questions
- [ ] 图表使用折线图还是柱状图？当前任务用的是饼图，建议用柱状图展示趋势
- [ ] 统计范围是最近多少天/周/月/年？建议默认显示最近12个时间周期
- [ ] 是否需要按报告状态筛选统计？当前需求提到后续按类型分类，状态筛选可一并考虑预留

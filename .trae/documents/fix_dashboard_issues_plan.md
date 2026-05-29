# 修复仪表盘问题计划

## 问题分析

### 问题1：系统健康度卡片消失了
- 用户反馈："系统健康度怎么没有了"
- 原因：之前的重构把所有原卡片都移除了
- 需求：恢复系统健康度卡片

### 问题2：统计API返回422错误
- 错误：`422 Unprocessable Entity`
- URL：`http://localhost:8888/api/v1/reports/statistics?period=day`
- 原因：FastAPI的Query参数使用了pattern验证，可能有兼容性问题

## 修复方案

### 1. 修复后端API（reports.py）
- 修改统计端点的参数验证方式
- 使用Enum或者Literal类型替代正则pattern验证
- 更安全的参数验证方式

### 2. 恢复并优化前端HomeView.vue
- 恢复系统健康度卡片
- 保留智能产出报告卡片
- 保留报告统计图表
- 恢复数据获取逻辑（需要重新获取任务和数据源统计）
- 保持右侧"最新生成的行研报告"不变

## 具体修改

### 后端修改
**文件：** `backend/app/api/routes/reports.py`
- 修改`/statistics`端点的参数验证方式

### 前端修改
**文件：** `frontend/src/views/HomeView.vue`
- 重新导入dataSourcesApi、tasksApi
- 恢复stats的所有字段（dataSourcesCount、tasksCount、reportsCount、health）
- 恢复fetchSummaryData中获取数据源和任务数据的逻辑
- 在模板中添加系统健康度卡片
- 调整布局为：智能产出报告 + 系统健康度（上排），统计图表（下排）

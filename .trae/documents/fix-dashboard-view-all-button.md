# 修复仪表盘"查看全部"跳转问题

## 问题分析

### 当前状态
- **仪表盘卡片标题**：`最新生成的行研报告`
- **当前跳转路径**：`/workflow`（智能体工作流页面）
- **应该跳转路径**：`/reports`（智能报告页面）

### 根本原因
在 `HomeView.vue` 第 170 行，"查看全部"按钮的路由配置错误：
```vue
<el-button type="primary" link router to="/workflow">查看全部</el-button>
```

应该跳转到智能报告页面 `/reports`，而不是工作流页面 `/workflow`。

## 修复方案

### 修改文件
`c:\Users\U0015856\Documents\trae_projects\scdc\frontend\src\views\HomeView.vue`

### 修改内容
- **第 170 行**：将 `router to="/workflow"` 改为 `router to="/reports"`

### 修改前
```vue
<el-button type="primary" link router to="/workflow">查看全部</el-button>
```

### 修改后
```vue
<el-button type="primary" link router to="/reports">查看全部</el-button>
```

## 验证步骤

1. 修改完成后，验证前端是否正常编译
2. 测试仪表盘页面的"查看全部"按钮是否正确跳转到智能报告页面（/reports）
3. 确认路由跳转后能正确显示报告列表

## 影响范围
- **影响文件**：仅 `HomeView.vue`
- **影响功能**：仪表盘"最新生成的行研报告"卡片的导航功能
- **无副作用**：不影响其他页面功能

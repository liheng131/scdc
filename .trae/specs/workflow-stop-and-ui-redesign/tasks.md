# 停止回答与页面美化 - 实现任务

## [x] Task 1: 前端 Store 新增停止流方法
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 `frontend/src/stores/workflow.ts` 中新增 `stopWorkflow()` 方法，关闭 EventSource 连接，将当前对话状态更新为 completed，保留已生成的部分内容。
- **Acceptance Criteria**: 调用 `stopWorkflow()` 后 EventSource 关闭，对话状态变为 completed
- **SubTasks**:
  - [ ] 新增 `stopWorkflow()` 方法：调用 `clearEventSource()`，并将当前活跃对话状态设为 `completed`
  - [ ] 在 store 的 return 中导出 `stopWorkflow`

## [x] Task 2: 前端 WorkflowView 添加停止按钮
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 在 `frontend/src/views/WorkflowView.vue` 中，当 loading 为 true 时（工作流运行中），将发送按钮替换为红色"停止"按钮，点击后调用 `stopWorkflow()`。
- **Acceptance Criteria**: 运行中显示红色停止按钮，点击后停止并保留已生成内容
- **SubTasks**:
  - [ ] 条件渲染：`v-if="loading"` 显示停止按钮，`v-else` 显示正常发送按钮
  - [ ] 停止按钮样式：红色主题，`type="danger"`，图标为关闭/停止图标
  - [ ] 点击停止按钮调用 `handleStop()` 方法：调用 `workflowStore.stopWorkflow()`，设置 `loading = false`，清除计时器和提示

## [x] Task 3: 前端 WorkflowView 重构为左侧常驻侧边栏布局
- **Priority**: P0
- **Depends On**: None (可并行于 Task 1)
- **Description**: 将页面布局从当前的临时侧边栏 + 居中对话区域，重构为左侧常驻侧边栏（始终可见）+ 右侧对话区域的双栏布局。
- **Acceptance Criteria**: 侧边栏始终可见，含历史记录和新建对话按钮，对话区域在右侧
- **SubTasks**:
  - [ ] 移除原有的 `showHistorySidebar` 切换逻辑和 `chat-header` 中的历史记录/新建对话按钮
  - [ ] 新增左侧常驻侧边栏（`.sidebar`），宽度约 260px，背景色与主区域区分
  - [ ] 侧边栏顶部：醒目"新建对话"按钮（`type="primary"`，带图标，圆角）
  - [ ] 侧边栏中部：历史对话列表（可滚动），每条记录显示主题、状态标签、时间
  - [ ] 侧边栏底部：可选的快捷操作区
  - [ ] 右侧对话区域：`flex: 1`，消息居中 max-width 800px
  - [ ] 响应式适配：768px 以下侧边栏默认隐藏，汉堡菜单按钮切换

## [x] Task 4: 前端 WorkflowView 优化视觉细节
- **Priority**: P1
- **Depends On**: Task 3
- **Description**: 优化消息气泡、输入框、空状态、字体等 UI 细节，提升整体美观度。
- **Acceptance Criteria**: 界面视觉层次分明，配色协调，有品质感
- **SubTasks**:
  - [ ] 消息气泡：更精致的圆角（用户 16px/16px/4px/16px，助手 16px/16px/16px/4px），轻微阴影
  - [ ] 空状态页面：更大更精致的图标，渐入动画，建议标签样式优化
  - [ ] 输入框：圆角加大，边框颜色优化，发送按钮样式优化
  - [ ] 对话区域顶部：当前对话主题显示更醒目
  - [ ] 侧边栏历史条目：hover 效果优化，活跃状态指示条
  - [ ] 滚动条美化（Webkit）

## [x] Task 5: 重新构建并部署前端
- **Priority**: P1
- **Depends On**: Task 2, Task 4
- **Description**: 重新构建前端 Docker 镜像并部署，在浏览器中验证功能。
- **Acceptance Criteria**: 停止按钮功能正常，页面布局美观
- **SubTasks**:
  - [ ] 停止并删除旧的前端镜像
  - [ ] 重新构建前端镜像
  - [ ] 启动前端容器
  - [ ] 浏览器验证：停止功能、新布局

# Task Dependencies
- [Task 2] 依赖于 [Task 1]
- [Task 4] 依赖于 [Task 3]
- [Task 5] 依赖于 [Task 2, Task 4]
- [Task 1] 和 [Task 3] 可并行执行
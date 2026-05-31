# AI 模型设置标签页布局重构 - The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: 重构 AiModelsView.vue 为嵌套标签页布局
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 将 AiModelsView.vue 从垂直卡片布局改为内部包含三个子标签页的布局
  - 使用 el-tabs 组件，三个 tab-pane 分别对应三类模型
  - 每个标签页内展示对应类型的表格
  - 保留所有原有逻辑代码（数据获取、增删改查等），只修改模板部分
- **Acceptance Criteria Addressed**: [AC-1, AC-2, AC-5]
- **Test Requirements**:
  - `programmatic` TR-1.1: AiModelsView.vue 中包含 el-tabs，子标签页名称正确（"LLM推理模型"、"Embedding嵌入模型"、"Rerank重排序模型"）
  - `programmatic` TR-1.2: 每个标签页只展示对应类型的模型数据
  - `human-judgement` TR-1.3: 布局清晰，无过度重复代码

## [x] Task 2: 优化添加模型对话框的模型类型处理
- **Priority**: P0
- **Depends On**: [Task 1]
- **Description**: 
  - 添加模型时，自动将模型类型设置为当前激活标签页的类型
  - 新增时隐藏/禁用模型类型选择（因为由标签页决定）
  - 编辑时保持原类型不变（不可修改）
- **Acceptance Criteria Addressed**: [AC-3, AC-4]
- **Test Requirements**:
  - `programmatic` TR-2.1: 在 LLM 标签页点击添加，新增模型的 model_type 为 "llm"
  - `programmatic` TR-2.2: 在 Embedding 标签页点击添加，新增模型的 model_type 为 "embedding"
  - `programmatic` TR-2.3: 在 Rerank 标签页点击添加，新增模型的 model_type 为 "rerank"
  - `human-judgement` TR-2.4: 用户体验流畅，符合预期

## [x] Task 3: 验证所有功能完整可用
- **Priority**: P0
- **Depends On**: [Task 1, Task 2]
- **Description**: 
  - 验证添加、编辑、删除、设默认、测试连接功能在所有标签页内正常工作
  - 验证数据切换标签页时保持同步
- **Acceptance Criteria Addressed**: [AC-4]
- **Test Requirements**:
  - `human-judgement` TR-3.1: 所有操作按钮正常响应
  - `programmatic` TR-3.2: 数据修改后切换标签页，数据保持一致
  - `human-judgement` TR-3.3: 整体用户体验良好

## Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 1 and Task 2

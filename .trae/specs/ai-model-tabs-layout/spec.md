# AI 模型设置标签页布局重构 - Product Requirement Document

## Overview
- **Summary**: 将当前 AI 模型设置页面的垂直卡片布局重构为嵌套标签页布局，在 "AI 模型设置" 标签页内再包含三个子标签页（分别对应三类模型），使界面更宽松、更清晰。
- **Purpose**: 解决当前三类模型卡片垂直排列过于紧凑的问题，提供更好的用户体验。
- **Target Users**: 系统管理员、配置人员

## Goals
- 在 "AI 模型设置" 标签页内增加三个子标签页
- 每个子标签页只展示对应类型的模型配置
- 保持所有功能（增删改查、设默认、测试连接）完整可用
- 保持代码可维护性，避免重复代码

## Non-Goals (Out of Scope)
- 不改变后端 API
- 不改变数据模型
- 不重构路由配置（保持当前 SettingsView 入口不变）
- 不修改 "自动化调度与分发通道" 标签页

## Background & Context
- 当前实现：[SettingsView.vue](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/views/SettingsView.vue) 有两个标签页，其中「AI 模型配置」引入 [AiModelsView.vue](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/views/AiModelsView.vue)，垂直展示三类模型卡片
- 技术栈：Vue 3 + TypeScript + Element Plus
- 所有 API 已完整可用

## Functional Requirements
- **FR-1**: 「AI 模型设置」标签页内部包含三个子标签页
- **FR-2**: 每个子标签页只展示对应类型的模型配置
- **FR-3**: 所有现有功能（添加、编辑、删除、设默认、测试连接）在对应子标签页内正常工作
- **FR-4**: 添加模型时自动继承当前标签页的模型类型

## Non-Functional Requirements
- **NFR-1**: 切换标签页时保持数据同步（无需重复加载）
- **NFR-2**: 代码无明显重复，保持可维护性

## Constraints
- **Technical**: 必须使用现有的 Element Plus 组件库
- **Business**: 不能影响现有功能正常使用
- **Dependencies**: 现有 API 保持不变

## Assumptions
- 后端 API 保持兼容
- 用户习惯在 SettingsView 中导航
- 无需修改路由配置

## Acceptance Criteria

### AC-1: 嵌套标签页布局正确
- **Given**: 用户打开系统设置页面
- **When**: 点击「AI 模型设置」标签页
- **Then**: 页面内显示三个子标签页：「LLM推理模型」、「Embedding嵌入模型」、「Rerank重排序模型」
- **Verification**: `human-judgment`

### AC-2: 各子标签页只展示对应类型模型
- **Given**: 用户在「AI 模型设置」标签页内
- **When**: 切换不同子标签页
- **Then**: 每个子标签页只显示对应类型的模型配置表格
- **Verification**: `programmatic` + `human-judgment`

### AC-3: 添加模型时自动使用当前标签页类型
- **Given**: 用户在某个子标签页内
- **When**: 点击「添加模型」按钮
- **Then**: 新增模型的类型自动预设为当前标签页对应的类型（不可修改）
- **Verification**: `programmatic`

### AC-4: 所有现有功能正常工作
- **Given**: 用户在任意子标签页内
- **When**: 执行添加、编辑、删除、设默认、测试连接操作
- **Then**: 所有操作正常完成，数据同步更新
- **Verification**: `programmatic` + `human-judgment`

### AC-5: 代码结构清晰，无过度重复
- **Given**: 开发人员审阅代码
- **When**: 检查重构后的实现
- **Then**: 逻辑代码复用合理，模板部分保持清晰易读
- **Verification**: `human-judgment`

## Open Questions
- 无，需求已明确

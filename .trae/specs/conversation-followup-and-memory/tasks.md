# 对话追问与记忆功能 - 实现计划 (Decomposed and Prioritized Task List)

## [x] Task 1: 后端 Schema 扩展 - 支持对话历史参数
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 `backend/app/schemas/agent.py` 中为 `ReporterInput` 新增可选的 `conversation_history` 字段（列表类型，存储历史消息）。同时在 `backend/app/schemas/workflow.py` 中新增 `FollowUpRequest` Schema（包含 topic、message、conversation_history）。
- **Acceptance Criteria Addressed**: 追问上下文传递, ReporterAgent 输入
- **Test Requirements**:
  - programmatic: ReporterInput 能正常接收 conversation_history 参数
  - programmatic: FollowUpRequest 能正常通过 Pydantic 验证
- **Notes**: conversation_history 结构：[{role: "user"|"assistant", content: "..."}]

## [x] Task 2: 后端新增 /follow-up 流式接口
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 在 `backend/app/api/routes/workflow.py` 中新增 `POST /api/v1/workflow/follow-up` SSE 流式接口。接收 FollowUpRequest（含历史对话），直接调用 LLM 参考历史上下文快速响应，不触发完整四阶段工作流。
- **Acceptance Criteria Addressed**: 快速追问响应
- **Test Requirements**:
  - programmatic: 接口返回 SSE 格式流式数据
  - programmatic: LLM 能收到包含 conversation_history 的 prompt
  - programmatic: 响应时间在 30 秒内
- **Notes**: 使用与 ReporterAgent 相同的 LLM 调用逻辑，但 prompt 中注入对话历史

## [x] Task 3: 后端 ReporterAgent 支持对话历史上下文
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 修改 `backend/app/agents/reporter.py` 的 `_build_report_prompt` 方法，在 prompt 中注入 conversation_history 作为上下文参考，让 LLM 在生成报告时能引用之前的对话内容。
- **Acceptance Criteria Addressed**: 追问上下文传递, ReporterAgent 输入
- **Test Requirements**:
  - programmatic: 带有 conversation_history 的 ReporterInput 能正确生成包含历史引用的 prompt
  - human-judgment: 生成的报告内容能体现对前序对话的引用和延续
- **Notes**: 在 prompt 的 EXECUTIVE SUMMARY 之前插入对话历史摘要

## [x] Task 4: 后端工作流服务支持 follow-up 模式
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 在 `backend/app/services/workflow.py` 中新增 `_run_follow_up` 方法，实现基于 LLM 的快速追问响应逻辑。
- **Acceptance Criteria Addressed**: 快速追问响应
- **Test Requirements**:
  - programmatic: _run_follow_up 能正确接收消息和历史并调用 LLM
- **Notes**: 复用现有 ReporterAgent 的 LLM 调用逻辑

## [x] Task 5: 前端 API 服务新增 follow-up 接口封装
- **Priority**: P0
- **Depends On**: None
- **Description**: 在 `frontend/src/api/services/workflow.ts` 中新增 followUp 方法，封装对 /api/v1/workflow/follow-up 的 SSE 流式请求。
- **Acceptance Criteria Addressed**: 对话内追问功能
- **Test Requirements**:
  - programmatic: TypeScript 类型定义正确
  - programmatic: SSE 事件解析逻辑正确
- **Notes**: 复用现有的 start 方法的 SSE 连接模式

## [x] Task 6: 前端 Store 支持追问消息追加
- **Priority**: P0
- **Depends On**: Task 5
- **Description**: 在 `frontend/src/stores/workflow.ts` 中新增 `appendFollowUpMessage` 方法，实现在当前对话中追加追问消息（而非创建新对话）。同时新增 `startFollowUpStream` 方法管理追问的 SSE 流。
- **Acceptance Criteria Addressed**: 对话内追问功能
- **Test Requirements**:
  - programmatic: appendFollowUpMessage 正确将消息追加到当前对话
  - programmatic: 追问消息正确保存到 localStorage
- **Notes**: 追问消息的角色也是 user/assistant 对

## [x] Task 7: 前端 WorkflowView 修改发送逻辑
- **Priority**: P0
- **Depends On**: Task 6
- **Description**: 修改 `frontend/src/views/WorkflowView.vue`：
  1. 新增 `sendFollowUp` 方法，当存在活跃对话且已完成时调用
  2. 修改输入框区域，根据对话状态显示不同的按钮文案（"开始分析" vs "发送追问"）
  3. 当工作流运行中时，禁用输入框并显示"分析进行中"提示
  4. 输入框 placeholder 根据对话状态动态变化
- **Acceptance Criteria Addressed**: 对话内追问功能, startAnalysis 发送逻辑
- **Test Requirements**:
  - human-judgment: 首次发送显示"开始分析"，已有对话完成后显示"发送追问"
  - human-judgment: 工作流执行中时输入框不可用
  - human-judgment: 追问消息正确显示在当前对话中
- **Notes**: 按钮使用不同颜色和图标区分"开始分析"和"发送追问"

## [x] Task 8: 重新构建并部署前后端
- **Priority**: P1
- **Depends On**: Task 7
- **Description**: 重新构建 Docker 前后端镜像并部署，在浏览器中测试完整的追问流程。
- **Acceptance Criteria Addressed**: 全部
- **Test Requirements**:
  - human-judgment: 完整流程测试通过：首次分析→查看结果→追问→查看追问结果
  - human-judgment: 对话历史侧边栏正确显示所有对话
  - human-judgment: 切换对话后能正确恢复上下文

# Task Dependencies
- [Task 2] 依赖于 [Task 1]
- [Task 3] 依赖于 [Task 1]
- [Task 4] 依赖于 [Task 2]
- [Task 6] 依赖于 [Task 5]
- [Task 7] 依赖于 [Task 6]
- [Task 8] 依赖于 [Task 7]
# 修复导出失败与报告未同步 Spec

## Why
智能体工作流页面导出非 md 格式文件时均失败，原因是数据库 reports 表的 `task_id` 列仍为 integer 类型，工作流产生的字符串 workflow_id 无法写入导致 `_save_report` 静默失败。由于报告未入库，智能报告页面也无法展示对应报告。

## What Changes
- 在 `main.py` 应用启动时添加数据库迁移逻辑，将 `reports` 表的 `task_id` 列从 integer 类型改为 varchar(50)
- 增强 `_save_report` 的日志记录，确保错误信息可见
- 前端导出逻辑：确保 `_save_report` 完成后导出请求能正确查询到报告
- 优化 `_save_report` 增加重试机制，确保后台任务可靠执行

## Impact
- Affected specs: fix-workflow-conversation-llm-export
- Affected code:
  - `backend/main.py` - 新增启动时数据库迁移
  - `backend/app/services/workflow.py` - `_save_report` 增强日志和错误处理
  - `backend/app/core/db.py` - 新增迁移函数

## ADDED Requirements

### Requirement: 数据库列类型迁移
系统 SHALL 在启动时检测并迁移 `reports` 表的 `task_id` 列，确保其为 `varchar(50)` 类型。

#### Scenario: 应用启动时自动迁移
- **WHEN** 后端应用启动
- **THEN** 检测 `reports` 表 `task_id` 列的当前类型
- **AND** 如果为 integer 类型，则执行 `ALTER TABLE` 将其改为 `varchar(50)`
- **AND** 迁移日志记录操作结果

### Requirement: _save_report 增强日志
系统 SHALL 在 `_save_report` 方法中记录详细的成功/失败日志，便于诊断入库问题。

#### Scenario: 报告成功入库
- **WHEN** `_save_report` 成功执行
- **THEN** 记录 INFO 级别日志，包含 report id 和 workflow_id

#### Scenario: 报告入库失败
- **WHEN** `_save_report` 执行异常
- **THEN** 记录 ERROR 级别日志，包含完整异常堆栈和上下文信息

### Requirement: 导出前等待报告同步
系统 SHALL 在导出非 md 格式时，若首次查询未找到报告，则等待并重试。

#### Scenario: 报告刚写入尚未查询到
- **WHEN** 用户点击导出但报告尚未被 `_save_report` 完成写入
- **THEN** 前端最多重试 3 次，每次间隔 1 秒
- **AND** 最终找到报告则正常导出，否则提示用户稍后重试

## MODIFIED Requirements

### Requirement: 报告入库流程
`_save_report` 方法 SHALL 增加 `summary` 字段（截取 report_markdown 前 500 字符作为摘要），提升报告列表展示质量。

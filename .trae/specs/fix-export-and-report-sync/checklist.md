# Checklist

- [x] 后端启动时自动执行 reports 表 task_id 列类型迁移（integer -> varchar(50)）
- [x] _save_report 方法包含 INFO 级别开始/成功日志
- [x] _save_report 失败时记录 ERROR 级别日志并包含完整异常堆栈
- [x] _save_report 包含重试机制（最多 2 次）
- [x] _save_report 写入时包含 summary 字段（前 200 字符）
- [x] 前端导出非 md 格式时有重试逻辑（最多 3 次，每次间隔 1 秒）
- [x] 工作流完成后导出非 md 格式文件成功
- [x] 智能报告页面能展示工作流产出的报告
# Checklist

- [x] `export_report` 端点使用 `get_current_active_user_sse` 依赖（非 `get_current_active_user`）
- [x] `get_current_active_user_sse` 已正确导入
- [x] 后端 Docker 镜像重新构建并启动成功
- [x] 通过 `?token=xxx` 方式导出 PDF 成功（返回 200）
- [x] 通过 `?token=xxx` 方式导出 DOCX 成功（返回 200）
- [x] 通过 `?token=xxx` 方式导出 PPTX 成功（返回 200）

# Tasks
- [x] Task 1: 修复报告保存时 chart_images 未持久化问题
  - [x] SubTask 1.1: 修改 `create_from_workflow` 接收 chart_images 参数
  - [x] SubTask 1.2: 修改 workflow 保存报告时传入 chart_images
  - [x] SubTask 1.3: 统一 chart_images 存储格式为 `{"title": str, "base64": str}`
- [x] Task 2: 修复 PDF 导出临时文件处理
  - [x] SubTask 2.1: 将 PDF 导出中的 `NamedTemporaryFile(delete=False)` + `os.unlink` 改为安全的上下文管理器方式
- [x] Task 3: 验证 DOCX/PDF/PPTX 导出
  - [x] SubTask 3.1: 测试 PDF 导出图表正常显示
  - [x] SubTask 3.2: 测试 DOCX 导出图表正常嵌入
  - [x] SubTask 3.3: 测试 PPTX 导出图表正常嵌入

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1, Task 2]

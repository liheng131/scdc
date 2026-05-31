# Tasks
- [x] Task 1: 修复 PDF 解析器 - 过滤无效内容
  - [x] SubTask 1.1: 在 PDFParser 中检测 PDF 原始二进制内容（%PDF 头部、大量不可打印字符）
  - [x] SubTask 1.2: 跳过无有效文本的页面（扫描件/图片PDF）
  - [x] SubTask 1.3: 增加内容有效性检测逻辑
- [x] Task 2: 增强 CleanerAgent 内容过滤
  - [x] SubTask 2.1: 检测并过滤 PDF 原始二进制内容
  - [x] SubTask 2.2: 检测并过滤其他非人类可读内容
- [x] Task 3: 修复 ReporterAgent 图表中文显示
  - [x] SubTask 3.1: 配置 matplotlib 使用支持中文的字体
  - [x] SubTask 3.2: 在 Dockerfile 中安装中文字体包
- [x] Task 4: 验证修复效果
  - [x] SubTask 4.1: 端到端测试 PDF 内容过滤
  - [x] SubTask 4.2: 验证图表中文正常显示

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 4] depends on [Task 1, Task 2, Task 3]

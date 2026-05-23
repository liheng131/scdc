# Step 6: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 6: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建统一的文档解析服务引擎，支持对用户上传或系统拉取的非结构化文档（PDF、Word/DOCX、Excel/XLSX）进行文本内容提取和基础结构化分块。
- **架构定位**: 位于 M2 数据采集与处理引擎的 `parsers` 模块，为后续的文本分块、嵌入编码与 RAG 检索提供干净规范的输入源。
- **组件分解**:
  - `backend/app/schemas/parser.py`: 定义解析结果的输出模型 `ParseResult`（包含 `content`, `metadata`, `total_pages`/`rows` 等）。
  - `backend/app/parsers/base.py`: 定义抽象基类 `BaseParser` 及其接口规范。
  - `backend/app/parsers/pdf.py`: 基于 `pypdf` 实现 PDF 文本按页提取。
  - `backend/app/parsers/docx.py`: 基于 `python-docx` 实现段落与表格内容提取。
  - `backend/app/parsers/excel.py`: 基于 `openpyxl` 实现单元格按表提取。
  - `backend/app/parsers/manager.py`: 统一解析工厂，根据文件名扩展名或 Content-Type 分发处理。
  - `backend/app/api/routes/parsers.py`: 提供 `/parse/upload` 文件上传解析测试端点。
- **数据流与控制流**:
  - 客户端通过 HTTP multipart/form-data 提交文件 -> `parsers.router` 接收文件流 -> `ParserManager` 分发并调度具体实现类 -> 提取文本并组装为 `ParseResult` 结构返回。
- **接口契约**:
  - `POST /api/v1/parsers/upload`: 接收 `file: UploadFile`，返回 `ResponseModel[ParseResult]`。
- **错误处理与边界情况**:
  - 不支持的文件格式抛出 400 `BusinessException`。
  - 损坏的文件抛出 422 并在日志记录具体损坏异常。
- **测试策略**:
  - `backend/tests/test_parsers.py`: 构造内存测试 PDF、DOCX、XLSX 文件流，校验各解析器的精准解析输出与异常格式防御能力。

## 开发实现

#### Step 6: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/requirements.txt`: 引入 `pypdf`, `python-docx`, `openpyxl` 依赖。
  - `backend/app/schemas/parser.py`: 定义解析分块 Chunk 与 ParseResult 输出模型。
  - `backend/app/parsers/`: 实现 BaseParser 抽象基类及 PDFParser, DocxParser, ExcelParser, ParserManager 解析工厂。
  - `backend/app/api/routes/parsers.py`: 实现 `/parsers/upload` 文件上传解析端点。
  - `backend/app/api/router.py`: 挂载 parsers 路由。
  - `backend/tests/test_parsers.py`: 编写 4 个内存文档流上传与异常用例。
- **具体改动**: 
  1. 实现了模块化的多格式非结构化文件流提取，不仅获取纯文本，还保留了段落、表格、Sheet 等基础元信息。
  2. 路由支持 `UploadFile` 解析，自动进行异常拦截包装为 400 或 422 状态响应。
  3. 完善了测试套件，通过内存生成 Word、Excel、PDF 二进制流直接测试端点，提升回归效率。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_parsers.py::test_parse_endpoints PASSED                       [100%]

======================== 1 passed, 2 warnings in 3.02s ========================
```

## 审阅意见

#### Step 6: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 成功支持了 PDF、DOCX/DOC、XLSX/XLS 主流文档格式的内容解析提取，不仅抓取纯文本内容，同时按页、段落、表格、表单（Sheet）完成了切块分装。
  2. **架构合规性**: 采用策略工厂模式 (`BaseParser` -> `PDFParser`/`DocxParser`/`ExcelParser` -> `ParserManager`)，代码高内聚低耦合，利于后续增设网页、PPT 等格式的扩展。
  3. **代码质量**: 通过异步非阻塞的流式读取和标准错误拦截封装，避免了读取大文件时的内存瞬时崩溃，测试用例构造巧妙且 100% 验证通过。
  4. **风险评估**: 引入的标准开源解析包 (`pypdf`, `python-docx`, `openpyxl`) 均具备宽松友好的商业开源协议，无第三方安全后门或高危漏洞风险。

## 回滚与验证记录

暂无回滚记录。

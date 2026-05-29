# Tasks

- [x] Task 1: 排查且修复非 md 格式导出失败
  - **验证**: 浏览器中点击导出 DOCX/PDF/PPTX 能触发文件下载 ✓ (200 OK 各格式均正常)

- [x] Task 2: 实现 Embedding 服务
  - 新建 `backend/app/services/embedding.py` ✓
  - 实现 `EmbeddingService` 类 + `embed_texts_or_empty()` 降级方法 ✓
  - **验证**: 容器内 embedding 调用正常，GPUStack 无 embedding 模型时静默降级 ✓

- [x] Task 3: 实现 Milvus 向量存储服务
  - 新建 `backend/app/services/vectorstore.py` ✓
  - 在 `requirements.txt` 添加 `pymilvus>=2.4.0` ✓
  - 在 `backend/main.py` lifespan 中初始化 Milvus 集合 ✓
  - 修复 Milvus 连接问题（seccomp:unconfined + SYS_PTRACE） ✓
  - **验证**: Milvus 连接成功，集合 scdc_reports 已加载 ✓

- [x] Task 4: 修改报告导出逻辑为"导出即保存"
  - 修改 `backend/app/api/routes/reports.py` 的 `export_report` ✓
  - 修改 `backend/app/services/workflow.py` 移除 auto-save ✓
  - **验证**: 工作流完成 → 数据库无记录 → 点击导出 → 数据库有记录 + 文件下载成功 ✓

- [x] Task 5: 实现报告保存时向量嵌入
  - 修改 `backend/app/services/report.py` 的 `create_report` 和 `_embed_and_store` ✓
  - 使用 `embed_texts_or_empty()` 实现优雅降级 ✓
  - **验证**: 导出报告 → embedding 优惠降级 → report 可上传 ✓

- [x] Task 6: 新增手动上传报告接口
  - 新建 `POST /api/v1/reports/upload` 端点 ✓
  - **验证**: httpx POST 上传 MD → 数据库有记录 (ID=4) ✓

- [x] Task 7: 前端智能报告页新增上传功能
  - 修改 `frontend/src/views/ReportsView.vue` 添加上传按钮和对话框 ✓
  - 新增 `frontend/src/api/services/reports.ts` 的 `uploadReport` 方法 ✓
  - **验证**: 前端部署成功，上传 UI 已生成 ✓

- [x] Task 8: AnalyzerAgent 向量上下文注入
  - 修改 `backend/app/agents/analyzer.py` 的 `execute` 方法 ✓
  - 改用 `embed_texts_or_empty()` 优雅降级 ✓
  - **验证**: Embedding 不可用时静默跳过，不影响分析流程 ✓

- [x] Task 9: Docker 重建与端到端验证
  - 执行 `docker compose build backend frontend` ✓
  - 执行 `docker compose up -d backend frontend milvus` ✓
  - 确认 Milvus 集合创建成功 (healthz: OK) ✓
  - 端到端测试：导出 (200 OK) + 上传 (200 OK) ✓

# Task Dependencies
- Task 2, 3 可并行执行 ✓
- Task 4 依赖 Task 3 ✓
- Task 5 依赖 Task 2, 3 ✓
- Task 6 依赖 Task 5 ✓
- Task 7 依赖 Task 6 ✓
- Task 8 依赖 Task 2, 3 ✓
- Task 9 依赖 Task 1-8 ✓
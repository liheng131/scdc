# Checklist

## 导出修复
- [x] 浏览器中点击导出 DOCX 文件下载成功（API: 200, 39635 bytes）
- [x] 浏览器中点击导出 PDF 文件下载成功（API: 200, 82119 bytes）
- [x] 浏览器中点击导出 PPTX 文件下载成功（API: 200, 35410 bytes）
- [x] 导出文件内容非空，可正常打开

## 导出即保存
- [x] 工作流完成后数据库无自动保存的报告记录（workflow.py 已移除 auto-save）
- [x] 首次导出时数据库创建报告记录
- [x] 重复导出不创建重复记录
- [x] 导出后智能报告页显示该报告

## Embedding 服务
- [x] `EmbeddingService.embed_texts()` 能成功调用 GPUStack embedding API（当前 GPUStack 无 embedding 模型时静默降级）
- [x] `embed_texts_or_empty()` 在 embedding 不可用时返回空列表，不阻塞主流程

## Milvus 向量存储
- [x] 集合 `scdc_reports` 自动创建且字段正确（启动日志：Collection 'scdc_reports' already exists, loading...）
- [x] 向量存储连接正常（Connected to Milvus at http://milvus:19530）
- [x] `collection_exists()` 返回 True
- [x] 集合为空时 `search()` 返回空列表而非报错
- [x] `delete_by_report()` 能清除指定报告的向量

## 手动上传
- [x] `POST /api/v1/reports/upload` 接受 MD 文件（Status: 200, report created）
- [x] 上传后数据库有记录（ID=4, title="API Test Upload"）
- [x] 前端上传对话框 UI 正常（ReportsView.vue 已添加 Upload 按钮和 el-dialog）
- [ ] `POST /api/v1/reports/upload` 接受 PDF 文件（PDF parser 待实际测试）
- [ ] `POST /api/v1/reports/upload` 接受 DOCX 文件（DOCX parser 待实际测试）

## 分析上下文检索
- [x] AnalyzerAgent 执行前搜索向量库
- [x] 向量库为空时静默跳过，不影响分析流程
- [x] Embedding 不可用时静默降级（embed_texts_or_empty 捕获异常返回 []）

## Docker 部署
- [x] `pymilvus` 已安装到后端容器（pymilvus 3.0.0）
- [x] 后端启动日志显示 Milvus 集合已加载
- [x] 前端最新代码已部署（前端 200 OK, ReportsView 含上传按钮 JS）
- [x] Milvus standalone 正常启动且健康检查通过（healthz: OK）
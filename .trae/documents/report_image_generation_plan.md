# 报告配图生成能力调研报告及实现计划

## 一、当前系统调研结论

### 1. 报告生成流程
- 报告生成由 [`ReporterAgent`](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/agents/reporter.py) 负责
- 流程：收集洞察(Insights) → 组装成Markdown格式报告 → 保存到数据库
- 报告结构包含：标题、执行摘要、详细章节（市场概况、核心发现、竞争格局、趋势预测、结论建议等）

### 2. LLM 模型能力
- 系统通过 `app/core/config.py` 配置 LLM
- 当前 LLM 主要用于文本生成（洞察分析、报告撰写）
- **不支持图片生成**：LLM 本身是文本模型，无法直接生成图像

### 3. 图片生成能力
- 系统**已集成** ComfyUI 图片生成服务（通过 [`ImageGenerationService`](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/services/image_generation.py)）
- ComfyUI 服务地址配置在 `settings.comfyui_url`
- 图片生成流程：文本 prompt → ComfyUI 工作流 → 返回图片 URL
- 当前图片生成主要用于工作流中的视觉素材，未与报告生成集成

## 二、实现方案

### 方案概述
在报告生成过程中，根据报告正文内容自动生成配套插图，实现图文结合。

### 核心思路
1. **报告结构增强**：在报告 schema 中新增图片字段，支持存储配图信息
2. **智能配图生成**：报告生成后，分析各章节内容，为关键章节生成配图 prompt
3. **调用 ComfyUI 生成图片**：使用已有的 ImageGenerationService 生成配图
4. **图片与报告关联**：将生成的图片 URL 关联到对应章节
5. **前端展示**：在报告详情页面图文混排展示

### 技术可行性
✅ 可行。系统已有 ComfyUI 图片生成服务，只需在报告生成流程中集成调用即可。

## 三、实现步骤

### Phase 1: 数据库与 Schema 扩展
1. 修改 Report 模型，新增 `images` 字段（JSON，存储配图信息：章节、prompt、图片URL、位置）
2. 修改 ReportCreate/ReportOut schema，支持图片字段
3. 创建数据库 migration 添加 images 列

### Phase 2: 配图生成服务
1. 新建 `ReportImageService` 服务类
2. 实现章节内容分析 → 生成图片 prompt 的逻辑
3. 集成调用现有的 `ImageGenerationService`
4. 实现图片生成后的存储和关联

### Phase 3: 报告生成流程集成
1. 修改 `ReporterAgent` 或报告创建流程
2. 报告生成完成后，异步触发配图生成
3. 配图生成后更新报告记录

### Phase 4: 前端报告展示优化
1. 修改报告详情页面，支持图文混排展示
2. 图片按章节位置插入
3. 图片加载优化（懒加载、占位符）

### Phase 5: 配置与优化
1. 添加配置项控制是否启用自动配图
2. 控制每个报告生成的图片数量
3. 配图生成失败时的降级处理

## 四、风险与注意事项

1. **配图质量**：ComfyUI 生成的图片质量取决于 prompt 设计，需要精心设计 prompt 模板
2. **生成时间**：图片生成较慢，需异步处理，避免阻塞报告生成
3. **存储成本**：图片需要存储空间，考虑使用对象存储或 CDN
4. **LLM 上下文**：分析章节内容生成 prompt 可能消耗较多 token
5. **兼容性**：旧报告没有图片字段，前端需要兼容处理

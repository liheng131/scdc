# 大纲模板功能废弃评估 Spec

## Why
当前系统中存在完整的大纲模板功能（数据模型、CRUD 服务、API 路由、前端管理页面），但经过代码审计发现：**模板功能与工作流管线完全脱节，零集成**。

ReporterAgent 中：
- LLM 正常时：使用 `_build_report_prompt()` 中**硬编码**的 prompt 模板生成报告
- LLM 失败降级时：使用 `_build_template_report()` 中**硬编码**的结构化模板生成报告

`TemplateService.render_template()` 方法注释写明"供 ReporterAgent 调用"，但 ReporterAgent **从未**调用过该方法。用户在 TemplatesView 页面保存的模板数据从未被任何流程消费。

用户明确表示：不希望模板作为 LLM 失败降级处理的兜底。

## 数据分析

### 当前模板功能代码清单
| 层级 | 文件 | 用途 | 是否被工作流使用 |
|------|------|------|:---:|
| 数据模型 | `models/template.py` | templates 表定义 | ❌ 否 |
| 服务层 | `services/template.py` | CRUD + Jinja2 渲染 | ❌ 否 |
| API 路由 | `api/routes/templates.py` | RESTful CRUD 端点 | ❌ 否 |
| Schema | `schemas/template.py` | 请求/响应校验 | ❌ 否 |
| 前端页面 | `views/TemplatesView.vue` | 管理界面 | ❌ 否 |
| 路由注册 | `api/router.py` | 注册 `/api/v1/templates` | ❌ 否 |
| ReporterAgent | `agents/reporter.py` | `_build_template_report()` 是硬编码模板，与 DB 无关 | ❌ 否 |

### 两种方案对比

| 维度 | 方案 A：一刀切删除 | 方案 B：集成到 LLM prompt 构建 |
|------|:---|:---|
| 复杂度 | 低，纯删除 | 中，需要重构 `_build_report_prompt` |
| 用户价值 | 消除无用功能，减少困惑 | 用户可自定义报告章节结构 |
| 维护成本 | 零 | 需持续维护模板语法、渲染错误 |
| 风险 | 无 | 模板语法错误可能导致报告生成失败 |
| 推荐度 | **强烈推荐** | 不推荐 |

## What Changes

### 方案 A：一刀切删除（推荐）
- 删除 `backend/app/models/template.py`
- 删除 `backend/app/services/template.py`
- 删除 `backend/app/api/routes/templates.py`
- 删除 `backend/app/schemas/template.py`
- 删除 `frontend/src/views/TemplatesView.vue`
- 从 `backend/app/api/router.py` 移除 templates 路由注册
- 从 `backend/app/models/__init__.py` 移除 Template 导入（如存在）
- 从 `frontend/src/router/index.ts` 移除模板页面路由
- 从 `frontend/src/views/SettingsView.vue` 移除模板管理入口（如存在）
- 数据库迁移：`DROP TABLE IF EXISTS templates`

### ReporterAgent 不变
- `_build_template_report()` 保留，它是 LLM 失败时的**硬编码兜底**，不依赖 DB
- 它产生的是结构化数据输出（置信度 + 引用），仍有实用价值

## Impact
- Affected code:
  - `backend/app/models/template.py` - 删除
  - `backend/app/services/template.py` - 删除
  - `backend/app/api/routes/templates.py` - 删除
  - `backend/app/schemas/template.py` - 删除
  - `backend/app/api/router.py` - 移除路由注册
  - `frontend/src/views/TemplatesView.vue` - 删除
  - `frontend/src/router/index.ts` - 移除路由
  - `frontend/src/views/SettingsView.vue` - 移除入口

## ADDED Requirements
无

## MODIFIED Requirements
无

## REMOVED Requirements
### Requirement: 大纲模板管理
**Reason**: 此功能从未被工作流管线消费，ReporterAgent 使用硬编码模板生成报告，DB 模板完全闲置。
**Migration**: 执行 `DROP TABLE IF EXISTS templates` 清理数据库。
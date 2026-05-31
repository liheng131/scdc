# 大纲模板功能分析与集成方案

## 一、现状分析

### 1.1 大纲模板功能现有架构

| 层级 | 文件 | 功能 |
|------|------|------|
| 数据库模型 | `backend/app/models/template.py` | `templates` 表，字段：name/scope/version/content/status |
| Schema | `backend/app/schemas/template.py` | `TemplateCreate`/`TemplateUpdate`/`TemplateOut` |
| 服务层 | `backend/app/services/template.py` | 完整 CRUD + Jinja2 模板渲染引擎 |
| API 路由 | `backend/app/api/routes/templates.py` | `POST/GET/PUT/DELETE` + `/render` 预览端点 |
| 前端页面 | `frontend/src/views/TemplatesView.vue` | 模板列表管理 + Jinja2 在线插值预览沙箱 |
| 前端 API | `frontend/src/api/services/templates.ts` | 封装了 getTemplates/createTemplate/renderPreview 等 |

### 1.2 核心问题：模板与工作流完全脱节

**关键发现：工作流流水线中没有任何地方使用 `TemplateService`！**

- `ReporterAgent._build_template_report()` 是**硬编码**的 Python 模板，不是从数据库读取的
- `CollectorAgent`、`CleanerAgent`、`AnalyzerAgent`、`OrchestratorAgent` 均未导入 `TemplateService`
- 用户在模板页面保存的 Jinja2 模板只是存入了数据库，但**从未被任何流程消费**

```python
# ReporterAgent 中的硬编码模板（与数据库模板无关）
def _build_template_report(self, topic, summary, insights, evidence_map, reference_list):
    header = f"# 深度市场洞察报告：{topic}\n\n..."
    exec_section = f"## 📑 执行摘要 (Executive Summary)\n\n{summary}\n\n"
    # ... 完全硬编码的结构
```

### 1.3 模板设计初衷 vs 实际状态

| 设计初衷（代码注释描述） | 实际状态 |
|--------------------------|----------|
| "将 Prompt 和报告格式与代码解耦，非技术人员也可修改" | 报告格式完全硬编码在 `reporter.py` 中 |
| "ReporterAgent 生成报告后，通过模板将结构化数据渲染为最终 Markdown" | ReporterAgent 从未调用 `TemplateService` |
| "用户可自定义模板内容，调整报告的格式、段落结构" | 用户保存的模板无人使用 |
| "支持按 scope 分类管理生命周期" | scope 分类仅用于前端展示，无实际作用 |

### 1.4 结论

**当前的"大纲模板"功能是一个孤立的 CRUD 管理页面，不参与任何实际业务流水线。用户保存的模板数据永远不会被消费，没有实际意义。**

---

## 二、方案：将模板接入报告生成流程

### 2.1 核心思路

让 `ReporterAgent` 在生成报告时，如果用户指定了 `template_id`（或存在默认模板），则使用数据库中的 Jinja2 模板来格式化报告内容，而不是使用硬编码的 `_build_template_report`。

### 2.2 改动范围

| 文件 | 改动内容 |
|------|----------|
| `backend/app/agents/reporter.py` | 新增 `template_id` 参数，支持从数据库加载模板渲染报告 |
| `backend/app/agents/orchestrator.py` | 支持传入 `template_id` 给 ReporterAgent |
| `backend/app/schemas/agent.py` | `ReporterInput` 新增 `template_id: Optional[int]` 字段 |
| `backend/app/services/workflow.py` | 工作流创建时支持指定模板 |
| `frontend/src/views/TemplatesView.vue` | 已存在的模板管理页面无需改动 |
| `frontend/src/views/WorkflowView.vue` | 新增模板选择器，用户可在发起工作流时选择模板 |

### 2.3 具体实现步骤

#### Step 1: ReporterAgent 支持模板渲染

修改 `backend/app/agents/reporter.py`：

- `ReporterInput` 新增 `template_id: Optional[int] = None` 字段
- 在 `execute()` 方法中，当 LLM 生成失败需要降级时：
  1. 如果 `template_id` 有值，从数据库加载模板并用 Jinja2 渲染
  2. 如果 `template_id` 为空，回退到原有的硬编码 `_build_template_report`
- 即使 LLM 成功生成报告，如果用户指定了模板，可以在 LLM 生成后也套用模板的结构化格式

#### Step 2: OrchestratorAgent 传递模板参数

修改 `backend/app/agents/orchestrator.py`：

- `OrchestratorInput` 新增 `template_id: Optional[int] = None` 字段
- 在调用 `ReporterAgent.execute()` 时传递 `template_id`

#### Step 3: 工作流 API 支持模板选择

修改 `backend/app/services/workflow.py`：

- `create_workflow()` 新增 `template_id: Optional[int] = None` 参数
- 传递给 `OrchestratorInput`

#### Step 4: 前端工作流页面添加模板选择器

修改 `frontend/src/views/WorkflowView.vue`：

- 在发起工作流的表单中新增模板下拉选择框
- 调用 `templatesApi.getTemplates({ scope: 'report', status: 'active' })` 获取可用模板列表
- 用户可选择"不使用模板"（默认）或选择一个模板

### 2.4 数据流转

```
用户在 TemplatesView 保存模板 → 存入 templates 表
                                                    ↓
用户在 WorkflowView 发起工作流 → 选择模板(可选) → template_id
                                                    ↓
工作流创建 → OrchestratorAgent → ReporterAgent → 加载模板
                                                    ↓
Jinja2 渲染：{{ topic }} → 实际话题, {{ insights }} → 分析数据
                                                    ↓
生成最终 Markdown 报告
```

### 2.5 模板内容示例

用户在模板页面可以保存如下 Jinja2 模板：

```jinja2
# {{ topic }} - 深度市场洞察报告

> 执行时间: {{ execution_time }}
> 分析引擎: {{ analysis_engine }}

## 📑 执行摘要
{{ summary }}

## 🎯 维度分析
{% for dim, items in dimensions.items() %}
### {{ dim }}
{% for item in items %}
- **{{ item.conclusion }}** (置信度: {{ item.confidence }})
  {{ item.analysis }}
{% endfor %}
{% endfor %}

## 🔗 参考来源
{% for ref in references %}
[^{{ loop.index }}]: {{ ref }}
{% endfor %}
```

---

## 三、收益

1. **模板价值实现**：用户保存的模板终于能被工作流消费，不再是孤立的无用功能
2. **报告格式可定制**：不同用户/场景可以保存不同的报告模板（如 SWOT 分析模板、竞品分析模板等）
3. **非技术人员可维护**：业务人员可以通过前端页面修改模板，无需改动代码
4. **向后兼容**：不选择模板时行为与现在完全一致，零破坏性

---

## 四、不做的

- 不做模板的 AI 自动生成
- 不做模板市场/分享功能
- 不做模板版本对比/diff 功能